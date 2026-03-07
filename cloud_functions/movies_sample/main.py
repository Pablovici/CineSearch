"""movies_sample — Cloud Function
Returns a paginated sample of movies ordered by movieId.
Useful for dataset exploration and integration testing.
Note: the Streamlit UI uses movies_search (with q="") for its home page;
this endpoint is kept for direct dataset browsing and future extensions.
All executed SQL is printed to stdout (visible in Cloud Run logs).
"""
import functions_framework
from google.cloud import bigquery

# ── BigQuery config ───────────────────────────────────────────────────────────
_PROJECT = "ferrous-store-487916-f8"
_DATASET = "ASSIGNEMENT1"
_TABLE_MOVIES = f"`{_PROJECT}.{_DATASET}.movies`"

_CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
}


@functions_framework.http
def movies_sample(request):
    """HTTP Cloud Function — return a sample of movies."""
    # Handle CORS pre-flight
    if request.method == "OPTIONS":
        return ("", 204, _CORS_HEADERS)

    limit = min(int(request.args.get("limit", "50")), 200)  # hard cap at 200

    try:
        client = bigquery.Client()
    except Exception as exc:
        return ({"error": f"BigQuery client init failed: {exc}"}, 503, _CORS_HEADERS)

    sql = f"""
    SELECT
        movieId,
        title,
        genres,
        language,
        release_year,
        country,
        tmdbId
    FROM {_TABLE_MOVIES}
    ORDER BY movieId
    LIMIT @limit
    """

    print("\n── SQL EXECUTED (movies_sample) ──")
    print(sql)
    print(f"  PARAM limit = {limit}\n")

    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("limit", "INT64", limit),
        ]
    )

    try:
        rows = [dict(row) for row in client.query(sql, job_config=job_config).result()]
    except Exception as exc:
        return ({"error": f"BigQuery query failed: {exc}"}, 500, _CORS_HEADERS)

    print(f"  → {len(rows)} rows returned\n")

    return ({"rows": rows, "count": len(rows)}, 200, _CORS_HEADERS)
