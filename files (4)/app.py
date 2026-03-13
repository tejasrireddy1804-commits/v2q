# """
# app.py - Voice2SQL with User Database Upload
# Run: python app.py
# Then open: http://127.0.0.1:5000
# """

# import sys
# import os
# import logging

# BASEDIR = os.path.dirname(os.path.abspath(__file__))
# sys.path.insert(0, BASEDIR)

# from flask import Flask, jsonify, Response
# from flask_cors import CORS

# from voice_routes import voice_bp
# from sql_routes import sql_bp
# from upload_routes import upload_bp

# logging.basicConfig(
#     level=logging.INFO,
#     format="%(asctime)s  %(levelname)-8s  %(name)s - %(message)s",
#     datefmt="%Y-%m-%d %H:%M:%S",
# )
# logger = logging.getLogger(__name__)

# # Folder where uploaded databases are stored
# UPLOAD_FOLDER = os.path.join(BASEDIR, "uploads")
# os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# def create_app():
#     app = Flask(__name__)
#     app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
#     app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50MB max upload
#     CORS(app)

#     app.register_blueprint(voice_bp)
#     app.register_blueprint(sql_bp)
#     app.register_blueprint(upload_bp)

#     @app.route("/")
#     def index():
#         html_path = os.path.join(BASEDIR, "index.html")
#         try:
#             with open(html_path, "r", encoding="utf-8") as f:
#                 return Response(f.read(), mimetype="text/html")
#         except Exception as e:
#             return Response("<h1>Error loading index.html: {}</h1>".format(e), mimetype="text/html")

#     @app.route("/health", methods=["GET"])
#     def health():
#         ai_backend = (
#             "gemini" if os.getenv("GEMINI_API_KEY") else
#             "openai" if os.getenv("OPENAI_API_KEY") else
#             "rule-based (no API key needed)"
#         )
#         return jsonify({"status": "ok", "service": "Voice2SQL", "ai_backend": ai_backend}), 200

#     @app.errorhandler(404)
#     def not_found(e):
#         return jsonify({"success": False, "error": "Endpoint not found."}), 404

#     @app.errorhandler(413)
#     def too_large(e):
#         return jsonify({"success": False, "error": "File too large. Max 50MB."}), 413

#     @app.errorhandler(500)
#     def internal_error(e):
#         return jsonify({"success": False, "error": "Internal server error."}), 500

#     return app


# if __name__ == "__main__":
#     app  = create_app()
#     port = int(os.getenv("FLASK_PORT", 5000))
#     logger.info("=" * 50)
#     logger.info("Voice2SQL is running!")
#     logger.info("Open: http://127.0.0.1:%d", port)
#     logger.info("=" * 50)
#     app.run(host="0.0.0.0", port=port, debug=False)



"""
app.py - Voice2SQL with User Database Upload
Run:   python app.py
Open:  http://127.0.0.1:5000

For 100% accurate SQL:
  1. Get free Gemini key: https://aistudio.google.com/apikey
  2. pip install google-generativeai
  3. set GEMINI_API_KEY=your_key_here
  4. python app.py
"""
import sys, os, logging
BASEDIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASEDIR)

from flask import Flask, jsonify, Response
from flask_cors import CORS
from voice_routes  import voice_bp
from sql_routes    import sql_bp
from upload_routes import upload_bp

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S")
logger = logging.getLogger(__name__)

UPLOAD_FOLDER = os.path.join(BASEDIR, "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


def create_app():
    app = Flask(__name__)
    app.config["UPLOAD_FOLDER"]      = UPLOAD_FOLDER
    app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024
    CORS(app)

    app.register_blueprint(voice_bp)
    app.register_blueprint(sql_bp)
    app.register_blueprint(upload_bp)

    @app.route("/")
    def index():
        html_path = os.path.join(BASEDIR, "index.html")
        try:
            with open(html_path, "r", encoding="utf-8") as f:
                return Response(f.read(), mimetype="text/html")
        except Exception as e:
            return Response("<h1>Error: {}</h1>".format(e), mimetype="text/html")

    @app.route("/health", methods=["GET"])
    def health():
        if os.getenv("GEMINI_API_KEY"):
            ai = "gemini"
        elif os.getenv("OPENAI_API_KEY"):
            ai = "openai"
        else:
            ai = "rule-based"
        return jsonify({"status": "ok", "service": "Voice2SQL", "ai_backend": ai}), 200

    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"success": False, "error": "Endpoint not found."}), 404

    @app.errorhandler(413)
    def too_large(e):
        return jsonify({"success": False, "error": "File too large. Max 50MB."}), 413

    @app.errorhandler(500)
    def internal_error(e):
        return jsonify({"success": False, "error": "Internal server error."}), 500

    return app


if __name__ == "__main__":
    app  = create_app()
    port = int(os.getenv("FLASK_PORT", 5000))

    if os.getenv("GEMINI_API_KEY"):
        ai_status = "Gemini AI (100% accurate)"
    elif os.getenv("OPENAI_API_KEY"):
        ai_status = "OpenAI GPT"
    else:
        ai_status = "Rule-based (limited accuracy) — set GEMINI_API_KEY for 100% accuracy"

    logger.info("=" * 60)
    logger.info("Voice2SQL is running!")
    logger.info("Open:       http://127.0.0.1:%d", port)
    logger.info("AI Engine:  %s", ai_status)
    logger.info("=" * 60)
    app.run(host="0.0.0.0", port=port, debug=False)