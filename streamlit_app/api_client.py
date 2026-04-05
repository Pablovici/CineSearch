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


def fetch_details(url: str, tmdb_id: int) -> Dict:
    """Fetch enriched movie details (poster, overview, cast) from TMDB Cloud Function."""
    return _get(url, params={"tmdb_id": tmdb_id})


# TMDB genre ID mapping (matches the genres listed in config.py)
_TMDB_GENRE_IDS: Dict[str, int] = {
    "Action":      28,
    "Adventure":   12,
    "Animation":   16,
    "Comedy":      35,
    "Crime":       80,
    "Documentary": 99,
    "Drama":       18,
    "Fantasy":     14,
    "Horror":      27,
    "Romance":     10749,
    "Sci-Fi":      878,
    "Thriller":    53,
    "War":         10752,
    "Western":     37,
}

_TMDB_IMG_BASE = "https://image.tmdb.org/t/p/w500"
_TMDB_DISCOVER = "https://api.themoviedb.org/3/discover/movie"


def fetch_genre_poster_urls(api_key: str) -> Dict[str, str]:
    """Call TMDB /discover/movie for each genre and return a unique poster per genre.

    Tracks already-used poster paths so no two tiles show the same image.
    Falls back to page 2 if page 1 is exhausted by duplicates.
    Returns a dict mapping genre name → poster URL.
    """
    result: Dict[str, str] = {}
    used_paths: set = set()

    for genre, genre_id in _TMDB_GENRE_IDS.items():
        try:
            for page in (1, 2):
                resp = requests.get(
                    _TMDB_DISCOVER,
                    params={
                        "api_key":        api_key,
                        "with_genres":    genre_id,
                        "sort_by":        "popularity.desc",
                        "vote_count.gte": 200,
                        "page":           page,
                    },
                    timeout=10,
                )
                if resp.status_code != 200:
                    break
                movies = resp.json().get("results", [])
                found = False
                for movie in movies:
                    path = movie.get("poster_path")
                    if path and path not in used_paths:
                        used_paths.add(path)
                        result[genre] = f"{_TMDB_IMG_BASE}{path}"
                        found = True
                        break
                if found:
                    break   # no need to fetch page 2
        except Exception:
            pass
    return result
