"""Flask API for CinéSearch (Assignment 2).

Routes:
  GET  /health        — liveness check
  GET  /autocomplete  — Elasticsearch title suggestions (?q=&limit=)
  POST /recommend     — BigQuery ML recommendations (selected_movie_ids)

POST /recommend modes:
  empty selected_movie_ids  → popular movies (BigQuery aggregate)
  non-empty                 → similar users (ASSIGNEMENT2.ratings + rating_im)
                              then ML.RECOMMEND (first_MF_model),
                              with popular fallback if no similar users found.

All BigQuery data comes from ASSIGNEMENT2:
  - movies   : movieId, title, genres, …
  - ratings  : userId, movieId, rating_im
  - links    : movieId, tmdbId
"""
from __future__ import annotations

import os
from decimal import Decimal

from flask import Flask, jsonify, request
from google.auth.exceptions import DefaultCredentialsError
from google.cloud import bigquery
from google.cloud.exceptions import GoogleCloudError
from google.api_core.exceptions import GoogleAPICallError

import es_service

app = Flask(__name__)


@app.after_request
def _add_cors(response):
    """Allow the Streamlit browser JS to call the backend directly (e.g. autocomplete)."""
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
# BigQuery (all tables in ASSIGNEMENT2):
#   PROJECT_ID / GOOGLE_CLOUD_PROJECT
#   DATASET_ID        default: ASSIGNEMENT2
#   MOVIES_TABLE      default: movies
#   RATINGS_TABLE     default: ratings   (column: rating_im)
#   LINKS_TABLE       default: links     (column: tmdbId)
#
# BigQuery ML:
#   BQML_MODEL_NAME             default: first_MF_model
#   SIMILAR_USER_MIN_RATING_IM  default: 3.0
#   SIMILAR_USERS_TOP_K         default: 10
#
# Elasticsearch (see es_service.py):
#   ES_ENDPOINT   — Elastic Cloud cluster URL
#   ES_API_KEY    — Elastic Cloud API key


def _first_env(*names: str) -> str | None:
    for name in names:
        val = os.environ.get(name)
        if val is not None and str(val).strip() != "":
            return val.strip()
    return None


PROJECT_ID    = _first_env("PROJECT_ID", "GOOGLE_CLOUD_PROJECT") or "ferrous-store-487916-f8"
DATASET_ID    = _first_env("DATASET_ID", "BQ_DATASET")           or "ASSIGNEMENT2"
MOVIES_TABLE  = _first_env("MOVIES_TABLE")                        or "movies"
RATINGS_TABLE = _first_env("RATINGS_TABLE")                       or "ratings"
LINKS_TABLE   = _first_env("LINKS_TABLE")                         or "links"

BQML_MODEL_NAME = _first_env("BQML_MODEL_NAME") or "first_MF_model"

_sim_min_raw = _first_env("SIMILAR_USER_MIN_RATING_IM")
SIMILAR_USER_MIN_RATING_IM = float(_sim_min_raw) if _sim_min_raw is not None else 0.7

_sk_top = _first_env("SIMILAR_USERS_TOP_K")
SIMILAR_USERS_TOP_K = int(_sk_top) if _sk_top is not None else 10

# Lazy client — fails only on first query, not at import time.
_bq_client: bigquery.Client | None = None


def _get_bq_client() -> bigquery.Client:
    global _bq_client
    if _bq_client is None:
        _bq_client = bigquery.Client(project=PROJECT_ID)
    return _bq_client


def _t(table_name: str) -> str:
    """Return fully-qualified `project.dataset.table` for use in SQL."""
    return f"`{PROJECT_ID}.{DATASET_ID}.{table_name}`"


def _model() -> str:
    """Fully-qualified BigQuery ML model reference."""
    return f"`{PROJECT_ID}.{DATASET_ID}.{BQML_MODEL_NAME}`"


def run_bigquery_to_dicts(
    sql: str,
    job_config: bigquery.QueryJobConfig | None = None,
) -> list[dict]:
    """Execute SQL and return rows as plain JSON-serializable dicts."""
    print(f"\n[SQL] Executing query:\n{sql.strip()}\n")

    client = _get_bq_client()
    job = client.query(sql, job_config=job_config)
    rows = job.result()

    out: list[dict] = []
    for row in rows:
        row_dict = dict(row.items())
        cleaned: dict = {}
        for key, val in row_dict.items():
            if isinstance(val, Decimal):
                cleaned[key] = float(val)
            elif hasattr(val, "item"):  # numpy scalar
                cleaned[key] = val.item()
            else:
                cleaned[key] = val
        out.append(cleaned)

    print(f"[SQL] Rows returned: {len(out)}")
    for i, row in enumerate(out[:3]):
        print(f"[SQL]   Row {i}: {row}")
    if len(out) > 3:
        print(f"[SQL]   ... ({len(out) - 3} more rows)")
    print()

    return out


def _bad_request(error: str, message: str):
    return jsonify(error=error, message=message), 400


# ---------------------------------------------------------------------------
# Input parsing
# ---------------------------------------------------------------------------

def _coerce_single_movie_id(value) -> int | None:
    """Return a non-negative int movie id, or None if value cannot be coerced."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, float):
        if not value.is_integer():
            return None
        iv = int(value)
        return iv if iv >= 0 else None
    if isinstance(value, str):
        s = value.strip()
        if s == "":
            return None
        try:
            fv = float(s)
        except ValueError:
            return None
        if not fv.is_integer():
            return None
        iv = int(fv)
        return iv if iv >= 0 else None
    return None


def _parse_selected_movie_ids(raw: list) -> tuple[list[int] | None, tuple[str, str] | None]:
    """Coerce JSON list to distinct non-negative ints. Returns (ids, None) or (None, (err, msg))."""
    out: list[int] = []
    seen: set[int] = set()
    for idx, item in enumerate(raw):
        mid = _coerce_single_movie_id(item)
        if mid is None:
            return None, (
                "invalid_movie_id",
                f"Item at index {idx} must be a non-negative integer (or numeric string), "
                f"got {type(item).__name__!r}.",
            )
        if mid not in seen:
            seen.add(mid)
            out.append(mid)
    return out, None


# ---------------------------------------------------------------------------
# SQL — Popular movies (ASSIGNEMENT2.movies + ratings + links)
# ---------------------------------------------------------------------------
# Both templates join links so that tmdbId is always present in the response.
# The EXCLUDING variant omits seed movies so popular fallback never repeats
# the user's own selection.

_SQL_POPULAR = """
SELECT
  m.movieId         AS movieId,
  m.title           AS title,
  AVG(r.rating_im)  AS avg_rating,
  COUNT(*)          AS rating_count,
  l.tmdbId          AS tmdbId
FROM {movies} AS m
INNER JOIN {ratings} AS r ON m.movieId = r.movieId
LEFT JOIN  {links}   AS l ON m.movieId = l.movieId
WHERE m.title IS NOT NULL
  AND TRIM(CAST(m.title AS STRING)) != ''
GROUP BY m.movieId, m.title, l.tmdbId
ORDER BY rating_count DESC, avg_rating DESC
LIMIT 10
"""

_SQL_POPULAR_EXCLUDING = """
SELECT
  m.movieId         AS movieId,
  m.title           AS title,
  AVG(r.rating_im)  AS avg_rating,
  COUNT(*)          AS rating_count,
  l.tmdbId          AS tmdbId
FROM {movies} AS m
INNER JOIN {ratings} AS r ON m.movieId = r.movieId
LEFT JOIN  {links}   AS l ON m.movieId = l.movieId
WHERE m.title IS NOT NULL
  AND TRIM(CAST(m.title AS STRING)) != ''
  AND m.movieId NOT IN UNNEST(@exclude_movie_ids)
GROUP BY m.movieId, m.title, l.tmdbId
ORDER BY rating_count DESC, avg_rating DESC
LIMIT 10
"""


def _inject_tables(template: str) -> str:
    """Replace {movies}/{ratings}/{links} placeholders with fully-qualified table names."""
    return template.format(
        movies=_t(MOVIES_TABLE),
        ratings=_t(RATINGS_TABLE),
        links=_t(LINKS_TABLE),
    )


def fetch_popular_movies(exclude_movie_ids: list[int] | None = None) -> list[dict]:
    """
    Top-10 popular movies from ASSIGNEMENT2, ranked by rating_count then avg(rating_im).
    When exclude_movie_ids is provided, those movies are omitted (used as popular fallback).
    """
    excl = exclude_movie_ids or []
    if not excl:
        print("[BQ] Fetching popular movies...")
        return run_bigquery_to_dicts(_inject_tables(_SQL_POPULAR))

    print(f"[BQ] Fetching popular movies (excluding {excl})...")
    sql = _inject_tables(_SQL_POPULAR_EXCLUDING)
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ArrayQueryParameter("exclude_movie_ids", "INT64", excl),
        ],
    )
    return run_bigquery_to_dicts(sql, job_config)


# ---------------------------------------------------------------------------
# SQL — Similar users (ASSIGNEMENT2.ratings, rating_im threshold)
# ---------------------------------------------------------------------------

def _fetch_similar_user_ids(selected_movie_ids: list[int]) -> list[int]:
    """
    Find users who rated the seed movies highly (rating_im >= threshold).
    Ranked by how many of the seed movies they rated.
    """
    if not selected_movie_ids:
        return []

    print(f"[BQ] Finding similar users for movie_ids: {selected_movie_ids}...")

    sql = """
    WITH overlap AS (
      SELECT
        r.userId        AS userId,
        COUNT(DISTINCT r.movieId) AS overlap_count
      FROM {ratings} AS r
      WHERE r.movieId IN UNNEST(@selected_movie_ids)
        AND r.rating_im >= @min_rating_im
      GROUP BY r.userId
    )
    SELECT userId
    FROM overlap
    ORDER BY overlap_count DESC, userId ASC
    LIMIT @top_k
    """.format(ratings=_t(RATINGS_TABLE))

    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ArrayQueryParameter("selected_movie_ids", "INT64", selected_movie_ids),
            bigquery.ScalarQueryParameter("min_rating_im", "FLOAT64", SIMILAR_USER_MIN_RATING_IM),
            bigquery.ScalarQueryParameter("top_k", "INT64", SIMILAR_USERS_TOP_K),
        ],
    )
    rows = run_bigquery_to_dicts(sql, job_config)
    return [int(row["userId"]) for row in rows]


# ---------------------------------------------------------------------------
# SQL — ML.RECOMMEND (ASSIGNEMENT2.first_MF_model)
# ---------------------------------------------------------------------------

def _fetch_similar_users_bqml_recommendations(
    selected_movie_ids: list[int],
    similar_user_ids: list[int],
) -> list[dict]:
    """
    Run ML.RECOMMEND for all similar users, rank by predicted_rating_im_confidence.

    Strategy:
      1. For each user, keep only their top-20 recommendations by confidence score,
         excluding seed movies — this prevents one prolific user from skewing averages.
      2. Aggregate across users: avg confidence + how many users recommended it.
      3. Sort by avg_confidence (the actual ML signal), then user_count as tiebreaker.
    """
    print(f"[BQ] Running ML.RECOMMEND for {len(similar_user_ids)} similar users...")

    sql = """
    WITH ranked AS (
      SELECT
        rec.movieId                        AS movieId,
        rec.predicted_rating_im_confidence AS confidence,
        ROW_NUMBER() OVER (
          PARTITION BY rec.userId
          ORDER BY rec.predicted_rating_im_confidence DESC
        ) AS rn
      FROM ML.RECOMMEND(
        MODEL {model},
        (SELECT user_id AS userId FROM UNNEST(@similar_user_ids) AS user_id)
      ) AS rec
      WHERE rec.movieId NOT IN UNNEST(@selected_movie_ids)
    ),
    aggregated AS (
      SELECT
        movieId,
        AVG(confidence) AS avg_confidence,
        COUNT(*)        AS user_count
      FROM ranked
      WHERE rn <= 20
      GROUP BY movieId
    )
    SELECT
      a.movieId        AS movieId,
      m.title          AS title,
      a.avg_confidence AS avg_confidence,
      a.user_count     AS user_count,
      l.tmdbId         AS tmdbId
    FROM aggregated AS a
    INNER JOIN {movies} AS m ON a.movieId = m.movieId
    LEFT JOIN  {links}  AS l ON a.movieId = l.movieId
    ORDER BY a.avg_confidence DESC, a.user_count DESC
    LIMIT 10
    """.format(
        model=_model(),
        movies=_t(MOVIES_TABLE),
        links=_t(LINKS_TABLE),
    )

    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ArrayQueryParameter("similar_user_ids", "INT64", similar_user_ids),
            bigquery.ArrayQueryParameter("selected_movie_ids", "INT64", selected_movie_ids),
        ],
    )
    return run_bigquery_to_dicts(sql, job_config)


# ---------------------------------------------------------------------------
# Cross-dataset filter — catalogue (ASSIGNEMENT1) → ML dataset (ASSIGNEMENT2)
# ---------------------------------------------------------------------------

def _filter_ids_in_ml_dataset(movie_ids: list[int]) -> list[int]:
    """Keep only the movieIds that exist in ASSIGNEMENT2.ratings.

    The user selects movies from the large catalogue (ASSIGNEMENT1, indexed
    in Elasticsearch).  The ML model only knows movieIds present in
    ASSIGNEMENT2.ratings.  This function filters so that downstream queries
    (similar users, ML.RECOMMEND) only receive valid movie IDs.
    """
    if not movie_ids:
        return []

    print(f"[BQ] Filtering IDs in ML dataset: {movie_ids}...")

    sql = """
    SELECT DISTINCT movieId
    FROM {ratings}
    WHERE movieId IN UNNEST(@candidate_ids)
    """.format(ratings=_t(RATINGS_TABLE))

    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ArrayQueryParameter("candidate_ids", "INT64", movie_ids),
        ],
    )
    rows = run_bigquery_to_dicts(sql, job_config)
    return [int(row["movieId"]) for row in rows]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return jsonify(status="ok")


@app.get("/movies/titles")
def movies_titles():
    """GET /movies/titles?limit=<n>

    Returns all movie titles from Elasticsearch for multiselect pre-loading.
    Falls back to an empty list if ES is unavailable.
    """
    limit = min(int(request.args.get("limit", 30_000)), 30_000)
    titles = es_service.fetch_all_titles(limit=limit)
    return jsonify(movies=titles)


@app.get("/autocomplete")
def autocomplete():
    """GET /autocomplete?q=<prefix>&limit=<n>

    Returns Elasticsearch title suggestions.
    Falls back to an empty list if ES is unavailable (never crashes the app).
    """
    query = request.args.get("q", "").strip()
    limit = min(int(request.args.get("limit", 8)), 20)
    suggestions = es_service.autocomplete_titles(query, limit=limit)
    return jsonify(suggestions=suggestions)


@app.post("/recommend")
def recommend():
    """
    POST /recommend
    Body: {"selected_movie_ids": [<int>, …]}

    Modes:
      popular_top                      — empty list → top-10 popular movies
      popular_fallback_no_similar_users — no similar users found → popular excluding seeds
      similar_users_bqml               — ML.RECOMMEND aggregated over similar users

    All branches return recommended_movies with: movieId, title, tmdbId
    plus mode-specific fields (avg_rating/rating_count or avg_confidence/user_count).
    """
    data = request.get_json(force=True, silent=True)
    if data is None or not isinstance(data, dict):
        return _bad_request(
            "invalid_json",
            "Request body must be a valid JSON object.",
        )

    if "selected_movie_ids" not in data:
        return _bad_request(
            "missing_field",
            "Field 'selected_movie_ids' is required (list of integer movie ids; may be empty).",
        )

    raw_ids = data["selected_movie_ids"]
    if not isinstance(raw_ids, list):
        return _bad_request(
            "invalid_type",
            "Field 'selected_movie_ids' must be a JSON array.",
        )

    movie_ids, parse_err = _parse_selected_movie_ids(raw_ids)
    if parse_err is not None:
        err, msg = parse_err
        return _bad_request(err, msg)

    try:
        # ── Mode 1: no seeds → plain popularity ranking ───────────────────────
        if len(movie_ids) == 0:
            recommended = fetch_popular_movies()
            return jsonify(
                input_count=0,
                input_movie_ids=[],
                recommendation_mode="popular_top",
                recommended_movies=recommended,
            )

        # ── Cross-dataset filter ──────────────────────────────────────────────
        # The user selects movies from the large catalogue (ASSIGNEMENT1).
        # The ML model only knows movies from the small dataset (ASSIGNEMENT2).
        # Keep only movieIds that exist in ASSIGNEMENT2.ratings.
        ml_movie_ids = _filter_ids_in_ml_dataset(movie_ids)

        if not ml_movie_ids:
            # None of the selected movies are in the ML dataset → popular fallback
            recommended = fetch_popular_movies(exclude_movie_ids=movie_ids)
            return jsonify(
                input_count=len(movie_ids),
                input_movie_ids=movie_ids,
                ml_filtered_count=0,
                recommendation_mode="popular_fallback_no_similar_users",
                recommended_movies=recommended,
            )

        # ── Mode 2 / 3: seeds that exist in ML dataset ───────────────────────
        similar_user_ids = _fetch_similar_user_ids(ml_movie_ids)

        if not similar_user_ids:
            # No similar users — fall back to popularity, excluding the seeds.
            recommended = fetch_popular_movies(exclude_movie_ids=movie_ids)
            return jsonify(
                input_count=len(movie_ids),
                input_movie_ids=movie_ids,
                ml_filtered_count=len(ml_movie_ids),
                similar_user_count=0,
                recommendation_mode="popular_fallback_no_similar_users",
                recommended_movies=recommended,
            )

        # ── Mode 3: ML.RECOMMEND via similar users ────────────────────────────
        recommended = _fetch_similar_users_bqml_recommendations(ml_movie_ids, similar_user_ids)
        return jsonify(
            input_count=len(movie_ids),
            input_movie_ids=movie_ids,
            ml_filtered_count=len(ml_movie_ids),
            similar_user_count=len(similar_user_ids),
            recommendation_mode="similar_users_bqml",
            recommended_movies=recommended,
        )

    except (GoogleAPICallError, GoogleCloudError, DefaultCredentialsError) as e:
        return (
            jsonify(
                error="bigquery_error",
                message="BigQuery request failed (check credentials, project, and table names).",
                details=str(e),
            ),
            502,
        )
    except Exception as e:  # noqa: BLE001
        return (
            jsonify(
                error="recommendation_error",
                message="Could not compute recommendations.",
                details=str(e),
            ),
            500,
        )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)
