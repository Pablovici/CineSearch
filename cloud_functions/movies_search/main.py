"""movies_search — Cloud Function
Advanced movie search with language, genre, average-rating, and release-year filters.
Executes a JOIN + GROUP BY + HAVING AVG(rating) query on BigQuery.
All executed SQL is printed to stdout (visible in Cloud Run logs).
"""
from typing import Optional

import functions_framework
from google.cloud import bigquery

# ── BigQuery config ───────────────────────────────────────────────────────────
_PROJECT = "ferrous-store-487916-f8"
_DATASET = "ASSIGNEMENT1"
_TABLE_MOVIES = f"`{_PROJECT}.{_DATASET}.movies`"
_TABLE_RATINGS = f"`{_PROJECT}.{_DATASET}.rating`"

_CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
}


def _genre_filter_sql(field: str = "m.genres") -> str:
    """
    Build a robust WHERE clause for pipe-separated genre strings
    e.g. 'Action|Comedy|Drama'.
    Works for exact match, prefix, middle, and suffix positions.
    """
    return f"""
      AND (
        @genre = ''
        OR LOWER({field}) = @genre
        OR LOWER({field}) LIKE CONCAT(@genre, '|%')
        OR LOWER({field}) LIKE CONCAT('%|', @genre, '|%')
        OR LOWER({field}) LIKE CONCAT('%|', @genre)
      )
    """


@functions_framework.http
def movies_search(request):
    """HTTP Cloud Function — advanced movie search with JOIN + aggregation."""
    if request.method == "OPTIONS":
        return ("", 204, _CORS_HEADERS)

    # ── Parse query parameters ────────────────────────────────────────────────
    q = request.args.get("q", "").strip()
    language = request.args.get("language", "").strip().lower()
    genre = request.args.get("genre", "").strip().lower()
    limit = min(int(request.args.get("limit", "20")), 100)

    min_rating_raw = request.args.get("min_rating", "").strip()
    min_rating: Optional[float] = float(min_rating_raw) if min_rating_raw else None

    min_year_raw = request.args.get("min_year", "").strip()
    min_year: Optional[int] = int(min_year_raw) if min_year_raw else None

    try:
        client = bigquery.Client()
    except Exception as exc:
        return ({"error": f"BigQuery client init failed: {exc}"}, 503, _CORS_HEADERS)

    sql = f"""
    SELECT
        m.movieId,
        m.title,
        m.tmdbId,
        m.language,
        m.genres,
        m.release_year,
        m.country,
        ROUND(AVG(r.rating), 2) AS avg_rating,
        COUNT(r.rating)         AS rating_count
    FROM {_TABLE_MOVIES} m
    JOIN {_TABLE_RATINGS} r ON m.movieId = r.movieId
    WHERE
        LOWER(m.title) LIKE CONCAT('%', LOWER(@q), '%')
        AND (@language = '' OR LOWER(m.language) = @language)
        {_genre_filter_sql("m.genres")}
        AND (@min_year IS NULL OR m.release_year >= @min_year)
    GROUP BY
        m.movieId, m.title, m.tmdbId, m.language, m.genres, m.release_year, m.country
    HAVING
        (@min_rating IS NULL OR AVG(r.rating) >= @min_rating)
    ORDER BY avg_rating DESC, rating_count DESC
    LIMIT @limit
    """

    print("\n── SQL EXECUTED (movies_search) ──")
    print(sql)
    print(f"  PARAM q          = '{q}'")
    print(f"  PARAM language   = '{language or '(all)'}'")
    print(f"  PARAM genre      = '{genre or '(all)'}'")
    print(f"  PARAM min_year   = {min_year}")
    print(f"  PARAM min_rating = {min_rating}")
    print(f"  PARAM limit      = {limit}\n")

    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("q", "STRING", q),
            bigquery.ScalarQueryParameter("language", "STRING", language),
            bigquery.ScalarQueryParameter("genre", "STRING", genre),
            bigquery.ScalarQueryParameter("min_year", "INT64", min_year),
            bigquery.ScalarQueryParameter("min_rating", "FLOAT64", min_rating),
            bigquery.ScalarQueryParameter("limit", "INT64", limit),
        ]
    )

    try:
        rows = [dict(row) for row in client.query(sql, job_config=job_config).result()]
    except Exception as exc:
        return ({"error": f"BigQuery query failed: {exc}"}, 500, _CORS_HEADERS)

    print(f"  → {len(rows)} movies returned\n")

    return (
        {
            "rows": rows,
            "count": len(rows),
            "filters": {
                "q": q,
                "language": language,
                "genre": genre,
                "min_year": min_year,
                "min_rating": min_rating,
            },
        },
        200,
        _CORS_HEADERS,
    )
