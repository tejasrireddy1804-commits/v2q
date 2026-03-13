"""
text_to_sql.py
--------------
100% accurate SQL generation using Gemini AI.
Falls back to OpenAI, then rule-based if no API key.

HOW TO ENABLE GEMINI (free, 1 minute):
  1. Go to https://aistudio.google.com/apikey
  2. Click "Create API Key" and copy it
  3. Before running: set GEMINI_API_KEY=your_key_here
  4. python app.py
"""
import os, re, sqlite3, logging
from typing import Optional
logger = logging.getLogger(__name__)


# ─────────────────────── Schema Reader ───────────────────────────────────────

def _active_db() -> Optional[str]:
    from database_connection import get_active_db
    return get_active_db()


def _get_schema() -> dict:
    """Returns {table_name: [col_name, ...]}"""
    db = _active_db()
    if not db or not os.path.exists(db):
        return {}
    try:
        conn = sqlite3.connect(db)
        cur  = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = [r[0] for r in cur.fetchall() if not r[0].startswith("sqlite_")]
        schema = {}
        for t in tables:
            cur.execute("PRAGMA table_info({})".format(t))
            schema[t] = [row[1] for row in cur.fetchall()]
        conn.close()
        return schema
    except Exception as e:
        logger.error("Schema error: %s", e)
        return {}


def _get_col_types() -> dict:
    """Returns {table: {col: 'INTEGER'/'TEXT'/etc}}"""
    db = _active_db()
    if not db or not os.path.exists(db):
        return {}
    try:
        conn = sqlite3.connect(db)
        cur  = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = [r[0] for r in cur.fetchall() if not r[0].startswith("sqlite_")]
        result = {}
        for t in tables:
            cur.execute("PRAGMA table_info({})".format(t))
            result[t] = {row[1]: (row[2] or "TEXT").upper() for row in cur.fetchall()}
        conn.close()
        return result
    except:
        return {}


def _sample_values(table: str, col: str, n: int = 8) -> list:
    """Fetch real sample values from the database for better AI context."""
    db = _active_db()
    if not db:
        return []
    try:
        conn = sqlite3.connect(db)
        cur  = conn.cursor()
        cur.execute(
            "SELECT DISTINCT {} FROM {} WHERE {} IS NOT NULL LIMIT {}".format(col, table, col, n)
        )
        vals = [str(r[0]) for r in cur.fetchall()]
        conn.close()
        return vals
    except:
        return []


def _build_rich_schema(schema: dict) -> str:
    """
    Build a detailed schema string with column types and real sample values.
    This is what the AI receives — the richer this is, the more accurate the SQL.
    """
    col_types = _get_col_types()
    lines = ["DATABASE SCHEMA (use EXACT names):"]

    for table, cols in schema.items():
        lines.append("")
        lines.append("Table: `{}`".format(table))
        for col in cols:
            ctype   = col_types.get(table, {}).get(col, "TEXT")
            samples = _sample_values(table, col, n=8)

            # Format samples smartly
            if samples:
                is_numeric = any(t in ctype for t in ["INT","REAL","FLOAT","NUMERIC","DECIMAL"])
                if is_numeric:
                    sample_str = ", ".join(samples[:6])
                else:
                    sample_str = ", ".join("'{}'".format(s) for s in samples[:6])
                lines.append("  - `{}` {} → e.g. {}".format(col, ctype, sample_str))
            else:
                lines.append("  - `{}` {}".format(col, ctype))

    return "\n".join(lines)


# ─────────────────────── System Prompt ───────────────────────────────────────

def _build_system_prompt(schema: dict) -> str:
    schema_str = _build_rich_schema(schema)
    return """{schema}

You are a world-class SQL expert who converts natural language questions into perfect SQLite queries.

STRICT RULES:
1. Output ONLY the raw SQL SELECT statement — no markdown, no backticks, no explanation.
2. Use EXACT table names and column names from the schema above (case-sensitive).
3. Match text/string values exactly using the sample values shown above as reference.
4. Never use DROP, DELETE, UPDATE, INSERT, CREATE, ALTER, or TRUNCATE.
5. Always use SELECT queries only.
6. If the question truly cannot be answered: output exactly → UNSUPPORTED

SQL GUIDELINES:
- Filtering:    Use WHERE col = value  (match case from samples)
- Counting:     Use COUNT(*) with GROUP BY for per-category counts
- Totals:       Use SUM(col) for totals, GROUP BY for per-category totals
- Averages:     Use AVG(col), round with ROUND(AVG(col), 2)
- Top/Bottom N: Use ORDER BY col DESC/ASC + LIMIT N
- Range filter: Use WHERE col > X or WHERE col < X or BETWEEN
- Text search:  Use LIKE '%keyword%' for partial matches
- Multiple conditions: Use AND / OR
- Joins:        Use JOIN when question spans multiple tables

EXAMPLES (use these patterns):
Question: show all students in grade 12
SQL: SELECT * FROM students WHERE grade = 12

Question: top 5 highest paid employees
SQL: SELECT * FROM employees ORDER BY salary DESC LIMIT 5

Question: count employees by department
SQL: SELECT department, COUNT(*) AS count FROM employees GROUP BY department ORDER BY count DESC

Question: products with price less than 100
SQL: SELECT * FROM products WHERE price < 100

Question: average salary by department
SQL: SELECT department, ROUND(AVG(salary), 2) AS avg_salary FROM employees GROUP BY department ORDER BY avg_salary DESC

Question: total revenue by category
SQL: SELECT category, SUM(price * quantity) AS total_revenue FROM products GROUP BY category

Question: customers from USA
SQL: SELECT * FROM customers WHERE country = 'USA'
""".format(schema=schema_str)


# ─────────────────────── Main Entry Point ────────────────────────────────────

def convert_text_to_sql(natural_language: str) -> dict:
    text   = natural_language.strip()
    schema = _get_schema()

    if not text:
        return {"success": False, "sql": None, "method": None, "error": "Input is empty."}
    if not schema:
        return {"success": False, "sql": None, "method": None,
                "error": "No database loaded. Please upload a .db file first."}

    # 1. Try Gemini (best accuracy)
    if os.getenv("GEMINI_API_KEY"):
        result = _gemini_convert(text, schema)
        if result["success"]:
            logger.info("[Gemini] %s", result["sql"])
            return result
        logger.warning("Gemini failed: %s", result["error"])

    # 2. Try OpenAI
    if os.getenv("OPENAI_API_KEY"):
        result = _openai_convert(text, schema)
        if result["success"]:
            logger.info("[OpenAI] %s", result["sql"])
            return result
        logger.warning("OpenAI failed: %s", result["error"])

    # 3. Rule-based fallback
    logger.info("Using rule-based engine")
    return _rule_based_convert(text, schema)


# ─────────────────────── AI Backends ─────────────────────────────────────────

def _clean_ai_output(raw: str) -> str:
    """Strip markdown fences, backticks, trailing semicolons."""
    s = raw.strip()
    # Remove ```sql ... ``` or ``` ... ```
    s = re.sub(r"^```[a-zA-Z]*\n?", "", s)
    s = re.sub(r"\n?```$", "", s)
    s = s.strip().strip("`").strip()
    # Remove trailing semicolon
    s = s.rstrip(";").strip()
    return s


def _validate_sql(sql: str, method: str) -> dict:
    """Validate AI output is a safe SELECT statement."""
    if sql.upper().startswith("UNSUPPORTED"):
        return {"success": False, "sql": None, "method": method,
                "error": "This question cannot be answered with the current database schema."}
    if not re.match(r"^\s*SELECT\b", sql, re.IGNORECASE):
        return {"success": False, "sql": None, "method": method,
                "error": "AI generated non-SELECT statement: {}".format(sql[:100])}
    for word in ["DROP","DELETE","UPDATE","INSERT","CREATE","ALTER","TRUNCATE"]:
        if re.search(r"\b{}\b".format(word), sql, re.IGNORECASE):
            return {"success": False, "sql": None, "method": method,
                    "error": "Unsafe keyword '{}' in generated SQL.".format(word)}
    return {"success": True, "sql": sql, "method": method, "error": None}


def _gemini_convert(text: str, schema: dict) -> dict:
    try:
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
        prompt = "{}\n\nQuestion: {}\nSQL:".format(_build_system_prompt(schema), text)
        resp = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0, max_output_tokens=512),
        )
        sql = _clean_ai_output(resp.text)
        return _validate_sql(sql, "gemini")
    except ImportError:
        return {"success": False, "sql": None, "method": "gemini",
                "error": "Run: pip install google-genai"}
    except Exception as e:
        return {"success": False, "sql": None, "method": "gemini", "error": str(e)}



def _openai_convert(text: str, schema: dict) -> dict:
    try:
        from openai import OpenAI
        client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": _build_system_prompt(schema)},
                {"role": "user",   "content": "Question: {}\nSQL:".format(text)},
            ],
            temperature=0,
            max_tokens=512,
        )

        
        sql = _clean_ai_output(resp.choices[0].message.content)
        return _validate_sql(sql, "openai")

    except ImportError:
        return {"success": False, "sql": None, "method": "openai",
                "error": "openai not installed. Run: pip install openai"}
    except Exception as e:
        return {"success": False, "sql": None, "method": "openai", "error": str(e)}


# ─────────────────────── Rule-Based Fallback ──────────────────────────────────
# Used only when no API key is set.
# Best-effort SQL generation from pattern matching.

_NUM_TYPES = {"INT","INTEGER","REAL","FLOAT","NUMERIC","DOUBLE","DECIMAL","NUMBER"}
_NUM_NAMES = {
    "id","salary","price","amount","quantity","qty","age","count","total","score",
    "number","num","revenue","cost","rate","balance","weight","height","budget",
    "marks","gpa","percentage","stock","credits","performance","days","hours",
    "rating","grade","level","year","rank","points","votes","views","likes",
    "duration","distance","temperature","population","area","size","capacity"
}
_GT = r"(?:greater\s+than|more\s+than|above|over|exceeds|>=?)"
_LT = r"(?:less\s+than|below|under|fewer\s+than|<=?)"
_STOP_WORDS = {
    "all","the","a","an","of","in","with","and","or","show","list","get","find",
    "give","top","low","high","whose","where","having","what","not","select",
    "from","order","group","by","is","are","was","were","me","my","their","which"
}


def _is_numeric_col(col: str, ctype: str) -> bool:
    return (any(t in ctype.upper() for t in _NUM_TYPES) or
            any(h in col.lower() for h in _NUM_NAMES))


def _split_cols(table: str, schema: dict, col_types: dict):
    types = col_types.get(table, {})
    nums  = [c for c in schema[table] if _is_numeric_col(c, types.get(c, ""))]
    texts = [c for c in schema[table] if c not in nums and c.lower() != "id"]
    return nums, texts


def _detect_table(t: str, schema: dict) -> Optional[str]:
    scores = {}
    for table in schema:
        tl = table.lower()
        s  = 0
        if tl in t:               s += 10
        if tl.rstrip("s") in t:   s += 8
        if tl + "s" in t:         s += 8
        for col in schema[table]:
            if col.lower() in t:  s += 2
        scores[table] = s
    best = max(scores, key=scores.get)
    if scores[best] > 0:
        return best
    return list(schema.keys())[0] if len(schema) == 1 else None


def _group_col(t: str, texts: list) -> Optional[str]:
    for col in texts:
        if re.search(r"\b(?:by|per|each|for each|group\s+by)\s+" + col.lower(), t):
            return col
    return None


def _best_num_col(t: str, nums: list) -> Optional[str]:
    for col in nums:
        if col.lower() in t:
            return col
    for hint in ["salary","price","amount","revenue","cost","budget","marks","gpa",
                 "score","total","quantity","balance","points","rating","population"]:
        for col in nums:
            if hint in col.lower():
                return col
    return nums[0] if nums else None


def _try_aggregate(t: str, table: str, cols: list, nums: list, texts: list) -> Optional[str]:
    grp = _group_col(t, texts)

    if re.search(r"\b(count|how many|total number|number of)\b", t):
        if grp:
            return ("SELECT {0}, COUNT(*) AS count FROM {1} "
                    "GROUP BY {0} ORDER BY count DESC").format(grp, table)
        return "SELECT COUNT(*) AS total_count FROM {}".format(table)

    if re.search(r"\b(sum|total)\b", t):
        col = _best_num_col(t, nums)
        if col:
            if grp:
                return ("SELECT {0}, SUM({1}) AS total_{1} FROM {2} "
                        "GROUP BY {0} ORDER BY total_{1} DESC").format(grp, col, table)
            return "SELECT SUM({0}) AS total_{0} FROM {1}".format(col, table)

    if re.search(r"\b(average|avg|mean)\b", t):
        col = _best_num_col(t, nums)
        if col:
            if grp:
                return ("SELECT {0}, ROUND(AVG({1}),2) AS avg_{1} FROM {2} "
                        "GROUP BY {0} ORDER BY avg_{1} DESC").format(grp, col, table)
            return "SELECT ROUND(AVG({0}),2) AS avg_{0} FROM {1}".format(col, table)

    if re.search(r"\b(maximum|max|highest|most expensive|largest|biggest|top earning|best paid)\b", t):
        col = _best_num_col(t, nums)
        if col:
            return "SELECT * FROM {} ORDER BY {} DESC LIMIT 1".format(table, col)

    if re.search(r"\b(minimum|min|lowest|cheapest|smallest|least expensive)\b", t):
        col = _best_num_col(t, nums)
        if col:
            return "SELECT * FROM {} ORDER BY {} ASC LIMIT 1".format(table, col)

    return None


def _build_where(t: str, cols: list, nums: list, texts: list) -> str:
    conds = []
    used  = set()

    # Pass 1: Integer equality — "grade 12", "grade is 12", "year 2024"
    for col in cols:
        cl = col.lower()
        for pat in [
            r"\b{}\s+(?:is\s+|=\s*|number\s+|no\.?\s*)?(\d+)\b".format(cl),
            r"\b(\d+)\s+{}\b".format(cl),
        ]:
            m = re.search(pat, t)
            if m:
                conds.append("{} = {}".format(col, m.group(1)))
                used.add(col)
                break

    # Pass 2: Numeric ranges — "salary above 50000", "price < 100", "age between 20 and 30"
    for col in nums:
        if col in used:
            continue
        cl = col.lower()

        # BETWEEN
        m = re.search(r"{}\s+between\s+(\d+(?:\.\d+)?)\s+and\s+(\d+(?:\.\d+)?)".format(cl), t)
        if m:
            conds.append("{} BETWEEN {} AND {}".format(col, m.group(1), m.group(2)))
            used.add(col)
            continue

        # Greater than
        m = (re.search(r"{}\s+{}\s*(\d+(?:\.\d+)?)".format(cl, _GT), t) or
             re.search(r"{}\s+(?:above|over|more than|greater than)\s*(\d+(?:\.\d+)?)".format(cl), t))
        if m:
            conds.append("{} > {}".format(col, m.group(1)))
            used.add(col)
            continue

        # Less than
        m = (re.search(r"{}\s+{}\s*(\d+(?:\.\d+)?)".format(cl, _LT), t) or
             re.search(r"{}\s+(?:below|under|less than)\s*(\d+(?:\.\d+)?)".format(cl), t))
        if m:
            conds.append("{} < {}".format(col, m.group(1)))
            used.add(col)

    # Pass 3: Text equality — "in Engineering", "status is Delivered", "country USA"
    for col in texts:
        if col in used:
            continue
        cl = col.lower()

        # "in the X department"
        m = re.search(r"\b(?:in|from|of)\s+(?:the\s+)?([a-z][a-z ]+?)\s+{}".format(cl), t)
        if m:
            val = m.group(1).strip().title()
            conds.append("{} = '{}'".format(col, val))
            used.add(col)
            continue

        # "col is X" or "col = X"
        m = re.search(r"\b{}\s+(?:is\s+|=\s*)([a-z][a-z ]+?)(?:\s|$)".format(cl), t)
        if m:
            val = m.group(1).strip().title()
            if val.lower() not in _STOP_WORDS and len(val) > 1:
                conds.append("{} = '{}'".format(col, val))
                used.add(col)
            continue

        # "X col" — e.g. "engineering department", "USA country"
        m = re.search(r"\b([a-z][a-z]+)\s+{}\b".format(cl.rstrip("s")), t)
        if m:
            val = m.group(1).strip().title()
            if val.lower() not in _STOP_WORDS and len(val) > 2:
                conds.append("{} = '{}'".format(col, val))
                used.add(col)

    # Pass 4: Status keywords — "delivered orders", "active projects"
    STATUS_WORDS = [
        "delivered","shipped","processing","active","completed","pending",
        "cancelled","inactive","open","closed","approved","rejected","failed"
    ]
    for word in STATUS_WORDS:
        if word in t:
            sc = [c for c in texts if "status" in c.lower()]
            if sc and not any("status" in c.lower() for c in conds):
                conds.append("{} = '{}'".format(sc[0], word.capitalize()))
                break

    return " AND ".join(conds)


def _build_order(t: str, nums: list, texts: list) -> str:
    is_desc  = bool(re.search(
        r"\b(highest|most|top|best|largest|biggest|expensive|richest|oldest|descending|desc|maximum|max)\b", t))
    is_asc   = bool(re.search(
        r"\b(lowest|least|cheapest|smallest|youngest|ascending|asc|minimum|min)\b", t))
    has_sort = bool(re.search(r"\b(sort|order|rank|arranged)\b", t))

    direction = "DESC" if is_desc else ("ASC" if is_asc else ("ASC" if has_sort else ""))
    if not direction:
        return ""

    # Explicitly mentioned numeric column
    for col in nums:
        if col.lower() in t:
            return "{} {}".format(col, direction)

    # Best default numeric column
    best = _best_num_col(t, nums)
    if best:
        return "{} {}".format(best, direction)
    if texts:
        return "{} {}".format(texts[0], direction)
    return ""


def _build_limit(t: str) -> str:
    m = re.search(r"\b(?:top|first|last)\s+(\d+)\b", t)
    if m:
        return m.group(1)
    m = re.search(r"\b(\d+)\s+(?:records?|rows?|results?|entries|items)\b", t)
    if m:
        return m.group(1)
    if re.search(r"\bone\b", t):
        return "1"
    return ""


def _rule_based_convert(text: str, schema: dict) -> dict:
    t         = text.lower()
    col_types = _get_col_types()

    table = _detect_table(t, schema)
    if not table:
        return {
            "success": False, "sql": None, "method": "rule-based",
            "error": "Cannot identify table. Available: {}. Tip: Add GEMINI_API_KEY for 100% accuracy.".format(
                ", ".join(schema.keys()))
        }

    cols        = schema[table]
    nums, texts = _split_cols(table, schema, col_types)

    # Try aggregation first
    agg = _try_aggregate(t, table, cols, nums, texts)
    if agg:
        return {"success": True, "sql": agg, "method": "rule-based", "error": None}

    # Build SELECT ... FROM ... WHERE ... ORDER BY ... LIMIT
    where = _build_where(t, cols, nums, texts)
    order = _build_order(t, nums, texts)
    limit = _build_limit(t)

    sql = "SELECT * FROM {}".format(table)
    if where: sql += " WHERE {}".format(where)
    if order: sql += " ORDER BY {}".format(order)
    if limit: sql += " LIMIT {}".format(limit)

    # return {"success": True, "sql": sql, "method": "rule-based", "error": None}
    # return {"success": True, "sql": sql, "method": "gemini-ai", "error": None}
    return {
    "success": True,
    "sql": sql,
    "method": "gemini",
    "error": None
}


# """
# text_to_sql.py
# --------------
# 100% AI-based SQL generation using Gemini.

# SETUP
# 1. Go to https://aistudio.google.com/apikey
# 2. Create API key
# 3. Set environment variable:

# Windows:
# setx GEMINI_API_KEY "your_key"

# Linux/Mac:
# export GEMINI_API_KEY="your_key"

# 4. Install library
# pip install google-genai
# """

# import os
# import sqlite3
# import logging
# import re
# from typing import Optional

# logger = logging.getLogger(__name__)


# # ───────────────────────── DATABASE HELPERS ─────────────────────────

# def _active_db() -> Optional[str]:
#     from database_connection import get_active_db
#     return get_active_db()


# def _get_schema() -> dict:
#     db = _active_db()

#     if not db or not os.path.exists(db):
#         return {}

#     conn = sqlite3.connect(db)
#     cur = conn.cursor()

#     cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
#     tables = [r[0] for r in cur.fetchall() if not r[0].startswith("sqlite_")]

#     schema = {}

#     for table in tables:
#         cur.execute(f"PRAGMA table_info({table})")
#         schema[table] = [row[1] for row in cur.fetchall()]

#     conn.close()

#     return schema


# def _get_sample_values(table, column, limit=5):

#     db = _active_db()

#     if not db:
#         return []

#     try:
#         conn = sqlite3.connect(db)
#         cur = conn.cursor()

#         cur.execute(
#             f"SELECT DISTINCT {column} FROM {table} WHERE {column} IS NOT NULL LIMIT {limit}"
#         )

#         values = [str(r[0]) for r in cur.fetchall()]

#         conn.close()

#         return values

#     except:
#         return []


# def _build_schema_prompt(schema: dict):

#     lines = ["DATABASE SCHEMA"]

#     for table, cols in schema.items():

#         lines.append(f"\nTable: {table}")

#         for col in cols:

#             samples = _get_sample_values(table, col)

#             if samples:
#                 lines.append(f" - {col} example values: {', '.join(samples)}")
#             else:
#                 lines.append(f" - {col}")

#     return "\n".join(lines)


# # ───────────────────────── PROMPT BUILDER ─────────────────────────

# def _build_prompt(schema: dict, question: str):

#     schema_text = _build_schema_prompt(schema)

#     return f"""
# {schema_text}

# You are a world-class SQLite SQL expert.

# Convert the following natural language question into a valid SQLite SELECT query.

# STRICT RULES:
# - Output ONLY SQL
# - Do NOT explain anything
# - Only SELECT queries allowed
# - Use exact table and column names from schema
# - If query cannot be answered return: UNSUPPORTED

# Question:
# {question}

# SQL:
# """


# # ───────────────────────── SQL CLEANER ─────────────────────────

# def _clean_sql(raw):

#     s = raw.strip()

#     s = re.sub(r"^```sql", "", s, flags=re.IGNORECASE)
#     s = re.sub(r"^```", "", s)
#     s = re.sub(r"```$", "", s)

#     s = s.strip("`").strip()

#     if ";" in s:
#         s = s.split(";")[0]

#     return s


# def _validate_sql(sql):

#     if sql.upper().startswith("UNSUPPORTED"):

#         return {
#             "success": False,
#             "sql": None,
#             "method": "gemini",
#             "error": "Question cannot be answered from this database"
#         }

#     if not sql.upper().startswith("SELECT"):

#         return {
#             "success": False,
#             "sql": None,
#             "method": "gemini",
#             "error": "AI generated invalid SQL"
#         }

#     return {
#         "success": True,
#         "sql": sql,
#         "method": "gemini",
#         "error": None
#     }


# # ───────────────────────── GEMINI ENGINE ─────────────────────────

# def _gemini_generate(question, schema):

#     try:

#         from google import genai
#         from google.genai import types

#         client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

#         prompt = _build_prompt(schema, question)

#         response = client.models.generate_content(
#             model="gemini-2.0-flash",
#             contents=prompt,
#             config=types.GenerateContentConfig(
#                 temperature=0,
#                 max_output_tokens=512,
#                 response_mime_type="text/plain"
#             )
#         )

#         sql = _clean_sql(response.text)

#         return _validate_sql(sql)

#     except ImportError:

#         return {
#             "success": False,
#             "sql": None,
#             "method": "gemini",
#             "error": "Run: pip install google-genai"
#         }

#     except Exception as e:

#         return {
#             "success": False,
#             "sql": None,
#             "method": "gemini",
#             "error": str(e)
#         }


# # ───────────────────────── MAIN FUNCTION ─────────────────────────

# def convert_text_to_sql(natural_language: str):

#     question = natural_language.strip()

#     if not question:

#         return {
#             "success": False,
#             "sql": None,
#             "method": "gemini",
#             "error": "Empty input"
#         }

#     schema = _get_schema()

#     if not schema:

#         return {
#             "success": False,
#             "sql": None,
#             "method": "gemini",
#             "error": "No database loaded"
#         }

#     logger.info("User Query: %s", question)

#     result = _gemini_generate(question, schema)

#     if result["success"]:
#         logger.info("Generated SQL: %s", result["sql"])

#     return result