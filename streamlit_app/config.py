"""config.py — centralised configuration for the Streamlit application."""
import os

# ── Cloud Function endpoints ──────────────────────────────────────────────────
MOVIES_AUTOCOMPLETE_URL: str = os.getenv(
    "MOVIES_AUTOCOMPLETE_URL",
    "https://movies-autocomplete-120497552025.europe-west6.run.app",
)
MOVIES_SEARCH_URL: str = os.getenv(
    "MOVIES_SEARCH_URL",
    "https://movies-search-120497552025.europe-west6.run.app",
)
MOVIE_DETAILS_URL: str = os.getenv(
    "MOVIE_DETAILS_URL",
    "https://movie-details-120497552025.europe-west6.run.app",
)

# ── Search behaviour ──────────────────────────────────────────────────────────
SEARCH_LIMIT: int = 100
AUTOCOMPLETE_LIMIT: int = 10
MIN_QUERY_LENGTH: int = 2

# ── Filter options shown in the UI ────────────────────────────────────────────
LANGUAGES = ["All", "en", "fr", "de", "it", "es", "hi", "ja", "ko", "zh"]

GENRES = [
    "All",
    "Action",
    "Adventure",
    "Animation",
    "Comedy",
    "Crime",
    "Documentary",
    "Drama",
    "Fantasy",
    "Horror",
    "Romance",
    "Sci-Fi",
    "Thriller",
    "War",
    "Western",
]

# MovieLens ratings are on a 0.5–5.0 scale (step 0.5)
DEFAULT_MIN_RATING: float = 0.0   # show all by default
DEFAULT_MIN_YEAR: int    = 1900   # MovieLens dataset starts ~1902
RESULTS_PER_LOAD: int    = 9      # cards shown initially (3×3 grid)
