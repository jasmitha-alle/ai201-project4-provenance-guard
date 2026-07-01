import uuid
import os
from dotenv import load_dotenv
load_dotenv()

from flask import Flask, request, jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import database as db
import detector

app = Flask(__name__)

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=[],
    storage_uri="memory://",
)


@app.route("/submit", methods=["POST"])
@limiter.limit("10 per minute")
def submit():
    data = request.get_json(silent=True)
    if not data or "text" not in data or "creator_id" not in data:
        return jsonify({"error": "Request body must include 'text' and 'creator_id'."}), 400

    text = data["text"].strip()
    creator_id = data["creator_id"].strip()

    if len(text) < 20:
        return jsonify({"error": "Text too short. Minimum 20 characters."}), 400

    content_id = str(uuid.uuid4())

    llm = detector.llm_signal(text)
    heuristic = detector.heuristic_signal(text)
    confidence = detector.compute_confidence(llm["score"], heuristic["score"])
    combined = round((llm["score"] * 0.60) + (heuristic["score"] * 0.40), 3)

    if confidence >= 0.80 and combined >= 0.50:
        attribution = "likely_ai"
    elif confidence >= 0.75 and combined < 0.50:
        attribution = "likely_human"
    else:
        attribution = "uncertain"

    db.write_entry(
        content_id=content_id,
        creator_id=creator_id,
        attribution=attribution,
        confidence=confidence,
        llm_score=llm["score"],
        extra={"heuristic_score": heuristic["score"], "heuristic_details": heuristic["details"]},
    )

    return jsonify({
        "content_id": content_id,
        "attribution": attribution,
        "confidence": confidence,
        "label": detector.build_label(attribution, confidence),
        "signals": {
            "llm_score": llm["score"],
            "llm_reasoning": llm["reasoning"],
            "heuristic_score": heuristic["score"],
            "heuristic_details": heuristic["details"],
        },
    }), 201


@app.route("/appeal", methods=["POST"])
def appeal():
    data = request.get_json(silent=True)
    if not data or "content_id" not in data or "creator_reasoning" not in data:
        return jsonify({"error": "Request body must include 'content_id' and 'creator_reasoning'."}), 400

    content_id = data["content_id"].strip()
    reasoning = data["creator_reasoning"].strip()

    if len(reasoning) < 10:
        return jsonify({"error": "creator_reasoning must be at least 10 characters."}), 400

    entry = db.get_entry(content_id)
    if not entry:
        return jsonify({"error": "content_id not found."}), 404

    if entry["status"] == "under_review":
        return jsonify({"error": "An appeal for this content is already under review."}), 409

    db.update_status(content_id, "under_review", extra={"appeal_reasoning": reasoning})

    return jsonify({
        "content_id": content_id,
        "status": "under_review",
        "message": "Your appeal has been received. A human reviewer will assess the original classification.",
    }), 202


@app.route("/log", methods=["GET"])
def log():
    limit = min(int(request.args.get("limit", 50)), 200)
    return jsonify({"entries": db.get_log(limit)})


@app.route("/", methods=["GET"])
def index():
    return jsonify({"service": "Provenance Guard", "version": "0.3.0"})


@app.errorhandler(429)
def rate_limit_exceeded(e):
    return jsonify({"error": "Rate limit exceeded. Maximum 10 submissions per minute."}), 429


if __name__ == "__main__":
    db.init_db()
    app.run(debug=True, port=int(os.environ.get("PORT", 5000)))