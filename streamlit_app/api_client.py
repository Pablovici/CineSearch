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


def _post_json(url: str, json_body: Optional[Dict] = None) -> Dict:
    """POST *url* with JSON body and return parsed JSON."""
    resp = requests.post(url, json=json_body if json_body is not None else {}, timeout=_TIMEOUT)
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


def post_recommend(base_url: str, body: Optional[Dict] = None) -> Dict:
    """POST /recommend on the local Flask API. *body* must include non-empty selected_movies."""
    url = f"{base_url.rstrip('/')}/recommend"
    return _post_json(url, body)


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


def fetch_all_titles(base_url: str, limit: int = 30_000) -> List[Dict]:
    """Return all movie titles from Flask /movies/titles for multiselect pre-loading."""
    url = f"{base_url.rstrip('/')}/movies/titles"
    data = _get(url, params={"limit": limit})
    return data.get("movies", [])


def fetch_details(url: str, tmdb_id: int) -> Dict:
    """Fetch enriched movie details (poster, overview, cast) from TMDB Cloud Function."""
    return _get(url, params={"tmdb_id": tmdb_id})
