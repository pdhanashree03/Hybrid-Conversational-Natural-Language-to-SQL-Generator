from sqlalchemy import create_engine, text
import re


def fix_ambiguous(sql: str, schema: dict) -> str:
    tables_used = [
        t for t in schema["tables"].keys()
        if re.search(rf'\b{t}\b', sql, re.IGNORECASE)
    ]
    if len(tables_used) < 2:
        return sql
    qualified = ", ".join(f"{t}.*" for t in tables_used)
    return re.sub(r'SELECT\s+\*', f'SELECT {qualified}', sql, flags=re.IGNORECASE)


def execute_query(db_url: str, sql: str, schema: dict = None) -> dict:
    engine = create_engine(db_url)
    print(f"[executor] Running SQL:\n{sql}")

    try:
        with engine.connect() as conn:
            result  = conn.execute(text(sql))
            columns = list(result.keys())
            rows    = [dict(zip(columns, row)) for row in result.fetchall()]
        return {"columns": columns, "rows": rows, "count": len(rows)}

    except Exception as e:
        err = str(e).lower()

        # Auto-fix ambiguous columns
        if "ambiguous" in err and schema:
            fixed = fix_ambiguous(sql, schema)
            print(f"[executor] Retrying with fixed SQL:\n{fixed}")
            with engine.connect() as conn:
                result  = conn.execute(text(fixed))
                columns = list(result.keys())
                rows    = [dict(zip(columns, row)) for row in result.fetchall()]
            return {"columns": columns, "rows": rows, "count": len(rows)}

        # Helpful error for wrong table name
        if "no such table" in err:
            m = re.search(r'no such table: (\w+)', str(e))
            wrong = m.group(1) if m else "unknown"
            actual = list(schema["tables"].keys()) if schema else []
            raise Exception(
                f"Table '{wrong}' not found. Available tables: {actual}"
            )

        raise Exception(f"SQL Error: {str(e)}\nSQL: {sql}")