"""api_client.py — HTTP layer for calling Cloud Functions.

Pure Python — no Streamlit imports — so this module is testable independently.
All functions raise RuntimeError on failure so the caller (app.py) decides
how to surface errors to the user.
"""
from typing import Dict, List, Optional

import requests

_TIMEOUT = 30


def _get(url: str, params: Optional[Dict] = None) -> Dict:
    """
    GET *url* with optional query params and return parsed JSON.
    Raises RuntimeError on HTTP errors or non-JSON responses.
    """
    resp = requests.get(url, params=params or {}, timeout=_TIMEOUT)
    content_type = resp.headers.get("content-type", "")

    if resp.status_code >= 400:
        snippet = resp.text[:300].replace("\n", " ")
        raise RuntimeError(
            f"HTTP {resp.status_code} from {url} — {snippet}"
        )

    try:
        return resp.json()
    except ValueError:
        snippet = resp.text[:300].replace("\n", " ")
        raise RuntimeError(f"Non-JSON response from {url} — {snippet}")


def fetch_autocomplete(url: str, prefix: str, limit: int = 10) -> List[Dict]:
    """Return title suggestions matching *prefix* (SQL LIKE autocomplete)."""
    data = _get(url, params={"q": prefix, "limit": limit})
    return data.get("suggestions", [])


def fetch_search(
    url: str,
    q: str,
    language: str = "",
    genre: str = "",
    min_rating: Optional[float] = None,
    min_year: Optional[int] = None,
    limit: int = 20,
) -> List[Dict]:
    """Search movies with filters (BigQuery JOIN + GROUP BY via Cloud Function)."""
    params: Dict = {"q": q, "limit": limit}
    if language and language != "All":
        params["language"] = language.lower()
    if genre and genre != "All":
        params["genre"] = genre.lower()
    if min_rating is not None:
        params["min_rating"] = min_rating
    if min_year is not None:
        params["min_year"] = min_year
    data = _get(url, params=params)
    return data.get("rows", [])


def fetch_details(url: str, tmdb_id: int) -> Dict:
    """Fetch enriched movie details (poster, overview, cast) from TMDB Cloud Function."""
    return _get(url, params={"tmdb_id": tmdb_id})
