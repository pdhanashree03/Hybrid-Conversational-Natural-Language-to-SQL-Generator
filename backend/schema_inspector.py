from sqlalchemy import create_engine, inspect


def get_schema(db_url: str) -> dict:
    engine  = create_engine(db_url)
    insp    = inspect(engine)
    dialect = engine.dialect.name
    schema  = {"dialect": dialect, "tables": {}}

    for table in insp.get_table_names():
        fks = [
            {
                "from":     fk["constrained_columns"],
                "to_table": fk["referred_table"],
                "to_cols":  fk["referred_columns"],
            }
            for fk in insp.get_foreign_keys(table)
        ]
        schema["tables"][table] = {
            "columns":      [
                {
                    "name":     c["name"],
                    "type":     str(c["type"]),
                    "nullable": c.get("nullable", True),
                }
                for c in insp.get_columns(table)
            ],
            "primary_keys": insp.get_pk_constraint(table).get("constrained_columns", []),
            "foreign_keys": fks,
        }

    return schema


def get_all_names(schema: dict) -> dict:
    tables  = list(schema["tables"].keys())
    columns = []
    for tbl in schema["tables"].values():
        columns.extend([c["name"] for c in tbl["columns"]])
    return {"tables": tables, "columns": columns}