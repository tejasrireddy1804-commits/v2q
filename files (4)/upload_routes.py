"""
upload_routes.py
----------------
Handles database file uploads and schema introspection.

Endpoints:
  POST /upload-db     - Upload a .db or .sqlite file
  GET  /db-info       - Get info about the currently loaded database
  GET  /tables        - List all tables with columns and row counts
  POST /clear-db      - Remove the active database
"""

import os
import sqlite3
import logging
from flask import Blueprint, jsonify, request, current_app
from database_connection import set_active_db, get_active_db, get_connection, get_db_info, UPLOAD_DIR

upload_bp = Blueprint("upload", __name__)
logger    = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {".db", ".sqlite", ".sqlite3"}


def allowed_file(filename: str) -> bool:
    _, ext = os.path.splitext(filename.lower())
    return ext in ALLOWED_EXTENSIONS


@upload_bp.route("/upload-db", methods=["POST"])
def upload_db():
    """
    POST /upload-db
    Accepts a multipart/form-data file upload.
    Validates it is a real SQLite file, saves it, sets it as active.
    """
    if "file" not in request.files:
        return jsonify({"success": False, "error": "No file provided. Send file as 'file' field."}), 400

    file = request.files["file"]

    if not file.filename:
        return jsonify({"success": False, "error": "No file selected."}), 400

    if not allowed_file(file.filename):
        return jsonify({
            "success": False,
            "error": "Invalid file type. Only .db, .sqlite, .sqlite3 files are allowed."
        }), 400

    # Save the file
    safe_name = os.path.basename(file.filename)
    save_path = os.path.join(UPLOAD_DIR, safe_name)
    file.save(save_path)
    logger.info("Saved uploaded file: %s", save_path)

    # Validate it is a real SQLite database
    try:
        conn = sqlite3.connect(save_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [r["name"] for r in cursor.fetchall() if not r["name"].startswith("sqlite_")]
        conn.close()
    except Exception as e:
        os.remove(save_path)
        return jsonify({
            "success": False,
            "error": "File is not a valid SQLite database: {}".format(e)
        }), 400

    if not tables:
        return jsonify({
            "success": False,
            "error": "The database has no tables. Please upload a database with data."
        }), 400

    # Set as active database
    set_active_db(save_path)

    # Get full schema
    schema = _get_schema(save_path)

    return jsonify({
        "success":    True,
        "message":    "Database uploaded successfully!",
        "filename":   safe_name,
        "tables":     schema,
        "table_count": len(schema),
    }), 200


@upload_bp.route("/db-info", methods=["GET"])
def db_info():
    """GET /db-info - Returns info about the currently loaded database."""
    info = get_db_info()
    if not info["loaded"]:
        return jsonify({"success": False, "loaded": False,
                        "error": "No database loaded yet."}), 200
    schema = _get_schema(info["path"])
    return jsonify({
        "success":  True,
        "loaded":   True,
        "name":     info["name"],
        "size_kb":  info["size_kb"],
        "tables":   schema,
        "table_count": len(schema),
    }), 200


@upload_bp.route("/tables", methods=["GET"])
def get_tables():
    """GET /tables - List all tables with columns and row counts."""
    info = get_db_info()
    if not info["loaded"]:
        return jsonify({"success": False, "error": "No database loaded. Please upload a .db file first."}), 400

    schema = _get_schema(info["path"])
    return jsonify({"success": True, "tables": schema}), 200


@upload_bp.route("/clear-db", methods=["POST"])
def clear_db():
    """POST /clear-db - Clears the active database."""
    import json
    state_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "active_db.json")
    try:
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump({"path": None}, f)
        return jsonify({"success": True, "message": "Database cleared."}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


def _get_schema(db_path: str) -> list:
    """Return full schema of a SQLite database."""
    try:
        conn   = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        table_names = [r["name"] for r in cursor.fetchall() if not r["name"].startswith("sqlite_")]

        tables = []
        for tname in table_names:
            cursor.execute("PRAGMA table_info({})".format(tname))
            columns = [
                {"name": c["name"], "type": c["type"] or "TEXT",
                 "not_null": bool(c["notnull"]), "pk": bool(c["pk"])}
                for c in cursor.fetchall()
            ]
            try:
                cursor.execute("SELECT COUNT(*) AS cnt FROM {}".format(tname))
                row_count = cursor.fetchone()["cnt"]
            except Exception:
                row_count = 0

            tables.append({"name": tname, "columns": columns, "row_count": row_count})

        conn.close()
        return tables
    except Exception as e:
        logger.error("Schema error: %s", e)
        return []
