"""
Provenance Guard — Flask app.

Milestone 4 scope: two detection signals combined into a single weighted
confidence score, wired to a structured, append-only audit log.
"""

import os
import uuid
from datetime import datetime, timezone

from flask import Flask, request, jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from signal_1_llm import signal_1_score
from signal_2_stylometric import signal_2_stylometric
from confidence import combine_signals
from audit_log import append_entry, get_recent

app = Flask(__name__)
limiter = Limiter(get_remote_address, app=app, default_limits=["60 per minute"])

@app.route("/submit", methods=["POST"])
@limiter.limit("20 per minute")
def submit():
    data = request.get_json(silent=True) or {}
    text = data.get("text")
    creator_id = data.get("creator_id")

    if not text or not isinstance(text, str) or not text.strip():
        return jsonify({"error": "'text' is required and must be a non-empty string"}), 400
    if not creator_id:
        return jsonify({"error": "'creator_id' is required"}), 400

    content_id = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc).isoformat()

    signal_1 = signal_1_score(text)
    signal_2 = signal_2_stylometric(text)

    combined = combine_signals(signal_1["llm_score"], signal_2["stylometric_score"])
    confidence = combined["confidence"]
    attribution = combined["attribution"]

    entry = {
        "content_id": content_id,
        "creator_id": creator_id,
        "timestamp": timestamp,
        "attribution": attribution,
        "confidence": confidence,
        "llm_score": signal_1["llm_score"],
        "signal_1_source": signal_1["source"],
        "stylometric_score": signal_2["stylometric_score"],
        "sentence_length_cv": signal_2["sentence_length_cv"],
        "type_token_ratio": signal_2["type_token_ratio"],
        "status": "classified",
    }
    append_entry(entry)

    return jsonify({
        "content_id": content_id,
        "attribution": attribution,
        "confidence": confidence,
        "signals": {
            "llm_score": signal_1["llm_score"],
            "stylometric_score": signal_2["stylometric_score"],
        },
    }), 201


@app.route("/log", methods=["GET"])
def log():
    limit = request.args.get("limit", default=20, type=int)
    return jsonify({"entries": get_recent(limit=limit)})


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1", port=port)
