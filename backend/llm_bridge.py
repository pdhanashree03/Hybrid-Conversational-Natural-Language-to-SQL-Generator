"""
LLM bridge — only called for complex queries NLP cannot handle.
Uses Ollama with a very tight, structured prompt.
"""

import re
import json
import requests

OLLAMA_URL   = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "phi3"   # change to mistral if you have more RAM


def build_llm_prompt(text: str, schema: dict, plan) -> str:
    """Build a minimal prompt with only relevant schema."""
    # Find relevant tables by name matching
    relevant_tables = {}
    text_lower = text.lower()

    for table, info in schema["tables"].items():
        if table.lower() in text_lower or any(
            token in table.lower() for token in text_lower.split()
            if len(token) > 3
        ):
            relevant_tables[table] = info

    # If no match, include all
    if not relevant_tables:
        relevant_tables = schema["tables"]

    # Build compact DDL
    ddl_lines = []
    for table, info in relevant_tables.items():
        col_defs = [f"{c['name']} {c['type']}" for c in info["columns"]]
        fk_defs  = [
            f"-- FK: {fk['from'][0]} -> {fk['to_table']}.{fk['to_cols'][0]}"
            for fk in info.get("foreign_keys", [])
        ]
        ddl_lines.append(f"TABLE {table}({', '.join(col_defs + fk_defs)})")

    ddl = "\n".join(ddl_lines)

    # Exact table names
    table_list = ", ".join(schema["tables"].keys())

    return f"""You are a SQLite SQL generator. Output ONLY JSON.

SCHEMA:
{ddl}

EXACT TABLE NAMES: {table_list}

QUERY: {text}

RULES:
- Use ONLY table names from EXACT TABLE NAMES above
- Always prefix columns: TableName.ColumnName
- No placeholder values
- For JOINs use FK relationships shown above

Output ONLY this JSON:
{{"sql":"SELECT ...","explanation":"brief description","tables_used":["t1"],"confidence":0.9}}"""


def call_ollama(prompt: str) -> str:
    try:
        requests.get("http://localhost:11434", timeout=3)
    except Exception:
        raise Exception("Ollama not running. Start with: ollama serve")

    try:
        resp = requests.post(
            OLLAMA_URL,
            json={
                "model":  OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.1,
                    "num_predict": 200,
                    "num_ctx":     1024,
                }
            },
            timeout=120
        )
        resp.raise_for_status()
        return resp.json().get("response", "").strip()
    except requests.exceptions.Timeout:
        raise Exception("Ollama timed out. Try: ollama run phi3 hello")
    except requests.exceptions.ConnectionError:
        raise Exception("Cannot connect to Ollama. Run: ollama serve")


def fix_json(text: str) -> str:
    text = re.sub(r',\s*}', '}', text)
    text = re.sub(r',\s*]', ']', text)
    text = re.sub(r'(["\d\]}])\s*\n\s*(")', r'\1,\n\2', text)
    text = re.sub(r'([\]"}])\s+("(?:sql|explanation|tables_used|confidence)")', r'\1,\2', text)
    if '"confidence"' not in text and text.rstrip().endswith('}'):
        text = text.rstrip()[:-1] + ',"confidence":0.9}'
    return text


def parse_llm_response(raw: str) -> dict:
    # Direct parse
    try:
        return json.loads(raw)
    except Exception:
        pass

    # Strip markdown
    cleaned = re.sub(r'```json|```', '', raw).strip()
    try:
        return json.loads(cleaned)
    except Exception:
        pass

    # Fix and retry
    try:
        return json.loads(fix_json(cleaned))
    except Exception:
        pass

    # Find JSON block
    match = re.search(r'\{[\s\S]*\}', raw)
    if match:
        try:
            return json.loads(fix_json(match.group()))
        except Exception:
            pass

    # SQL fallback
    sql = re.search(r'(SELECT[\s\S]+?)(?:;|$)', raw, re.IGNORECASE)
    if sql:
        return {
            "sql":         sql.group(1).strip(),
            "explanation": "Query generated",
            "tables_used": [],
            "confidence":  0.5
        }

    raise Exception(f"Could not parse LLM response: {raw[:300]}")


def generate_sql_llm(text: str, schema: dict, plan) -> dict:
    """Call LLM when NLP alone cannot build the SQL."""
    prompt = build_llm_prompt(text, schema, plan)
    print(f"[llm] Calling Ollama for complex query...")
    raw = call_ollama(prompt)
    print(f"[llm] Response: {raw[:300]}")
    return parse_llm_response(raw)