"""voice_routes.py - POST /voice-input"""

from flask import Blueprint, jsonify, request
from speech_to_text import capture_voice_input

voice_bp = Blueprint("voice", __name__)

@voice_bp.route("/voice-input", methods=["POST"])
def voice_input():
    body              = request.get_json(silent=True) or {}
    timeout           = int(body.get("timeout", 5))
    phrase_time_limit = int(body.get("phrase_time_limit", 10))
    result = capture_voice_input(timeout=timeout, phrase_time_limit=phrase_time_limit)
    if result["success"]:
        return jsonify({"success": True, "text": result["text"], "message": "Voice captured."}), 200
    return jsonify({"success": False, "error": result["error"]}), 400
