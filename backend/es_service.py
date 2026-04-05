"""es_service.py — Elasticsearch helpers for the Flask backend.

Provides autocomplete and search over the 'movies_catalog_v1' index, which is
built from ASSIGNEMENT1 (the large catalogue) by index_movies_to_es.py.

Environment variables required:
    ES_ENDPOINT  — Elastic Cloud cluster URL (https://…:443)
    ES_API_KEY   — API key for the cluster
"""
from __future__ import annotations

import os
import re
from elasticsearch import Elasticsearch

ES_INDEX = "movies_catalog_v1"


def _get_es_client() -> Elasticsearch:
    return Elasticsearch(
        os.environ.get("ES_ENDPOINT"),
        api_key=os.environ.get("ES_API_KEY"),
    )


def fetch_all_titles(limit: int = 30_000) -> list[dict]:
    """Return ALL movies using search_after pagination to bypass the ES 10k limit.

    Uses movieId as the sort key so pagination is stable and deterministic.
    Returns [] silently if ES is unreachable or not configured.
    """
    try:
        es      = _get_es_client()
        results = []
        search_after = None
        batch_size   = 1_000

        while len(results) < limit:
            body: dict = {
                "size":    batch_size,
                "_source": ["title", "movieId", "tmdbId"],
                "query":   {"match_all": {}},
                "sort":    [{"movieId": "asc"}],
            }
            if search_after is not None:
                body["search_after"] = search_after

            resp = es.search(index=ES_INDEX, body=body)
            hits = resp["hits"]["hits"]
            if not hits:
                break

            results.extend(hits)
            search_after = hits[-1]["sort"]

        print(f"[ES] fetch_all_titles: {len(results)} movies (search_after pagination)")
        return [
            {
                "title":   hit["_source"].get("title", ""),
                "movieId": hit["_source"].get("movieId"),
                "tmdbId":  hit["_source"].get("tmdbId"),
            }
            for hit in results[:limit]
            if hit["_source"].get("title") and hit["_source"].get("movieId") is not None
        ]
    except Exception as exc:
        print(f"[ES] fetch_all_titles error: {exc}")
        return []


_ARTICLE_RE = re.compile(
    r"^(.+?),\s+(The|A|An|Le|La|Les|L'|El|Los|Las|Un|Une|Die|Das|Der|Ein)"
    r"(\s+\(.+\))?$",
    re.IGNORECASE,
)


def _normalize_title(raw: str) -> str:
    """'Scar, The (Blizna) (1976)' → 'The Scar (Blizna) (1976)'"""
    m = _ARTICLE_RE.match(raw)
    if m:
        return f"{m.group(2)} {m.group(1)}{m.group(3) or ''}"
    return raw


def autocomplete_titles(query: str, limit: int = 8) -> list[dict]:
    """Return up to *limit* title suggestions matching *query*.

    Uses multi_match bool_prefix — the fastest approach for search-as-you-type.
    The sub-fields title._2gram / title._3gram are created automatically by ES
    when the field mapping is of type search_as_you_type.

    Returns a list of dicts: [{title, movieId}, …]
    Returns [] silently if ES is unreachable or not configured.
    """
    if not query or len(query.strip()) < 2:
        return []

    try:
        es   = _get_es_client()
        # Combined query:
        #  • prefix (boost ×10): titles whose FIRST WORD starts exactly with the query
        #    → guarantees "Scum" scores higher than "Scenes from a Mall"
        #  • multi_match bool_prefix: finds word-boundary matches elsewhere
        fetch_size = min(limit * 15, 120)
        resp = es.search(
            index=ES_INDEX,
            body={
                "size": fetch_size,
                "_source": ["title", "movieId", "tmdbId"],
                "query": {
                    "bool": {
                        "should": [
                            {
                                "prefix": {
                                    "title": {
                                        "value": query.lower(),
                                        "boost": 10,
                                    }
                                }
                            },
                            {
                                "multi_match": {
                                    "query":  query,
                                    "type":   "bool_prefix",
                                    "fields": ["title^4", "title._2gram^2", "title._3gram"],
                                }
                            },
                        ]
                    }
                },
            },
        )
        hits = resp["hits"]["hits"]
        print(f"[ES] autocomplete '{query}': {len(hits)} raw hits")

        q_low = query.lower()
        # Articles to skip when looking for the first significant word
        _SKIP = {"the", "a", "an", "le", "la", "les", "un", "une", "des", "l'", "d'"}

        def _first_sig_word(title: str) -> str:
            """Return the first non-article word of the title, lower-cased."""
            for w in title.lower().split():
                clean = w.strip(".,!?\"'-()")
                if clean and clean not in _SKIP:
                    return clean
            return title.lower().split()[0] if title else ""

        def _rank(hit: dict) -> int:
            # Rank on the NORMALISED title so "Scar, The" is treated as "The Scar"
            # and no longer gets rank-0 for query "sc".
            raw = hit["_source"].get("title", "")
            t   = _normalize_title(raw).lower()
            fsw = _first_sig_word(t)
            if t.startswith(q_low):
                return 0     # whole title starts with query  → "Scarface"
            if fsw.startswith(q_low):
                return 1     # first significant word starts  → "School of Rock"
            if any(w.strip(".,!?\"'-()" ).startswith(q_low) for w in t.split()):
                return 2     # some other word starts         → "Ninja Scroll"
            return 3         # substring / ngram noise        → excluded for short queries

        # Secondary sort: within same rank, prefer the hit whose first significant
        # word is most "covered" by the query (higher ratio = closer match).
        # e.g. query "sc": "Scum"(4) → 2/4=50%, "Scrooge"(7) → 2/7=28%  → Scum wins.
        # Tertiary: title length ascending as final tiebreaker.
        def _sort_key(hit: dict):
            title   = hit["_source"].get("title", "")
            fsw     = _first_sig_word(title)
            fsw_len = max(len(fsw), 1)
            # Higher coverage = shorter first word relative to query = better match.
            coverage = -(len(q_low) / fsw_len)
            # Final tiebreaker: alphabetical on first significant word.
            return (_rank(hit), coverage, fsw, len(title))

        ranked = sorted(hits, key=_sort_key)

        # For short queries (≤ 3 chars) drop rank-3 noise entirely —
        # that removes "Old School", "White Sheik" etc. from "sc" results.
        if len(q_low) <= 3:
            ranked = [h for h in ranked if _rank(h) < 3]

        ranked = ranked[:limit]
        print(f"[ES] autocomplete '{query}': {len(ranked)} after filter/rank")

        return [
            {
                "title":   _normalize_title(hit["_source"].get("title", "")),
                "movieId": hit["_source"].get("movieId"),
                "tmdbId":  hit["_source"].get("tmdbId"),
            }
            for hit in ranked
        ]
    except Exception as exc:
        print(f"[ES] autocomplete error: {exc}")
        return []
