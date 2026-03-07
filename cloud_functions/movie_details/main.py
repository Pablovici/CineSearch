"""movie_details — Cloud Function
Fetches enriched movie information (poster, overview, cast, runtime, budget…)
from The Movie Database (TMDB) API.
Optionally resolves a BigQuery movieId → tmdbId if only movieId is provided.
"""
import os
from typing import Optional

import functions_framework
import requests
from google.cloud import bigquery

# ── BigQuery config ───────────────────────────────────────────────────────────
_PROJECT = "ferrous-store-487916-f8"
_DATASET = "ASSIGNEMENT1"
_TABLE_MOVIES = f"`{_PROJECT}.{_DATASET}.movies`"

# ── TMDB config ───────────────────────────────────────────────────────────────
# The API key is read from the environment so it is not hard-coded in production.
# Set it with: gcloud run services update movie-details --set-env-vars TMDB_API_KEY=<key>
_TMDB_API_KEY: str = os.environ.get("TMDB_API_KEY", "02e7692e7df463d1691e91f494f1c19b")
_TMDB_BASE: str = "https://api.themoviedb.org/3"
_TMDB_IMG_BASE: str = "https://image.tmdb.org/t/p/w500"

_CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
}


def _resolve_tmdb_id(client: bigquery.Client, movie_id: int) -> Optional[int]:
    """Look up tmdbId in BigQuery given a MovieLens movieId."""
    sql = f"""
    SELECT tmdbId
    FROM {_TABLE_MOVIES}
    WHERE movieId = @movie_id
    LIMIT 1
    """
    print("\n── SQL EXECUTED (tmdbId lookup) ──")
    print(sql)
    print(f"  PARAM movie_id = {movie_id}\n")

    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("movie_id", "INT64", movie_id)
        ]
    )
    rows = list(client.query(sql, job_config=job_config).result())
    if rows and rows[0].get("tmdbId") is not None:
        return int(rows[0]["tmdbId"])
    return None


@functions_framework.http
def movie_details(request):
    """HTTP Cloud Function — fetch enriched TMDB details for a movie.

    Query parameters:
        tmdb_id  (int) — TMDB movie ID  [preferred]
        movie_id (int) — MovieLens movieId; tmdbId is resolved via BigQuery
    """
    if request.method == "OPTIONS":
        return ("", 204, _CORS_HEADERS)

    # ── Resolve TMDB ID ───────────────────────────────────────────────────────
    tmdb_id_raw = request.args.get("tmdb_id", "").strip()
    movie_id_raw = request.args.get("movie_id", "").strip()

    tmdb_id: Optional[int] = None
    try:
        if tmdb_id_raw:
            tmdb_id = int(tmdb_id_raw)
        elif movie_id_raw:
            client = bigquery.Client()
            tmdb_id = _resolve_tmdb_id(client, int(movie_id_raw))
    except (ValueError, TypeError) as exc:
        return ({"error": f"Invalid ID parameter: {exc}"}, 400, _CORS_HEADERS)

    if not tmdb_id:
        return (
            {"error": "Provide 'tmdb_id' or 'movie_id' as a query parameter."},
            400,
            _CORS_HEADERS,
        )

    # ── Call TMDB API ─────────────────────────────────────────────────────────
    try:
        resp = requests.get(
            f"{_TMDB_BASE}/movie/{tmdb_id}",
            params={
                "api_key": _TMDB_API_KEY,
                "language": "en-US",
                "append_to_response": "credits",
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.exceptions.HTTPError as exc:
        return ({"error": f"TMDB HTTP error: {exc}"}, 502, _CORS_HEADERS)
    except requests.exceptions.RequestException as exc:
        return ({"error": f"TMDB request failed: {exc}"}, 502, _CORS_HEADERS)

    # ── Shape the response ────────────────────────────────────────────────────
    poster_path = data.get("poster_path")
    cast = [
        {"name": c.get("name"), "character": c.get("character")}
        for c in data.get("credits", {}).get("cast", [])[:10]
    ]

    print(f"\n── TMDB RESPONSE (tmdb_id={tmdb_id}) ──")
    print(f"  title   = {data.get('title')}")
    print(f"  rating  = {data.get('vote_average')} ({data.get('vote_count')} votes)")
    print(f"  runtime = {data.get('runtime')} min\n")

    return (
        {
            "tmdb_id": tmdb_id,
            "title": data.get("title"),
            "tagline": data.get("tagline"),
            "overview": data.get("overview"),
            "release_date": data.get("release_date"),
            "runtime": data.get("runtime"),
            "vote_average": data.get("vote_average"),
            "vote_count": data.get("vote_count"),
            "original_language": data.get("original_language"),
            "budget": data.get("budget"),
            "revenue": data.get("revenue"),
            "genres": [g["name"] for g in data.get("genres", [])],
            "cast": cast,
            "poster_url": f"{_TMDB_IMG_BASE}{poster_path}" if poster_path else None,
        },
        200,
        _CORS_HEADERS,
    )
