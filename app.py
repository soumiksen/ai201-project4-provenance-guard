"""
Provenance Guard — Flask app.

Milestone 3 scope: submission endpoint + first detection signal, wired to a
structured, append-only audit log.
"""

import os
import uuid
from datetime import datetime, timezone

from flask import Flask, request, jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from signals import signal_1_llm_assessment
from audit_log import append_entry, get_recent

app = Flask(__name__)
limiter = Limiter(get_remote_address, app=app, default_limits=["60 per minute"])

# Thresholds from planning.md Section 2 (Uncertainty Representation).
# Kept as named constants, not magic numbers scattered through the code.
LIKELY_HUMAN_MAX = 0.34
UNCERTAIN_MAX = 0.65


def label_from_score(score: float) -> str:
    """Maps a 0-1 score to one of the three attribution bands."""
    if score <= LIKELY_HUMAN_MAX:
        return "likely_human"
    if score <= UNCERTAIN_MAX:
        return "uncertain"
    return "likely_ai"


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

    signal_1 = signal_1_llm_assessment(text)
    llm_score = signal_1["llm_score"]

    # Milestone 3: confidence is a placeholder, equal to signal 1's score.
    # Milestone 4 replaces this with a true weighted combination of both
    # signals per planning.md Section 1.
    confidence = llm_score
    attribution = label_from_score(confidence)

    entry = {
        "content_id": content_id,
        "creator_id": creator_id,
        "timestamp": timestamp,
        "attribution": attribution,
        "confidence": confidence,
        "llm_score": llm_score,
        "signal_1_source": signal_1["source"],
        "status": "classified",
    }
    append_entry(entry)

    return jsonify({
        "content_id": content_id,
        "attribution": attribution,
        "confidence": confidence,
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
