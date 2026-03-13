"""
query_executor.py
-----------------
Validates and safely executes SQL SELECT queries.
"""

import re
import logging
from database_connection import get_connection

logger  = logging.getLogger(__name__)
BLOCKED = {"DROP","DELETE","UPDATE","INSERT","CREATE","ALTER","TRUNCATE","ATTACH","DETACH","PRAGMA"}
MAX_ROWS = 500


def validate_query(sql: str) -> dict:
    if not sql or not sql.strip():
        return {"valid": False, "error": "SQL query is empty."}
    if not re.match(r"^\s*SELECT\b", sql.strip(), re.IGNORECASE):
        return {"valid": False, "error": "Only SELECT queries are allowed."}
    for token in re.findall(r"\b[A-Z_]+\b", sql.upper()):
        if token in BLOCKED:
            return {"valid": False, "error": "Forbidden keyword '{}' detected.".format(token)}
    if ";" in sql.strip()[:-1]:
        return {"valid": False, "error": "Multiple statements not allowed."}
    return {"valid": True, "error": None}


def execute_query(sql: str) -> dict:
    v = validate_query(sql)
    if not v["valid"]:
        return {"success": False, "columns": [], "rows": [], "row_count": 0,
                "truncated": False, "error": v["error"], "executed_sql": sql}
    try:
        conn   = get_connection()
        cursor = conn.cursor()
        cursor.execute(sql)
        raw       = cursor.fetchmany(MAX_ROWS + 1)
        truncated = len(raw) > MAX_ROWS
        raw       = raw[:MAX_ROWS]
        conn.close()

        if raw:
            columns = list(raw[0].keys())
            rows    = [dict(r) for r in raw]
        else:
            conn2   = get_connection()
            cur2    = conn2.cursor()
            cur2.execute(sql)
            columns = [d[0] for d in (cur2.description or [])]
            rows    = []
            conn2.close()

        return {"success": True, "columns": columns, "rows": rows,
                "row_count": len(rows), "truncated": truncated,
                "error": None, "executed_sql": sql}

    except RuntimeError as e:
        return {"success": False, "columns": [], "rows": [], "row_count": 0,
                "truncated": False, "error": str(e), "executed_sql": sql}
    except Exception as e:
        return {"success": False, "columns": [], "rows": [], "row_count": 0,
                "truncated": False, "error": "Query failed: {}".format(e), "executed_sql": sql}
