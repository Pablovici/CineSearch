"""app.py — CinéSearch · Streamlit entry point.

Orchestrator: wires cached API calls and delegates all rendering to ui_components.

Architecture (2-layer as per assignment):
  Layer 1 — Database  : BigQuery  (via Cloud Functions)
  Layer 2 — Logic+UI  : Streamlit + Cloud Functions

Internal modules:
  app.py           ← orchestration, caching, navigation state
  config.py        ← Cloud Function URLs, UI constants
  api_client.py    ← HTTP layer (pure Python, no Streamlit)
  ui_components.py ← rendering helpers (no HTTP, no SQL)
"""
import json
import random
import time
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

import config
from api_client import fetch_autocomplete, fetch_details, fetch_search, post_recommend
from ui_components import (
    _normalize_title,
    _render_movie_card,
    hide_loader,
    inject_css,
    render_empty_state,
    render_featured_grid,
    render_filters,
    render_hero_section,
    render_movie_detail_full,
    render_results_cards,
    render_section_divider,
    render_sidebar_header,
    render_trending_row,
)

st.set_page_config(
    page_title="CinéSearch",
    page_icon="C",
    layout="wide",
    initial_sidebar_state="auto",
)

# TMDB IDs for the home page hero carousel (Inception, Dark Knight, Interstellar, Pulp Fiction, Shawshank)
_HERO_IDS     = [27205, 155, 157336, 680, 278]
_PAGE_SIZE    = config.RESULTS_PER_LOAD
_SORT_OPTIONS = ["Relevance", "Title A→Z", "Title Z→A", "Year ↓", "Year ↑", "Rating ↓", "Rating ↑"]

# ── Favorites persistence (survives URL navigations / page reloads) ───────────
_FAVORITES_FILE = Path.home() / ".cinesearch_favorites.json"


def _load_favorites() -> List[Dict]:
    try:
        return json.loads(_FAVORITES_FILE.read_text())
    except Exception:
        return []


def _save_favorites(favs: List[Dict]) -> None:
    try:
        _FAVORITES_FILE.write_text(json.dumps(favs))
    except Exception:
        pass


_REC_MODE_LABELS: Dict[str, str] = {
    "popular_top":                       "Popular right now",
    "popular_fallback_no_similar_users": "Popular movies",
    "similar_users_bqml":                "Recommended for your taste",
}


# ── Cached API wrappers ───────────────────────────────────────────────────────

@st.cache_data(ttl=30)
def _autocomplete(prefix: str) -> List[Dict]:
    """ES autocomplete via Flask backend, Cloud Function as fallback.

    Priority:
      1. Flask /autocomplete  — Elasticsearch, returns {title, movieId}
      2. Cloud Function       — BigQuery LIKE, returns {title, release_year, …}
    Falls back silently so the UI is never blocked.
    """
    # 1 — Try Flask/ES first
    try:
        url = f"{config.BACKEND_URL.rstrip('/')}/autocomplete"
        results = fetch_autocomplete(url, prefix, config.AUTOCOMPLETE_LIMIT)
        if results:
            return results
    except Exception:
        pass
    # 2 — Fall back to Cloud Function (always deployed)
    try:
        return fetch_autocomplete(
            config.MOVIES_AUTOCOMPLETE_URL, prefix, config.AUTOCOMPLETE_LIMIT
        )
    except Exception:
        return []


@st.cache_data(ttl=60)
def _search(q: str, language: str, genre: str, min_rating: float, min_year: int) -> List[Dict]:
    return fetch_search(
        config.MOVIES_SEARCH_URL,
        q=q,
        language=language,
        genre=genre,
        min_rating=float(min_rating),
        min_year=int(min_year),
        limit=config.SEARCH_LIMIT,
    )


@st.cache_data(ttl=3600)
def _details(tmdb_id: int) -> Dict:
    return fetch_details(config.MOVIE_DETAILS_URL, tmdb_id)


@st.cache_data(ttl=3600)
def _featured_movies_pool() -> List[Dict]:
    """Diverse pool for the 'Discover' section.

    Fetches a broad set of movies, then filters client-side to favour
    well-known but not ubiquitous titles (rating_count 150–800) with a
    good-but-not-perfect average (avg_rating 3.0–4.4 / 5).
    Falls back to the unfiltered results if the pool is too small.
    """
    try:
        results = fetch_search(
            config.MOVIES_SEARCH_URL,
            q="",
            language="All",
            genre="All",
            min_rating=2.5,
            min_year=1960,
            limit=300,
        )
        filtered = [
            r for r in results
            if 150 <= int(r.get("rating_count") or 0) <= 800
            and 3.0 <= float(r.get("avg_rating") or 0) <= 4.4
        ]
        return filtered if len(filtered) >= 20 else results
    except Exception:
        return []


@st.cache_data(ttl=3600)
def _trending_movies_data() -> List[Dict]:
    """Top-rated films from the two most recent years in the dataset."""
    try:
        results = fetch_search(
            config.MOVIES_SEARCH_URL,
            q="the",
            language="All",
            genre="All",
            min_rating=0.0,
            min_year=1900,
            limit=500,
        )
        if not results:
            return []

        years = [int(r.get("release_year") or 0) for r in results if r.get("release_year")]
        if not years:
            return []
        max_year = max(years)

        recent = [
            r for r in results
            if int(r.get("release_year") or 0) >= max_year - 2
        ]
        recent = sorted(recent, key=lambda r: int(r.get("rating_count") or 0), reverse=True)
        return recent[:6]
    except Exception:
        return []



# ── Helpers ───────────────────────────────────────────────────────────────────

def _year_ok(suggestion: dict, min_year: int) -> bool:
    year = suggestion.get("release_year")
    if not year:
        return True  # missing year (e.g. ES suggestions) → pass through
    try:
        return int(year) >= min_year
    except (ValueError, TypeError):
        return True


def _year_ok_max(row: dict, max_year: int) -> bool:
    """Client-side max year filter (API only supports min_year)."""
    try:
        return int(row.get("release_year", 9999)) <= max_year
    except (ValueError, TypeError):
        return True


_TITLE_ARTICLES = {"the", "a", "an", "le", "la", "les", "un", "une", "l'", "d'"}


def _relevance_rank(title: str, q: str) -> tuple:
    """Same ranking logic as ES autocomplete so the grid order matches the dropdown.

    Rank 0 — whole title starts with q         → "Scarface"
    Rank 1 — first significant word starts     → "School of Rock"
    Rank 2 — any other word starts             → "Ninja Scroll"
    Rank 3 — query appears anywhere (contains) → "Great Escape" for "sca"

    Within each rank: higher coverage of first word → better;
    then alphabetical on first significant word.
    """
    t = title.lower()
    q = q.lower()
    words = t.split()
    # First significant word (skip leading articles)
    fsw = next(
        (w.strip(".,!?\"'()") for w in words if w.strip(".,!?\"'()") not in _TITLE_ARTICLES),
        words[0] if words else "",
    )
    fsw_len  = max(len(fsw), 1)
    coverage = -(len(q) / fsw_len)   # more negative = better (ascending sort)

    if t.startswith(q):
        rank = 0
    elif fsw.startswith(q):
        rank = 1
    elif any(w.strip(".,!?\"'()").startswith(q) for w in words):
        rank = 2
    else:
        rank = 3

    return (rank, coverage, fsw, len(title))


def _sort_rows(rows: list, sort_by: str, q: str = "") -> list:
    """Sort results list based on selected option."""
    if sort_by == "Title A→Z":
        return sorted(rows, key=lambda r: r.get("title", "").lower())
    if sort_by == "Title Z→A":
        return sorted(rows, key=lambda r: r.get("title", "").lower(), reverse=True)
    if sort_by == "Year ↓":
        return sorted(rows, key=lambda r: r.get("release_year", 0), reverse=True)
    if sort_by == "Year ↑":
        return sorted(rows, key=lambda r: r.get("release_year", 9999))
    if sort_by == "Rating ↓":
        return sorted(rows, key=lambda r: float(r.get("avg_rating") or 0), reverse=True)
    if sort_by == "Rating ↑":
        return sorted(rows, key=lambda r: float(r.get("avg_rating") or 0))
    # "Relevance" — re-rank by same prefix logic as the autocomplete dropdown
    if q:
        return sorted(rows, key=lambda r: _relevance_rank(r.get("title", ""), q))
    return rows


def _add_to_history(q: str) -> None:
    """Prepend q to search history, deduplicate, keep last 10."""
    history: List[str] = st.session_state.get("_search_history", [])
    if q in history:
        history.remove(q)
    history.insert(0, q)
    st.session_state["_search_history"] = history[:10]


def _prefetch_poster_urls(movies: List[Dict]) -> Dict[int, str]:
    """Fetch TMDB details and extract poster URLs for a list of movies."""
    poster_urls: Dict[int, str] = {}
    for movie in movies:
        raw_id = movie.get("tmdbId")
        if raw_id is None:
            continue
        try:
            if pd.isna(raw_id):
                continue
            tmdb_id = int(raw_id)
            det = _details(tmdb_id)
            url = det.get("poster_url")
            if url:
                poster_urls[tmdb_id] = url
        except Exception:
            pass
    return poster_urls


# ── Auto-rotating hero carousel (re-renders every 8 s) ────────────────────────

@st.fragment(run_every=5)
def _hero_carousel_fragment() -> None:
    """Hero carousel: auto-advances every 5 s."""
    n = len(_HERO_IDS)
    idx = (int(time.time()) // 5) % n
    tmdb_id = _HERO_IDS[idx]
    try:
        details = _details(tmdb_id)
    except Exception:
        details = {}
    render_hero_section(details, idx, n, tmdb_id=tmdb_id)


# ── Recommendation section (Assignment 2) ────────────────────────────────────

_EMPTY_SLOT_HTML = (
    '<div style="aspect-ratio:2/3;background:rgba(255,255,255,0.04);'
    'border-radius:8px;border:1px dashed rgba(255,255,255,0.12);"></div>'
    '<div style="height:1.6rem;"></div>'
)


def _render_recommendation_section() -> None:
    """Two-row recommendation block driven by multiselect preferences / favorites.

    Row 1 — "Vous avez aimé"       : last 6 liked movies + "Voir tous" button.
    Row 2 — "Vous aimerez peut-être": ML recommendations auto-triggered from preferences.
    Preferences come from sidebar multiselect (synced with ❤️ favorites on detail pages).
    """
    favs: List[Dict] = st.session_state.get("_favorites", [])
    seed_ids: List[int] = [f["movieId"] for f in favs]

    # Auto-trigger recommendations whenever favorites change
    prev_seed_ids: Optional[List[int]] = st.session_state.get("_rec_seed_ids")
    if seed_ids != prev_seed_ids:
        st.session_state["_rec_seed_ids"] = list(seed_ids)
        try:
            with st.spinner("Calcul en cours…"):
                result = post_recommend(
                    config.BACKEND_URL,
                    {"selected_movie_ids": seed_ids},
                )
            rec_movies = result.get("recommended_movies", [])
            st.session_state["_rec_result"]  = result
            st.session_state["_rec_posters"] = _prefetch_poster_urls(rec_movies)
        except Exception:
            st.session_state.pop("_rec_result", None)
            st.session_state.pop("_rec_posters", None)

    # ── Row 1 : Vous avez aimé ────────────────────────────────────────────────
    col_label, col_btn = st.columns([5, 1], vertical_alignment="bottom")
    with col_label:
        st.markdown(
            '<p style="color:rgba(255,255,255,0.42);font-size:0.68rem;font-weight:600;'
            'letter-spacing:0.1em;text-transform:uppercase;margin:0.9rem 0 0.5rem;">'
            'Vous avez aimé</p>',
            unsafe_allow_html=True,
        )
    with col_btn:
        if favs and st.button(
            "Voir tous", key="_btn_see_all_favs",
            type="secondary", use_container_width=True,
        ):
            st.session_state["_view"] = "favorites"
            st.rerun()

    liked_data = list(reversed(favs))[:6]
    liked_posters = _prefetch_poster_urls(liked_data) if liked_data else {}
    cols = st.columns(6, gap="small")
    for i in range(6):
        if i < len(liked_data):
            _render_movie_card(cols[i], liked_data[i], liked_posters)
        else:
            cols[i].markdown(_EMPTY_SLOT_HTML, unsafe_allow_html=True)

    # ── Row 2 : Vous aimerez peut-être ───────────────────────────────────────
    st.markdown(
        '<p style="color:rgba(255,255,255,0.42);font-size:0.68rem;font-weight:600;'
        'letter-spacing:0.1em;text-transform:uppercase;margin:0.9rem 0 0.5rem;">'
        'Vous aimerez peut-être</p>',
        unsafe_allow_html=True,
    )
    if not favs:
        st.markdown(
            '<p style="color:rgba(255,255,255,0.3);font-size:0.8rem;margin:0.5rem 0 0.8rem;">'
            'Select movies in the sidebar to get personalized recommendations.</p>',
            unsafe_allow_html=True,
        )
    result     = st.session_state.get("_rec_result")
    rec_movies = result.get("recommended_movies", [])[:6] if result else []
    posters    = st.session_state.get("_rec_posters", {})
    cols = st.columns(6, gap="small")
    for i in range(6):
        if i < len(rec_movies):
            _render_movie_card(cols[i], rec_movies[i], posters)
        else:
            cols[i].markdown(_EMPTY_SLOT_HTML, unsafe_allow_html=True)


# ── Mes films aimés — full-page view ─────────────────────────────────────────

def _render_all_favorites_page() -> None:
    """Full-page grid of all liked movies with per-card unlike and a clear-all."""
    inject_css()

    col_back, col_title, col_clear = st.columns([1, 4, 1], vertical_alignment="bottom")
    with col_back:
        if st.button("← Retour", key="_back_from_favs", type="secondary"):
            st.session_state.pop("_view", None)
            st.rerun()
    with col_title:
        favs: List[Dict] = st.session_state.get("_favorites", [])
        st.markdown(
            f'<h2 style="color:#fff;font-size:1.4rem;font-weight:700;margin:0;">'
            f'Mes films aimés '
            f'<span style="font-size:0.9rem;font-weight:400;color:rgba(255,255,255,0.4);">'
            f'({len(favs)})</span></h2>',
            unsafe_allow_html=True,
        )
    with col_clear:
        if favs and st.button("🗑️ Tout supprimer", key="_btn_clear_all", type="secondary"):
            st.session_state["_favorites"] = []
            _save_favorites([])
            st.session_state.pop("_rec_seed_ids", None)
            st.session_state.pop("_rec_result", None)
            st.session_state.pop("_view", None)
            st.rerun()

    if not favs:
        st.markdown(
            '<p style="color:rgba(255,255,255,0.4);margin-top:2rem;">'
            'Vous n\'avez encore aimé aucun film. '
            'Explorez le catalogue et cliquez ❤️ sur les fiches.</p>',
            unsafe_allow_html=True,
        )
        hide_loader()
        return

    all_favs = list(reversed(favs))
    fav_posters = _prefetch_poster_urls(all_favs)

    # Render in rows of 6
    for row_start in range(0, len(all_favs), 6):
        row = all_favs[row_start : row_start + 6]
        cols = st.columns(6, gap="small")
        for i in range(6):
            if i < len(row):
                movie = row[i]
                _render_movie_card(cols[i], movie, fav_posters)
                mid = movie.get("movieId")
                with cols[i]:
                    if st.button(
                        "✕ Retirer", key=f"_unlike_{mid}_{row_start}",
                        use_container_width=True,
                    ):
                        st.session_state["_favorites"] = [
                            f for f in st.session_state.get("_favorites", [])
                            if f["movieId"] != mid
                        ]
                        _save_favorites(st.session_state["_favorites"])
                        st.session_state.pop("_rec_seed_ids", None)
                        st.toast("Retiré de vos favoris.")
                        st.rerun()
            else:
                cols[i].markdown(_EMPTY_SLOT_HTML, unsafe_allow_html=True)

    hide_loader()



# ── Full-page detail view ─────────────────────────────────────────────────────

def _show_full_detail() -> None:
    """Renders the full-page movie detail and a back button."""
    inject_css()

    # _detail_return_q is set ONLY when coming from search results.
    # Its presence (even if empty string) means "go back to search".
    came_from_search = "_detail_return_q" in st.session_state
    back_label = "← Results" if came_from_search else "← Home"

    if st.button(back_label, key="_back_btn", type="secondary"):
        del st.session_state["detail_tmdb_id"]
        if came_from_search:
            return_q = st.session_state.pop("_detail_return_q", "")
            # Restore the search query via a flag read BEFORE widget creation
            st.session_state["_restore_search"] = return_q
        else:
            st.session_state.pop("_detail_return_q", None)
            # Coming from home: wipe search state + refresh Discover selection
            st.session_state["_confirmed_q"]  = None
            st.session_state["_last_raw_q"]   = ""
            st.session_state["_reset_search"] = True
            st.session_state.pop("_featured_selection", None)
        st.rerun()

    tmdb_id  = st.session_state["detail_tmdb_id"]
    movie_id = st.session_state.get("detail_movie_id")   # MovieLens id, may be None

    with st.spinner("Loading details…"):
        try:
            details = _details(tmdb_id)
        except Exception as exc:
            st.error(f"Failed to load details: {exc}")
            return

    # ── Favorites toggle ──────────────────────────────────────────────────────
    if movie_id is not None:
        favs: List[Dict] = st.session_state.get("_favorites", [])
        fav_ids = [f["movieId"] for f in favs]
        is_fav  = movie_id in fav_ids
        btn_label = "❤️  Remove from Favorites" if is_fav else "♡  Add to Favorites"
        if st.button(btn_label, key="_btn_fav_toggle", type="secondary"):
            if is_fav:
                st.session_state["_favorites"] = [f for f in favs if f["movieId"] != movie_id]
                st.toast("Removed from favorites.")
            else:
                entry = {
                    "movieId": movie_id,
                    "title":   details.get("title", ""),
                    "tmdbId":  tmdb_id,
                }
                st.session_state.setdefault("_favorites", []).append(entry)
                st.session_state.pop("_fav_rec_result", None)  # stale recs no longer valid
                st.toast("Added to favorites!")
            # Persist to disk so favorites survive URL navigations
            _save_favorites(st.session_state["_favorites"])
            # Reset rec seed so home page recomputes with updated favorites
            st.session_state.pop("_rec_seed_ids", None)
            st.rerun()

    render_movie_detail_full(details)
    hide_loader()


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    inject_css()

    # ── Load favorites from disk on every fresh session ───────────────────────
    if "_favorites_loaded" not in st.session_state:
        st.session_state["_favorites"]       = _load_favorites()
        st.session_state["_favorites_loaded"] = True

    # ── Hero search form submission (?q=QUERY&fl_lang=…&fl_genres=…&…) ─────────
    # Guard: only handle if NOT a card-click (?detail=) or hero CTA (?hero_tmdb=)
    hero_q = st.query_params.get("q")
    if hero_q and not st.query_params.get("detail") and not st.query_params.get("hero_tmdb"):
        try:
            q_val = hero_q.strip()
            # Read filter params BEFORE clearing query_params
            fl_lang     = st.query_params.get("fl_lang", "")
            fl_genres   = st.query_params.get("fl_genres", "")
            fl_year_min = st.query_params.get("fl_year_min", "")
            fl_year_max = st.query_params.get("fl_year_max", "")
            fl_rating   = st.query_params.get("fl_rating", "")
            st.query_params.clear()
            if q_val:
                st.session_state["_confirmed_q"]      = q_val
                st.session_state["_last_raw_q"]       = q_val
                st.session_state["search_text_input"] = q_val
                st.session_state["_last_typed_q"]     = q_val
                st.session_state["_visible_count"]    = _PAGE_SIZE
                # Restore filter values from URL so they survive the navigation
                if fl_lang:
                    st.session_state["_fl_lang"] = fl_lang
                if fl_genres:
                    st.session_state["_fl_genres"] = [g for g in fl_genres.split(",") if g]
                if fl_year_min or fl_year_max:
                    try:
                        ymin = int(fl_year_min) if fl_year_min else config.DEFAULT_MIN_YEAR
                        ymax = int(fl_year_max) if fl_year_max else 2026
                        st.session_state["_fl_year"] = (ymin, ymax)
                    except (ValueError, TypeError):
                        pass
                if fl_rating:
                    try:
                        st.session_state["_fl_rating"] = float(fl_rating)
                    except (ValueError, TypeError):
                        pass
                st.rerun()
        except Exception:
            st.query_params.clear()

    # ── Card click via query param (?detail=ID&src=home|search&q=QUERY) ─────────
    detail_param = st.query_params.get("detail")
    if detail_param:
        try:
            src     = st.query_params.get("src", "home")
            q_param = st.query_params.get("q", "")
            mid     = st.query_params.get("mid")
            st.query_params.clear()
            if src == "search" and q_param:
                st.session_state["_detail_return_q"] = q_param
            else:
                st.session_state.pop("_detail_return_q", None)
            st.session_state["detail_tmdb_id"] = int(detail_param)
            # Store MovieLens movieId when available (passed via &mid= from card href).
            if mid:
                st.session_state["detail_movie_id"] = int(mid)
            else:
                st.session_state.pop("detail_movie_id", None)
            st.rerun()
        except (ValueError, TypeError):
            st.query_params.clear()

    # ── Hero CTA click via query param (?hero_tmdb=ID) ─────────────────────────
    hero_tmdb = st.query_params.get("hero_tmdb")
    if hero_tmdb:
        try:
            st.query_params.clear()
            st.session_state["app_started"] = True
            st.session_state.pop("_detail_return_q", None)
            st.session_state["detail_tmdb_id"] = int(hero_tmdb)
            st.rerun()
        except (ValueError, TypeError):
            st.query_params.clear()

    st.session_state["app_started"] = True

    # ── Full-page detail view ──────────────────────────────────────────────────
    if "detail_tmdb_id" in st.session_state:
        _show_full_detail()
        return

    # ── Mes films aimés — full-page view ──────────────────────────────────────
    if st.session_state.get("_view") == "favorites":
        _render_all_favorites_page()
        return

    # ── Sidebar ───────────────────────────────────────────────────────────────
    with st.sidebar:
        render_sidebar_header()

        # Restore confirmed query when returning from detail → results
        if "_restore_search" in st.session_state:
            restore_q = st.session_state.pop("_restore_search")
            if restore_q:
                st.session_state["_confirmed_q"]   = restore_q
                st.session_state["_visible_count"] = _PAGE_SIZE

        if st.session_state.pop("_reset_search", False):
            st.session_state["_confirmed_q"] = None
            st.session_state["_last_raw_q"]  = ""

        # ── Real-time autocomplete search component ───────────────────────────
        # • Typing → JS fetches ES suggestions live (180 ms debounce)
        # • Click suggestion → /?detail=TMDB_ID  (film detail page)
        # • Press Enter     → /?q=QUERY&fl_*=…   (results grid + filters)
        _current_q = (st.session_state.get("_confirmed_q") or "").replace('"', "&quot;")
        _backend   = config.BACKEND_URL.rstrip("/")
        # Snapshot current filter values so Enter preserves them across navigation.
        # Widgets may not have run yet on first load — use safe defaults in that case.
        _lang_display_names_snap = [config.LANGUAGE_NAMES[lang] for lang in config.LANGUAGES]
        _fl_lang_val   = str(st.session_state.get("_fl_lang") or _lang_display_names_snap[0] if _lang_display_names_snap else "").replace('"', "&quot;")
        _fl_genres_raw = st.session_state.get("_fl_genres") or []
        _fl_genres_val = ",".join(_fl_genres_raw).replace('"', "&quot;")
        _fl_year_raw   = st.session_state.get("_fl_year", (config.DEFAULT_MIN_YEAR, 2026))
        _fl_year_min   = int(_fl_year_raw[0]) if isinstance(_fl_year_raw, (tuple, list)) else config.DEFAULT_MIN_YEAR
        _fl_year_max   = int(_fl_year_raw[1]) if isinstance(_fl_year_raw, (tuple, list)) else 2026
        _fl_rating_val = float(st.session_state.get("_fl_rating") or 0.0)
        components.html(f"""<!DOCTYPE html><html>
<head><style>
  *,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
  html,body{{background:transparent;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;overflow:visible}}
  #w{{position:relative}}
  #si{{
    display:block;width:100%;height:42px;padding:0 14px;
    border:1px solid rgba(255,255,255,0.12);border-radius:10px;
    background:rgba(255,255,255,0.04);color:#fff;font-size:.88rem;outline:none;
    transition:border-color .15s
  }}
  #si:focus{{border-color:rgba(200,50,50,.75)}}
  #si.open{{border-radius:10px 10px 0 0;border-bottom-color:rgba(255,255,255,0.04)}}
  #si::placeholder{{color:rgba(255,255,255,.25)}}
  #sugs{{
    display:none;position:absolute;top:42px;left:0;right:0;
    background:rgba(18,18,22,0.99);
    border:1px solid rgba(255,255,255,0.1);border-top:none;
    border-radius:0 0 10px 10px;overflow:hidden;z-index:999
  }}
  .sg{{
    padding:10px 16px;color:rgba(255,255,255,.75);font-size:.83rem;
    cursor:pointer;border-bottom:1px solid rgba(255,255,255,.04);
    overflow:hidden;text-overflow:ellipsis;white-space:nowrap;
    letter-spacing:.01em;transition:background .1s
  }}
  .sg:last-child{{border-bottom:none}}
  .sg:hover{{background:rgba(200,50,50,.15);color:rgba(255,255,255,.95)}}
</style></head>
<body><div id="w">
  <input id="si" type="text" placeholder="Search movies…"
         autocomplete="off" spellcheck="false" value="{_current_q}"/>
  <div id="sugs"></div>
</div>
<script>
  const BACKEND="{_backend}";
  const FL_LANG="{_fl_lang_val}";
  const FL_GENRES="{_fl_genres_val}";
  const FL_YEAR_MIN={_fl_year_min};
  const FL_YEAR_MAX={_fl_year_max};
  const FL_RATING={_fl_rating_val};
  const si=document.getElementById('si'),sugs=document.getElementById('sugs');
  let timer,ctrl;

  function setH(h){{try{{window.frameElement.style.height=h+'px'}}catch(e){{}}}}

  function openSugs(){{
    sugs.style.display='block';
    si.classList.add('open');
    setH(42+sugs.querySelectorAll('.sg').length*40+2);
  }}
  function closeSugs(){{
    sugs.style.display='none';
    si.classList.remove('open');
    setH(48);
  }}
  setH(48);

  function nav(url){{
    try{{ window.parent.location.href=url; }}
    catch(e){{
      try{{
        var a=document.createElement('a');
        a.href=url;a.target='_top';
        document.body.appendChild(a);a.click();document.body.removeChild(a);
      }}catch(e2){{ try{{window.top.location.href=url;}}catch(e3){{}} }}
    }}
  }}

  si.addEventListener('input',function(){{
    clearTimeout(timer);
    var q=this.value.trim();
    if(q.length<2){{closeSugs();return;}}
    timer=setTimeout(function(){{load(q);}},180);
  }});

  function load(q){{
    if(ctrl)ctrl.abort();
    ctrl=new AbortController();
    fetch(BACKEND+'/autocomplete?q='+encodeURIComponent(q)+'&limit=8',{{signal:ctrl.signal}})
      .then(function(r){{return r.json();}})
      .then(function(d){{show(d.suggestions||[]);d=null;}})
      .catch(function(e){{if(e.name!=='AbortError')closeSugs();}});
  }}

  function show(items){{
    if(!items.length){{closeSugs();return;}}
    sugs.innerHTML=items.map(function(m){{
      return '<div class="sg"'
        +' data-t="'+(m.tmdbId||'')+'"'
        +' data-m="'+(m.movieId||'')+'"'
        +' data-q="'+m.title.replace(/"/g,'&quot;')+'">'
        +m.title+'</div>';
    }}).join('');
    openSugs();
  }}

  sugs.addEventListener('click',function(e){{
    var el=e.target.closest('.sg');
    if(!el)return;
    var t=el.getAttribute('data-t');
    var m=el.getAttribute('data-m');
    var q=el.getAttribute('data-q');
    if(t&&t!=='None'&&t!=='null'&&t!==''){{
      nav('/?detail='+t+'&mid='+(m||'')+'&src=home');
    }} else if(q){{
      nav('/?q='+encodeURIComponent(q));
    }}
  }});

  si.addEventListener('keydown',function(e){{
    if(e.key==='Enter'){{
      var q=si.value.trim();
      if(q.length>=2){{
        closeSugs();
        var url='/?q='+encodeURIComponent(q);
        if(FL_LANG) url+='&fl_lang='+encodeURIComponent(FL_LANG);
        if(FL_GENRES) url+='&fl_genres='+encodeURIComponent(FL_GENRES);
        url+='&fl_year_min='+FL_YEAR_MIN+'&fl_year_max='+FL_YEAR_MAX;
        url+='&fl_rating='+FL_RATING;
        nav(url);
      }}
    }}
    if(e.key==='Escape')closeSugs();
  }});

  document.addEventListener('click',function(e){{
    if(!e.target.closest('#w'))closeSugs();
  }});
</script></body></html>""", height=50, scrolling=False)

        # ── Filters ──────────────────────────────────────────────────────────
        _lang_display_names = [config.LANGUAGE_NAMES[lang] for lang in config.LANGUAGES]
        language_display, selected_genres, min_rating, year_range = render_filters(
            languages=_lang_display_names,
            genres=config.GENRES,
            default_min_rating=config.DEFAULT_MIN_RATING,
            default_min_year=config.DEFAULT_MIN_YEAR,
        )
        _lang_name_to_code = {v: k for k, v in config.LANGUAGE_NAMES.items()}
        language = _lang_name_to_code.get(language_display, language_display)

    # ── Mobile: open sidebar once when navigating to results ─────────────────
    # Only fires when a query is confirmed (not while typing, to avoid toggling
    # the sidebar closed while the user is actively using it).
    confirmed_on_results = bool(st.session_state.get("_confirmed_q"))
    if confirmed_on_results and not st.session_state.get("_mob_sidebar_opened"):
        st.session_state["_mob_sidebar_opened"] = True
        components.html(
            """<script>
            setTimeout(function(){
                var btn = window.parent.document.querySelector('[data-testid="collapsedControl"]');
                var sidebar = window.parent.document.querySelector('[data-testid="stSidebar"]');
                var isOpen = sidebar && getComputedStyle(sidebar).display !== 'none'
                             && sidebar.offsetWidth > 50;
                if (btn && !isOpen && window.parent.innerWidth < 900) btn.click();
            }, 300);
            </script>""",
            height=0,
        )
    else:
        st.session_state.pop("_mob_sidebar_opened", None)

    # Resolve API-compatible values
    genre    = selected_genres[0] if selected_genres else "All"
    min_year = int(year_range[0])
    max_year = int(year_range[1])

    # Final effective query (search is now handled in hero fragment → detail navigation)
    q = st.session_state.get("_confirmed_q") or ""

    # ── No search query → hero carousel + Recommendations + Trending + Discover ──
    if not q or len(q) < config.MIN_QUERY_LENGTH:
        _hero_carousel_fragment()

        render_section_divider()
        _render_recommendation_section()

        # Trending section
        trending = _trending_movies_data()
        if trending:
            render_section_divider()
            with st.spinner("Loading trending movies…"):
                trend_posters = _prefetch_poster_urls(trending)
            render_trending_row(trending, trend_posters)

        # Discover section — stable random selection (unchanged when filters move)
        pool = _featured_movies_pool()
        if "_featured_selection" not in st.session_state and pool:
            st.session_state["_featured_selection"] = random.sample(pool, min(12, len(pool)))
        featured = st.session_state.get("_featured_selection", [])
        if featured:
            render_section_divider()
            with st.spinner("Loading posters…"):
                feat_posters = _prefetch_poster_urls(featured)
            render_featured_grid(featured, feat_posters)

        hide_loader()
        return

    # ── Search ────────────────────────────────────────────────────────────────
    try:
        # min_rating from UI is 0–10; API (MovieLens) uses 0–5 → divide by 2
        rows = _search(
            q=q,
            language=language,
            genre=genre,
            min_rating=float(min_rating) / 2.0,
            min_year=min_year,
        )
    except Exception as exc:
        st.error(f"Search failed: {exc}")
        return

    # Client-side max_year filter
    if max_year < 2026:
        rows = [r for r in rows if _year_ok_max(r, max_year)]

    # Track search history
    if q and q not in st.session_state.get("_search_history", []):
        _add_to_history(q)

    # ── Empty state ────────────────────────────────────────────────────────────
    if not rows:
        has_filters = (
            min_rating > 0.0
            or min_year > config.DEFAULT_MIN_YEAR
            or max_year < 2026
            or genre != "All"
            or language != "All"
        )
        if render_empty_state(q, has_filters):
            # Signal render_filters() to reset widgets on next run (before instantiation)
            st.session_state["_do_reset_filters"] = True
            st.rerun()
        hide_loader()
        return

    # ── Back to home button ───────────────────────────────────────────────────
    if st.button("← Home", key="btn_back_home", type="secondary"):
        st.session_state["_confirmed_q"]   = None
        st.session_state["_last_raw_q"]    = ""
        st.session_state["_visible_count"] = _PAGE_SIZE
        st.session_state["_reset_search"]  = True
        st.session_state.pop("_featured_selection", None)  # refresh Discover on return
        st.rerun()

    # ── Sort + results count row ───────────────────────────────────────────────
    col_count, col_sort = st.columns([4, 2])
    n_total = len(rows)
    capped  = n_total >= config.SEARCH_LIMIT
    label   = f"{n_total}+ MOVIES FOUND" if capped else f'{n_total} MOVIE{"S" if n_total != 1 else ""} FOUND'
    with col_count:
        st.markdown(
            f'<p class="section-count">{label}</p>',
            unsafe_allow_html=True,
        )
    with col_sort:
        sort_by = st.selectbox(
            "Trier par", _SORT_OPTIONS,
            label_visibility="collapsed",
            key="_sort_by",
        )

    # Reset visible count when sort changes
    if sort_by != st.session_state.get("_last_sort"):
        st.session_state["_visible_count"] = _PAGE_SIZE
        st.session_state["_last_sort"] = sort_by

    rows = _sort_rows(rows, sort_by, q=q)

    # ── Load-more slice ────────────────────────────────────────────────────────
    if "_visible_count" not in st.session_state:
        st.session_state["_visible_count"] = _PAGE_SIZE

    visible_count = int(st.session_state["_visible_count"])
    visible_rows  = rows[:visible_count]

    # ── Prefetch poster URLs for visible slice ─────────────────────────────────
    with st.spinner("Loading posters…"):
        poster_urls = _prefetch_poster_urls(visible_rows)

    # ── Results grid ──────────────────────────────────────────────────────────
    df = pd.DataFrame(visible_rows)
    render_results_cards(df, poster_urls=poster_urls, return_q=q)

    # ── Load more button ───────────────────────────────────────────────────────
    if visible_count < n_total:
        remaining = n_total - visible_count
        st.markdown("<div style='height:1.25rem'></div>", unsafe_allow_html=True)
        _, col_btn, _ = st.columns([2, 2, 2])
        with col_btn:
            if st.button(
                f"Load more  ({remaining} remaining)",
                key="_load_more",
                use_container_width=True,
                type="secondary",
            ):
                st.session_state["_visible_count"] = visible_count + _PAGE_SIZE
                st.rerun()
    else:
        st.markdown(
            f'<p class="results-end">— {n_total} movie{"s" if n_total != 1 else ""} displayed —</p>',
            unsafe_allow_html=True,
        )

    hide_loader()


if __name__ == "__main__":
    main()
