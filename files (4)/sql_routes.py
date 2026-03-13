"""sql_routes.py - /text-to-sql, /execute-query, /voice-to-sql"""

import logging
from flask import Blueprint, jsonify, request
from text_to_sql    import convert_text_to_sql
from query_executor import execute_query

sql_bp = Blueprint("sql", __name__)
logger = logging.getLogger(__name__)


@sql_bp.route("/text-to-sql", methods=["POST"])
def text_to_sql():
    body = request.get_json(silent=True) or {}
    text = body.get("text", "").strip()
    if not text:
        return jsonify({"success": False, "error": "Field 'text' is required."}), 400
    result = convert_text_to_sql(text)
    if result["success"]:
        return jsonify({"success": True, "sql": result["sql"],
                        "method": result["method"], "original_text": text}), 200
    return jsonify({"success": False, "error": result["error"]}), 400


@sql_bp.route("/execute-query", methods=["POST"])
def execute_query_route():
    body = request.get_json(silent=True) or {}
    sql  = body.get("sql", "").strip()
    if not sql:
        return jsonify({"success": False, "error": "Field 'sql' is required."}), 400
    result = execute_query(sql)
    return jsonify(result), 200 if result["success"] else 400


@sql_bp.route("/voice-to-sql", methods=["POST"])
def voice_to_sql():
    body = request.get_json(silent=True) or {}
    text = body.get("text", "").strip()
    if not text:
        return jsonify({"success": False, "error": "Field 'text' is required."}), 400
    nl = convert_text_to_sql(text)
    if not nl["success"]:
        return jsonify({"success": False, "error": nl["error"]}), 400
    ex = execute_query(nl["sql"])
    if not ex["success"]:
        return jsonify({"success": False, "sql": nl["sql"], "error": ex["error"]}), 400
    return jsonify({"success": True, "original_text": text, "sql": nl["sql"],
                    "method": nl["method"], "columns": ex["columns"],
                    "rows": ex["rows"], "row_count": ex["row_count"],
                    "truncated": ex["truncated"]}), 200
