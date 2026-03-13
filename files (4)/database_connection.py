"""
database_connection.py
----------------------
Manages connections to user-uploaded SQLite databases.
Uses a session-based approach: each upload gets a unique file stored in /uploads.
The active database path is stored in a simple JSON state file.
"""

import sqlite3
import os
import json
import logging

logger = logging.getLogger(__name__)

BASEDIR     = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR  = os.path.join(BASEDIR, "uploads")
STATE_FILE  = os.path.join(BASEDIR, "active_db.json")

os.makedirs(UPLOAD_DIR, exist_ok=True)


def set_active_db(path: str):
    """Save the currently active database path."""
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump({"path": path}, f)
    logger.info("Active DB set to: %s", path)


def get_active_db() -> str:
    """Return the currently active database path, or None if not set."""
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("path")
    except Exception:
        return None


def get_connection():
    """
    Return a SQLite connection to the currently active database.
    Raises RuntimeError if no database has been uploaded yet.
    """
    db_path = get_active_db()
    if not db_path or not os.path.exists(db_path):
        raise RuntimeError("No database loaded. Please upload a .db or .sqlite file first.")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def get_db_info() -> dict:
    """Return info about the currently active database."""
    db_path = get_active_db()
    if not db_path or not os.path.exists(db_path):
        return {"loaded": False, "name": None, "path": None, "size_kb": None}
    size_kb = round(os.path.getsize(db_path) / 1024, 1)
    return {
        "loaded": True,
        "name": os.path.basename(db_path),
        "path": db_path,
        "size_kb": size_kb,
    }
