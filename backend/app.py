"""Minimal Flask API for CinéSearch (Assignment 2).

Stub endpoints so Streamlit can call a separate backend over HTTP.
Extend later with real recommendation logic (BigQuery ML, etc.).
"""
from flask import Flask, jsonify, request

app = Flask(__name__)


def _bad_request(error: str, message: str):
    """Consistent JSON error shape for 400 responses."""
    return jsonify(error=error, message=message), 400


@app.get("/health")
def health():
    """Liveness check for ops / quick manual tests."""
    return jsonify(status="ok")


@app.post("/recommend")
def recommend():
    """Stub recommender: expects {"selected_movies": ["Title1", ...]}."""
    # force=True: parse JSON even if client omits Content-Type: application/json
    data = request.get_json(force=True, silent=True)
    if data is None or not isinstance(data, dict):
        return _bad_request(
            "invalid_json",
            "Request body must be a valid JSON object.",
        )

    if "selected_movies" not in data:
        return _bad_request(
            "missing_field",
            "Field 'selected_movies' is required.",
        )

    selected = data["selected_movies"]
    if not isinstance(selected, list):
        return _bad_request(
            "invalid_type",
            "Field 'selected_movies' must be a list.",
        )

    if len(selected) == 0:
        return _bad_request(
            "empty_selection",
            "Field 'selected_movies' must not be empty.",
        )

    # Placeholder recommendations (real scoring comes later)
    return jsonify(
        input_count=len(selected),
        input_movies=selected,
        recommended_movies=[
            {"title": "The Matrix"},
            {"title": "Blade Runner 2049"},
        ],
    )


if __name__ == "__main__":
    # Bind all interfaces so Docker / LAN access works the same as localhost
    app.run(host="0.0.0.0", port=8080, debug=True)
