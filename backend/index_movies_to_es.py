"""index_movies_to_es.py — One-shot script: BigQuery → Elasticsearch.

Reads all movies from ASSIGNEMENT1 (the large catalogue) and bulk-indexes
them into the Elasticsearch index 'movies_catalog_v1'.

Includes rich metadata: genres, language, release_year, country — so the
frontend can search and filter directly from Elasticsearch.

Usage:
    export ES_ENDPOINT="https://<your-cluster>.es.cloud.es.io:443"
    export ES_API_KEY="<your-api-key>"
    python backend/index_movies_to_es.py
"""

import os
from google.cloud import bigquery
from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk

# ── Config ────────────────────────────────────────────────────────────────────

PROJECT_ID       = os.environ.get("PROJECT_ID", "ferrous-store-487916-f8")
CATALOG_DATASET  = os.environ.get("CATALOG_DATASET", "ASSIGNEMENT1")
ES_ENDPOINT      = os.environ.get("ES_ENDPOINT")
ES_API_KEY       = os.environ.get("ES_API_KEY")
ES_INDEX         = "movies_catalog_v1"
BATCH_SIZE       = 500

# ── SQL — reads from the large catalogue (ASSIGNEMENT1) ─────────────────────

SQL = f"""
SELECT
  m.movieId      AS movieId,
  m.title        AS title,
  m.tmdbId       AS tmdbId,
  m.genres       AS genres,
  m.language     AS language,
  m.release_year AS release_year,
  m.country      AS country
FROM `{PROJECT_ID}.{CATALOG_DATASET}.movies` AS m
WHERE m.title IS NOT NULL
  AND TRIM(CAST(m.title AS STRING)) != ''
ORDER BY m.movieId
"""

# ── Elasticsearch index mapping ──────────────────────────────────────────────

INDEX_MAPPING = {
    "mappings": {
        "properties": {
            "movieId":      {"type": "integer"},
            "title":        {"type": "search_as_you_type"},
            "tmdbId":       {"type": "integer"},
            "genres":       {"type": "keyword"},
            "language":     {"type": "keyword"},
            "release_year": {"type": "integer"},
            "country":      {"type": "keyword"},
        }
    }
}

# ── BigQuery ──────────────────────────────────────────────────────────────────

def fetch_movies() -> list[dict]:
    print(f"[BQ] Connecting to {PROJECT_ID}.{CATALOG_DATASET}…")
    client = bigquery.Client(project=PROJECT_ID)
    rows   = list(client.query(SQL).result())
    print(f"[BQ] {len(rows)} movies fetched.")
    return rows

# ── Elasticsearch ─────────────────────────────────────────────────────────────

def _actions(rows: list):
    """Yield one bulk action per movie. movieId is used as document _id
    so re-running this script is safe (overwrites, no duplicates)."""
    for row in rows:
        doc = {
            "movieId":      int(row["movieId"]),
            "title":        row["title"],
            "tmdbId":       int(row["tmdbId"]) if row["tmdbId"] is not None else None,
            "genres":       row.get("genres"),
            "language":     row.get("language"),
            "release_year": int(row["release_year"]) if row.get("release_year") is not None else None,
            "country":      row.get("country"),
        }
        yield {
            "_index":  ES_INDEX,
            "_id":     doc["movieId"],
            "_source": doc,
        }


def create_index_if_needed(es: Elasticsearch) -> None:
    """Create the index with the proper mapping if it doesn't exist yet."""
    if es.indices.exists(index=ES_INDEX):
        print(f"[ES] Index '{ES_INDEX}' already exists — will overwrite documents.")
        return
    es.indices.create(index=ES_INDEX, body=INDEX_MAPPING)
    print(f"[ES] Created index '{ES_INDEX}' with search_as_you_type mapping.")


def index_movies(rows: list[dict]) -> None:
    print(f"[ES] Connecting to {ES_ENDPOINT}…")
    es      = Elasticsearch(ES_ENDPOINT, api_key=ES_API_KEY)
    cluster = es.info()["cluster_name"]
    print(f"[ES] Connected — cluster: {cluster}")

    create_index_if_needed(es)

    all_actions = list(_actions(rows))
    total_ok    = 0

    for i in range(0, len(all_actions), BATCH_SIZE):
        batch             = all_actions[i : i + BATCH_SIZE]
        success, errors   = bulk(es, batch, raise_on_error=False)
        total_ok         += success

        if errors:
            print(f"[ES] Batch {i // BATCH_SIZE + 1}: {success} ok, {len(errors)} errors")
            for err in errors[:3]:
                print(f"       {err}")
        else:
            print(f"[ES] Indexed {total_ok} / {len(all_actions)} movies…")

    print(f"\n[ES] Done — {total_ok} documents in index '{ES_INDEX}'.")

# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    if not ES_ENDPOINT or not ES_API_KEY:
        raise EnvironmentError(
            "ES_ENDPOINT and ES_API_KEY must be set as environment variables.\n"
            "  export ES_ENDPOINT='https://...'\n"
            "  export ES_API_KEY='...'"
        )

    rows = fetch_movies()
    if not rows:
        print("[BQ] No movies returned — check your dataset name and permissions.")
        return

    index_movies(rows)


if __name__ == "__main__":
    main()
