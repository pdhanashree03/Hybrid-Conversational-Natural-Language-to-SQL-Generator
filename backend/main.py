import os
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from session_memory import ConversationMemory
memory = ConversationMemory()
print("[startup] Loading modules...")
from schema_inspector import get_schema
from nlp_engine       import NLPEngine
from llm_bridge       import generate_sql_llm
from db_executor      import execute_query
print("[startup] Ready.")

app = FastAPI(title="NL-to-SQL")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Global state
current_schema = {}
current_db_url = ""


@app.get("/ping")
def ping():
    return {"status": "ok"}


@app.post("/upload-db")
async def upload_db(file: UploadFile = File(...)):
    global current_schema, current_db_url

    suffix = os.path.splitext(file.filename)[-1].lower()
    if suffix not in (".db", ".sqlite", ".sqlite3"):
        raise HTTPException(400, f"Unsupported type '{suffix}'. Use .db/.sqlite/.sqlite3")

    save_path = os.path.join(UPLOAD_DIR, "current" + suffix)
    if os.path.exists(save_path):
        os.remove(save_path)

    contents = await file.read()
    with open(save_path, "wb") as f:
        f.write(contents)
    print(f"[upload] Saved {len(contents)} bytes → {save_path}")

    db_url = f"sqlite:///{save_path}"
    try:
        schema = get_schema(db_url)
    except Exception as e:
        raise HTTPException(400, f"Cannot read DB: {str(e)}")

    current_schema = schema
    current_db_url = db_url
    tables = list(schema["tables"].keys())
    print(f"[upload] Tables: {tables}")

    return {"db_url": db_url, "filename": file.filename, "tables": tables}

@app.post("/ask")
async def ask(
    query:  str = Form(...),
    db_url: str = Form(...),
):
    global current_schema

    if not current_schema:
        try:
            current_schema = get_schema(db_url)
        except Exception as e:
            raise HTTPException(400, f"Cannot read schema: {str(e)}")

    print(f"\n[ask] Turn {memory.turn_num + 1}: '{query}'")

    try:
        # Step 1 — NLP builds SQL directly
        engine = NLPEngine(current_schema)
        result = engine.process(query)
        plan   = result["plan"]

        
       # Step 2 — Resolve against conversation history
        plan = memory.resolve(plan, query)

        # Always re-extract filters after memory resolution
        # Re-extract filters after memory resolution
        if plan.tables:
            engine2     = NLPEngine(current_schema)
            new_filters = engine2.extract_filters(query, plan.tables)
            print(f"[ask] Filter re-extraction: {[(f.col, f.operator, f.value) for f in new_filters]}")
            if new_filters:
                existing_cols = {f.col for f in plan.where_clauses if f.col}
                for f in new_filters:
                    # Only add filter if col belongs to a table in current query
                    if f.col and f.col not in existing_cols:
                        col_table = f.col.split(".")[0] if "." in f.col else None
                        if col_table and col_table in plan.tables:
                            plan.where_clauses.append(f)
                            existing_cols.add(f.col)
                            print(f"[ask] Added filter: {f.col} {f.operator} {f.value}")

        used_llm    = False
        explanation = ""
        confidence  = 0.95
        sql         = ""

        # Re-evaluate needs_llm AFTER memory resolution
        needs_llm = result["needs_llm"] and not plan.tables

        if needs_llm:
            print(f"[ask] NLP insufficient, calling LLM...")
            llm_result  = generate_sql_llm(query, current_schema, plan)
            sql         = llm_result["sql"]
            explanation = llm_result.get("explanation", "")
            confidence  = llm_result.get("confidence", 0.8)
            used_llm    = True
        else:
            try:
                engine2 = NLPEngine(current_schema)
                sql = engine2.plan_to_sql(plan)
            except Exception as sql_err:
                print(f"[ask] plan_to_sql failed: {sql_err}, falling back to LLM")
                llm_result  = generate_sql_llm(query, current_schema, plan)
                sql         = llm_result["sql"]
                explanation = llm_result.get("explanation", "")
                confidence  = llm_result.get("confidence", 0.8)
                used_llm    = True
            print(f"[ask] NLP built SQL successfully")

        # Step 3 — Execute
        data = execute_query(db_url, sql, schema=current_schema)
        print(f"[ask] Rows: {data['count']}")

        # Step 4 — Store turn in memory  ← NEW
        try:
            memory.store(plan, sql)
        except Exception as mem_err:
            print(f"[memory] Store failed (non-critical): {mem_err}")

        # Build trace
        trace = {
            "tables":          plan.tables,
            "joins":           [{"table": j.table, "on": f"{j.on_left} = {j.on_right}"} for j in plan.joins],
            "aggregate":       plan.aggregate,
            "aggregate_col":   plan.aggregate_col,
            "filters":         [f.__dict__ for f in plan.where_clauses if hasattr(f, '__dict__')],
            "group_by":        plan.group_by,
            "order_by":        plan.order_by,
            "order_dir":       plan.order_dir,
            "limit":           plan.limit,
            "used_llm":        used_llm,
        }

        if not explanation:
            explanation = build_explanation(plan, data["count"])

        return {
            "sql":          sql,
            "explanation":  explanation,
            "confidence":   confidence,
            "data":         data,
            "trace":        trace,
            "used_llm":     used_llm,
            "turn_number":  memory.turn_num,           # ← NEW
            "conversation": memory.history_summary,    # ← NEW
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(500, str(e))

def build_explanation(plan, row_count: int) -> str:
    """Build a human-readable explanation from the query plan."""
    parts = []

    if plan.aggregate == "COUNT":
        parts.append(f"Counted {row_count} records")
    elif plan.aggregate:
        parts.append(f"Calculated {plan.aggregate.lower()} of {plan.aggregate_col or 'values'}")
    else:
        parts.append(f"Retrieved {row_count} rows")

    if plan.tables:
        parts.append(f"from {', '.join(plan.tables)}")

    if plan.joins:
        joined = [j.table for j in plan.joins]
        parts.append(f"joined with {', '.join(joined)}")

    if plan.where_clauses:
        parts.append(f"with {len(plan.where_clauses)} filter(s)")

    if plan.group_by:
        parts.append(f"grouped by {plan.group_by}")

    if plan.order_by:
        parts.append(f"ordered by {plan.order_by} {plan.order_dir}")

    if plan.limit:
        parts.append(f"limited to {plan.limit}")

    return " ".join(parts) + "."


@app.post("/clear-session")
def clear_session():
    global current_schema, current_db_url
    memory.clear()   
    current_schema = {}
    current_db_url = ""
    return {"status": "cleared"}


@app.get("/schema")
def schema_view(db_url: str):
    try:
        return get_schema(db_url)
    except Exception as e:
        raise HTTPException(400, str(e))