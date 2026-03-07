"""movies_autocomplete — Cloud Function
Returns movie title suggestions matching a search prefix using SQL LIKE.
Results are ordered: titles that *start with* the prefix come first,
followed by titles that merely *contain* it.
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
def movies_autocomplete(request):
    """HTTP Cloud Function — title autocomplete via SQL LIKE."""
    if request.method == "OPTIONS":
        return ("", 204, _CORS_HEADERS)

    prefix = request.args.get("q", "").strip()
    limit = min(int(request.args.get("limit", "10")), 30)

    if not prefix:
        return ({"suggestions": [], "count": 0}, 200, _CORS_HEADERS)

    try:
        client = bigquery.Client()
    except Exception as exc:
        return ({"error": f"BigQuery client init failed: {exc}"}, 503, _CORS_HEADERS)

    # Starts-with suggestions come first, then broader "contains" matches.
    sql = f"""
    SELECT
        movieId,
        title,
        release_year,
        language,
        genres,
        tmdbId
    FROM {_TABLE_MOVIES}
    WHERE
        LOWER(title) LIKE CONCAT(LOWER(@prefix), '%')
        OR LOWER(title) LIKE CONCAT('%', LOWER(@prefix), '%')
    ORDER BY
        CASE WHEN LOWER(title) LIKE CONCAT(LOWER(@prefix), '%') THEN 0 ELSE 1 END,
        title
    LIMIT @limit
    """

    print("\n── SQL EXECUTED (movies_autocomplete) ──")
    print(sql)
    print(f"  PARAM prefix = '{prefix}'")
    print(f"  PARAM limit  = {limit}\n")

    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("prefix", "STRING", prefix),
            bigquery.ScalarQueryParameter("limit", "INT64", limit),
        ]
    )

    try:
        rows = [dict(row) for row in client.query(sql, job_config=job_config).result()]
    except Exception as exc:
        return ({"error": f"BigQuery query failed: {exc}"}, 500, _CORS_HEADERS)

    print(f"  → {len(rows)} suggestions returned\n")

    return ({"suggestions": rows, "count": len(rows)}, 200, _CORS_HEADERS)
