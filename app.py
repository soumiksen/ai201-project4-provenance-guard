"""
Provenance Guard — Flask app.

Milestone 5 scope: the full production layer on top of the Milestone 4
detection pipeline - transparency labels, an appeals workflow, rate
limiting, and a complete audit log.
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
from labels import generate_label
from audit_log import append_entry, update_entry, get_recent, get_by_content_id

app = Flask(__name__)

# Rate limiting reasoning (documented in full in README.md):
# - /submit: "10 per minute; 100 per day" - generous enough for a writer
#   submitting several drafts in a working session (1 every ~6 seconds),
#   while a flooding script hits the ceiling almost immediately.
# - default_limits left empty; each route sets its own explicit limit so
#   the reasoning per-route is visible at the decorator, not buried in a
#   global default.
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=[],
    storage_uri="memory://",
)


@app.route("/submit", methods=["POST"])
@limiter.limit("10 per minute;100 per day")
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
    label = generate_label(confidence)

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
        "label_headline": label["headline"],
        "status": "classified",
        "appeal_filed": False,
    }
    append_entry(entry)

    return jsonify({
        "content_id": content_id,
        "attribution": attribution,
        "confidence": confidence,
        "label": {
            "headline": label["headline"],
            "subtext": label["subtext"],
        },
        "signals": {
            "llm_score": signal_1["llm_score"],
            "stylometric_score": signal_2["stylometric_score"],
        },
    }), 201


@app.route("/appeal", methods=["POST"])
@limiter.limit("10 per minute")
def appeal():
    data = request.get_json(silent=True) or {}
    content_id = data.get("content_id")
    creator_reasoning = data.get("creator_reasoning")

    if not content_id:
        return jsonify({"error": "'content_id' is required"}), 400
    if not creator_reasoning or not isinstance(creator_reasoning, str) or not creator_reasoning.strip():
        return jsonify({"error": "'creator_reasoning' is required and must be a non-empty string"}), 400

    existing = get_by_content_id(content_id)
    if not existing:
        return jsonify({"error": f"no submission found with content_id '{content_id}'"}), 404

    appeal_timestamp = datetime.now(timezone.utc).isoformat()
    updated = update_entry(content_id, {
        "status": "under_review",
        "appeal_filed": True,
        "appeal_reasoning": creator_reasoning,
        "appeal_timestamp": appeal_timestamp,
    })

    return jsonify({
        "content_id": content_id,
        "status": updated["status"],
        "message": "Appeal received and logged. This submission is now under review.",
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
