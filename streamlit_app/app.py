"""app.py — Streamlit entry point.

Thin orchestrator: reads config, wires cached API calls, and delegates
all rendering to ui_components.

Architecture (2 layers as per assignment):
───────────────────────────────────────────
  Layer 1 — Database  : BigQuery  (accessed via Cloud Functions)
  Layer 2 — Logic+UI  : Streamlit (this file + api_client + ui_components)

Layer 2 internal modules:
  app.py              ← orchestration + Streamlit caching
  ├── config.py       ← Cloud Function URLs + UI constants
  ├── api_client.py   ← HTTP calls to Cloud Functions (pure Python, no Streamlit)
  └── ui_components.py← Streamlit rendering helpers (no HTTP, no SQL)
"""
import random
import time
from typing import Dict, List, Optional

import pandas as pd
import streamlit as st

import config
from api_client import fetch_autocomplete, fetch_details, fetch_search
from ui_components import (
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
    initial_sidebar_state="expanded",
)

# ── Hero TMDB IDs (carousel, shown when no active search) ─────────────────────
_HERO_IDS = [27205, 155, 157336, 680, 278]  # Inception, Dark Knight, Interstellar, Pulp Fiction, Shawshank

# ── Load-more page size ────────────────────────────────────────────────────────
_PAGE_SIZE = config.RESULTS_PER_LOAD  # 9

# ── Sort options ───────────────────────────────────────────────────────────────
_SORT_OPTIONS = ["Pertinence", "Titre A→Z", "Titre Z→A", "Année ↓", "Année ↑", "Note ↓", "Note ↑"]


# ── Cached API wrappers ───────────────────────────────────────────────────────

@st.cache_data(ttl=60)
def _autocomplete(prefix: str) -> List[Dict]:
    return fetch_autocomplete(
        config.MOVIES_AUTOCOMPLETE_URL, prefix, config.AUTOCOMPLETE_LIMIT
    )


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
    """
    Pool diversifié pour 'À découvrir'.
    Stratégie : requête large avec seuil bas, puis filtre client pour :
      - exclure les films avec trop peu d'avis (obscurs) ou trop (blockbusters omniprésents)
      - exclure les notes parfaites (>= 4.5/5 = 9/10) pour éviter toujours les mêmes tops
      - garder les films "bons mais pas parfaits" : 3.0–4.4 sur 5 (= 6.0–8.8/10)
    """
    try:
        results = fetch_search(
            config.MOVIES_SEARCH_URL,
            q="",           # chaîne vide → tous les films (LIKE '%%')
            language="All",
            genre="All",
            min_rating=2.5,  # ≥ 5/10 — on écarte les films vraiment mauvais
            min_year=1960,
            limit=300,
        )
        # Filtre diversité :
        #   rating_count 150–800 : film suffisamment connu (évite les documentaires ultra-niche
        #                          surreprésentés dans MovieLens mais inconnus sur TMDB)
        #   avg_rating   3.0–4.4 : bon film, mais pas note parfaite (évite les 10/10 répétitifs)
        filtered = [
            r for r in results
            if 150 <= int(r.get("rating_count") or 0) <= 800
            and 3.0 <= float(r.get("avg_rating") or 0) <= 4.4
        ]
        # Fallback si le filtre est trop restrictif
        return filtered if len(filtered) >= 20 else results
    except Exception:
        return []


@st.cache_data(ttl=3600)
def _trending_movies_data() -> List[Dict]:
    """Films de la dernière année du dataset, triés par nombre de votes décroissant."""
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

        # Détecter l'année la plus récente présente dans la base
        years = [int(r.get("release_year") or 0) for r in results if r.get("release_year")]
        if not years:
            return []
        max_year = max(years)

        # Films des 2 dernières années disponibles dans la base
        recent = [
            r for r in results
            if int(r.get("release_year") or 0) >= max_year - 2
        ]

        # Trier par nombre de votes décroissant
        recent = sorted(recent, key=lambda r: int(r.get("rating_count") or 0), reverse=True)
        return recent[:6]
    except Exception:
        return []


# ── Helpers ───────────────────────────────────────────────────────────────────

def _year_ok(suggestion: dict, min_year: int) -> bool:
    try:
        return int(suggestion.get("release_year", 0)) >= min_year
    except (ValueError, TypeError):
        return True


def _year_ok_max(row: dict, max_year: int) -> bool:
    """Client-side max year filter (API only supports min_year)."""
    try:
        return int(row.get("release_year", 9999)) <= max_year
    except (ValueError, TypeError):
        return True


def _sort_rows(rows: list, sort_by: str) -> list:
    """Sort results list based on selected option."""
    if sort_by == "Titre A→Z":
        return sorted(rows, key=lambda r: r.get("title", "").lower())
    if sort_by == "Titre Z→A":
        return sorted(rows, key=lambda r: r.get("title", "").lower(), reverse=True)
    if sort_by == "Année ↓":
        return sorted(rows, key=lambda r: r.get("release_year", 0), reverse=True)
    if sort_by == "Année ↑":
        return sorted(rows, key=lambda r: r.get("release_year", 9999))
    if sort_by == "Note ↓":
        return sorted(rows, key=lambda r: float(r.get("avg_rating") or 0), reverse=True)
    if sort_by == "Note ↑":
        return sorted(rows, key=lambda r: float(r.get("avg_rating") or 0))
    return rows  # "Pertinence" — keep API order


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
    """Hero carousel: auto-advances every 5 s (no manual prev/next buttons)."""
    n = len(_HERO_IDS)
    idx = (int(time.time()) // 5) % n

    tmdb_id = _HERO_IDS[idx]
    try:
        details = _details(tmdb_id)
    except Exception:
        details = {}

    render_hero_section(details, idx, n, tmdb_id=tmdb_id)


# ── Full-page detail view ─────────────────────────────────────────────────────

def _show_full_detail() -> None:
    """Renders the full-page movie detail and a back button."""
    inject_css()

    # _detail_return_q is set ONLY when coming from search results.
    # Its presence (even if empty string) means "go back to search".
    came_from_search = "_detail_return_q" in st.session_state
    back_label = "← Résultats" if came_from_search else "← Accueil"

    if st.button(back_label, key="_back_btn", type="secondary"):
        del st.session_state["detail_tmdb_id"]
        if came_from_search:
            return_q = st.session_state.pop("_detail_return_q", "")
            # Restore the search query via a flag read BEFORE widget creation
            st.session_state["_restore_search"] = return_q
        else:
            st.session_state.pop("_detail_return_q", None)
            # Coming from home: wipe search state + refresh À découvrir selection
            st.session_state["_confirmed_q"]  = None
            st.session_state["_last_raw_q"]   = ""
            st.session_state["_reset_search"] = True
            st.session_state.pop("_featured_selection", None)
        st.rerun()

    tmdb_id = st.session_state["detail_tmdb_id"]
    with st.spinner("Chargement des détails…"):
        try:
            details = _details(tmdb_id)
        except Exception as exc:
            st.error(f"Impossible de charger les détails : {exc}")
            return

    render_movie_detail_full(details)
    hide_loader()


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    inject_css()

    # ── Card click via query param (?detail=ID&src=home|search&q=QUERY) ─────────
    detail_param = st.query_params.get("detail")
    if detail_param:
        try:
            src     = st.query_params.get("src", "home")
            q_param = st.query_params.get("q", "")   # query survives page reload in URL
            st.query_params.clear()
            if src == "search" and q_param:
                st.session_state["_detail_return_q"] = q_param
            else:
                st.session_state.pop("_detail_return_q", None)
            st.session_state["detail_tmdb_id"] = int(detail_param)
            st.rerun()
        except (ValueError, TypeError):
            st.query_params.clear()

    # ── Hero CTA click via query param (?hero_tmdb=ID) ─────────────────────────
    hero_tmdb = st.query_params.get("hero_tmdb")
    if hero_tmdb:
        try:
            st.query_params.clear()
            st.session_state["app_started"] = True
            st.session_state.pop("_detail_return_q", None)  # coming from home
            st.session_state["detail_tmdb_id"] = int(hero_tmdb)
            st.rerun()
        except (ValueError, TypeError):
            st.query_params.clear()

    # ── Landing page supprimée — on arrive directement sur l'app ─────────────
    st.session_state["app_started"] = True

    # ── Full-page detail view ──────────────────────────────────────────────────
    if "detail_tmdb_id" in st.session_state:
        _show_full_detail()
        return

    # ── Sidebar ───────────────────────────────────────────────────────────────
    with st.sidebar:
        render_sidebar_header()

        # Search bar (in sidebar)
        # Handle navigation flags BEFORE the widget is instantiated
        if st.session_state.pop("_reset_search", False):
            # Returning to home: clear the search bar
            st.session_state["search_input"] = ""
        restore_q = st.session_state.pop("_restore_search", None)
        if restore_q is not None:
            # Returning from detail to search results: restore query in bar + state
            st.session_state["search_input"]  = restore_q
            st.session_state["_confirmed_q"]  = restore_q
            st.session_state["_last_raw_q"]   = restore_q
        raw_q: str = st.text_input(
            "",
            placeholder="Rechercher des films…",
            key="search_input",
            label_visibility="collapsed",
        )

        # Reset confirmed query when typed query changes
        if raw_q != st.session_state.get("_last_raw_q", ""):
            st.session_state["_confirmed_q"]  = None
            st.session_state["_last_raw_q"]   = raw_q
            st.session_state["_visible_count"] = _PAGE_SIZE

        # ── Autocomplete suggestions (while typing, no confirmed query yet) ───
        if raw_q and len(raw_q.strip()) >= 1 and st.session_state.get("_confirmed_q") is None:
            try:
                suggestions = _autocomplete(raw_q.strip())
                filtered = [
                    s for s in suggestions
                    if _year_ok(s, st.session_state.get("_filter_min_year", config.DEFAULT_MIN_YEAR))
                ][:8]
                if filtered:
                    for i, s in enumerate(filtered):
                        label = f"{s['title']}  ({s.get('release_year', '?')})"
                        if st.button(label, key=f"sug_{i}", use_container_width=True, type="secondary"):
                            st.session_state["_confirmed_q"]   = s["title"]
                            st.session_state["_visible_count"] = _PAGE_SIZE
                            _add_to_history(s["title"])
                            st.rerun()
            except Exception:
                pass

        # ── Search history (shown when search bar is empty) ────────────────
        elif not raw_q:
            history: List[str] = st.session_state.get("_search_history", [])
            if history:
                st.markdown(
                    '<p style="color:rgba(255,255,255,0.35);font-size:0.62rem;font-weight:700;'
                    'letter-spacing:0.1em;text-transform:uppercase;margin:0.7rem 0 0.3rem;">Récentes</p>',
                    unsafe_allow_html=True,
                )
                for h_q in history[:5]:
                    if st.button(f"↩  {h_q}", key=f"hist_{h_q}", use_container_width=True, type="secondary"):
                        st.session_state["_confirmed_q"]   = h_q
                        st.session_state["_visible_count"] = _PAGE_SIZE
                        st.rerun()

        # ── Filters ───────────────────────────────────────────────────────────
        language, selected_genres, min_rating, year_range = render_filters(
            languages=config.LANGUAGES,
            genres=config.GENRES,
            default_min_rating=config.DEFAULT_MIN_RATING,
            default_min_year=config.DEFAULT_MIN_YEAR,
        )

    # Resolve API-compatible values
    genre    = selected_genres[0] if selected_genres else "All"
    min_year = int(year_range[0])
    max_year = int(year_range[1])

    # Final effective query
    q = st.session_state.get("_confirmed_q") or raw_q.strip()

    # ── No search query → hero carousel + Tendances + À découvrir ────────────
    if not q or len(q) < config.MIN_QUERY_LENGTH:
        _hero_carousel_fragment()

        # Tendances section
        trending = _trending_movies_data()
        if trending:
            render_section_divider()
            with st.spinner("Chargement des tendances…"):
                trend_posters = _prefetch_poster_urls(trending)
            render_trending_row(trending, trend_posters)

        # À découvrir section — sélection aléatoire stable (ne change pas quand les filtres bougent)
        pool = _featured_movies_pool()
        if "_featured_selection" not in st.session_state and pool:
            st.session_state["_featured_selection"] = random.sample(pool, min(12, len(pool)))
        featured = st.session_state.get("_featured_selection", [])
        if featured:
            render_section_divider()
            with st.spinner("Chargement des affiches…"):
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
        st.error(f"Recherche échouée : {exc}")
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
    if st.button("← Accueil", key="btn_back_home", type="secondary"):
        st.session_state["_confirmed_q"]   = None
        st.session_state["_last_raw_q"]    = ""
        st.session_state["_visible_count"] = _PAGE_SIZE
        st.session_state["_reset_search"]  = True
        st.session_state.pop("_featured_selection", None)  # refresh À découvrir on return
        st.rerun()

    # ── Sort + results count row ───────────────────────────────────────────────
    col_count, col_sort = st.columns([4, 2])
    n_total = len(rows)
    with col_count:
        st.markdown(
            f'<p style="color:rgba(255,255,255,0.35);font-size:0.68rem;font-weight:700;'
            f'letter-spacing:0.12em;text-transform:uppercase;margin:0.6rem 0 0;">'
            f'{n_total} FILM{"S" if n_total != 1 else ""} TROUVÉ{"S" if n_total != 1 else ""}</p>',
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

    rows = _sort_rows(rows, sort_by)

    # ── Load-more slice ────────────────────────────────────────────────────────
    if "_visible_count" not in st.session_state:
        st.session_state["_visible_count"] = _PAGE_SIZE

    visible_count = int(st.session_state["_visible_count"])
    visible_rows  = rows[:visible_count]

    # ── Prefetch poster URLs for visible slice ─────────────────────────────────
    with st.spinner("Chargement des affiches…"):
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
                f"Charger plus  ({remaining} restant{'s' if remaining > 1 else ''})",
                key="_load_more",
                use_container_width=True,
                type="secondary",
            ):
                st.session_state["_visible_count"] = visible_count + _PAGE_SIZE
                st.rerun()
    else:
        st.markdown(
            f'<p style="color:rgba(255,255,255,0.2);font-size:0.8rem;text-align:center;'
            f'margin-top:1.5rem;">— {n_total} film{"s" if n_total != 1 else ""} affiché{"s" if n_total != 1 else ""} —</p>',
            unsafe_allow_html=True,
        )

    hide_loader()


if __name__ == "__main__":
    main()
