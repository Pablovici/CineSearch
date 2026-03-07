"""ui_components.py — Streamlit rendering helpers.

Pure UI layer — no HTTP calls, no config imports.
Design: CinéSearch — deep navy/black, glassmorphic cards, indigo accents,
        auto-rotating hero, À découvrir section, visual badges,
        full-page structured detail view, load-more pagination.
"""
from typing import Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st


# ── Genre gradients (poster fallback) ─────────────────────────────────────────
_GENRE_GRADIENTS = {
    "action":      "linear-gradient(160deg,#3a0000,#1a0000)",
    "adventure":   "linear-gradient(160deg,#0a2a1a,#0a1a2a)",
    "animation":   "linear-gradient(160deg,#00143a,#001428)",
    "comedy":      "linear-gradient(160deg,#2a1500,#1a1000)",
    "crime":       "linear-gradient(160deg,#0a0014,#07000e)",
    "documentary": "linear-gradient(160deg,#0a1a1a,#0a0a14)",
    "drama":       "linear-gradient(160deg,#0a0a28,#140014)",
    "fantasy":     "linear-gradient(160deg,#14003a,#0a0028)",
    "horror":      "linear-gradient(160deg,#0a0a0a,#14000a)",
    "romance":     "linear-gradient(160deg,#280014,#1a000a)",
    "sci-fi":      "linear-gradient(160deg,#00001e,#0a001e)",
    "thriller":    "linear-gradient(160deg,#050510,#050508)",
    "war":         "linear-gradient(160deg,#0f0f14,#050510)",
    "western":     "linear-gradient(160deg,#1a1000,#0f0800)",
    "default":     "linear-gradient(160deg,#0d1117,#080808)",
}


# ── CSS ───────────────────────────────────────────────────────────────────────
_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@300;400;600;700;900&display=swap');

/* ── Global ── */
.stApp, [data-testid="stAppViewContainer"] {
    background: #0a0a0a !important;
    color: #fff;
    font-family: 'Montserrat', -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
* { font-family: 'Montserrat', -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif !important; }
.block-container { padding-top: 1.25rem !important; padding-bottom: 3rem !important; }
header[data-testid="stHeader"] { background: transparent !important; }
hr { border-color: rgba(255,255,255,0.07) !important; }

/* ── Sidebar ── */
[data-testid="stSidebar"] {
    background: rgba(6,6,8,0.99) !important;
    border-right: 1px solid rgba(255,255,255,0.06) !important;
    min-width: 300px !important;
    max-width: 300px !important;
    width: 300px !important;
}
[data-testid="stSidebar"] > div:first-child {
    padding-top: 1.25rem !important;
    min-width: 300px !important;
    width: 300px !important;
}
[data-testid="stSidebar"] h1,[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3,[data-testid="stSidebar"] p { color: #fff !important; }

/* ── Search input ── */
[data-testid="stTextInput"] input {
    background: rgba(22,22,26,0.8) !important;
    border: 1px solid rgba(255,255,255,0.09) !important;
    color: #fff !important;
    border-radius: 12px !important;
    font-size: 0.95rem !important;
    padding: 0 1.1rem !important;
    height: 46px !important;
    caret-color: #fff;
    transition: all 0.3s ease !important;
}
[data-testid="stTextInput"] input:focus {
    border-color: rgba(255,255,255,0.28) !important;
    box-shadow: 0 0 12px rgba(255,255,255,0.06) !important;
    background: rgba(28,28,32,0.9) !important;
}
[data-testid="stTextInput"] input::placeholder { color: rgba(255,255,255,0.25) !important; }

/* ── Selectbox ── */
[data-testid="stSelectbox"] > div > div {
    background: rgba(18,18,22,0.8) !important;
    border: 1px solid rgba(255,255,255,0.08) !important;
    color: #fff !important; border-radius: 8px !important;
}

/* ── Slider ── */
[data-testid="stSlider"] [role="slider"] { background: rgba(255,255,255,0.85) !important; border: none !important; }
[data-testid="stSlider"] [data-testid="stThumbValue"] { color: rgba(255,255,255,0.55) !important; }

/* ── Checkboxes ── */
[data-testid="stCheckbox"] label { color: rgba(255,255,255,0.6) !important; font-size: 0.85rem !important; }
[data-testid="stCheckbox"] label:hover { color: #fff !important; }

/* ── Metrics ── */
[data-testid="metric-container"] {
    background: rgba(14,14,16,0.6); border: 1px solid rgba(255,255,255,0.06);
    border-radius: 10px; padding: 0.75rem 1rem;
}
[data-testid="metric-container"] label { color: rgba(255,255,255,0.38) !important; font-size: 0.78rem !important; }
[data-testid="metric-container"] [data-testid="stMetricValue"] { color: #fff !important; font-weight: 700; }

/* ── Landing page ── */
.landing-wrap { display:flex; flex-direction:column; align-items:center; justify-content:center; min-height:52vh; text-align:center; }
.landing-ring { background:rgba(255,255,255,0.05); padding:1.5rem; border-radius:50%; border:1px solid rgba(255,255,255,0.1); margin-bottom:2rem; box-shadow:0 0 40px rgba(255,255,255,0.04); font-size:3rem; line-height:1; }
.landing-title { font-size:4.5rem; font-weight:900; line-height:1; color:#fff; margin-bottom:0; letter-spacing:-0.04em; }
.landing-sub { font-size:1.15rem; color:rgba(255,255,255,0.38); max-width:500px; margin:1.25rem auto 2.5rem; line-height:1.65; }
.landing-genre-label { color:rgba(255,255,255,0.28); font-size:0.62rem; font-weight:700; letter-spacing:0.14em; text-transform:uppercase; text-align:center; margin:2.5rem 0 1rem; }
/* Genre buttons in landing — override the global secondary style */
.landing-genre-row [data-testid="baseButton-secondary"] {
    border-radius: 12px !important;
    height: 64px !important;
    font-size: 0.78rem !important;
    font-weight: 600 !important;
    background: rgba(255,255,255,0.04) !important;
    border: 1px solid rgba(255,255,255,0.09) !important;
    color: rgba(255,255,255,0.75) !important;
    transition: all 0.2s !important;
    flex-direction: column !important;
    gap: 4px !important;
}
.landing-genre-row [data-testid="baseButton-secondary"]:hover {
    background: rgba(255,255,255,0.1) !important;
    border-color: rgba(255,255,255,0.22) !important;
    color: #fff !important;
    transform: translateY(-2px) !important;
}

/* ── Hero section ── */
.hero-wrap { position:relative; width:100%; border-radius:18px; overflow:visible; margin-bottom:0.75rem; min-height:460px; }
/* Separate clip layer so blur/scale stay bounded but content can overflow */
.hero-bg-container { position:absolute; inset:0; border-radius:18px; overflow:hidden; }
.hero-bg { position:absolute; inset:0; background-size:cover; background-position:center top; filter:blur(6px) brightness(0.48); transform:scale(1.05); }
.hero-grad { position:absolute; inset:0; background:linear-gradient(90deg,rgba(0,0,0,0.82) 0%,rgba(0,0,0,0.50) 52%,rgba(0,0,0,0.10) 100%); }
.hero-content { position:relative; z-index:2; padding:4rem 3.5rem 3rem; max-width:60%; }
.hero-genre { display:inline-block; background:rgba(255,255,255,0.12); color:rgba(255,255,255,0.75); border:1px solid rgba(255,255,255,0.18); border-radius:4px; padding:0.22rem 0.65rem; font-size:0.68rem; font-weight:700; letter-spacing:0.12em; text-transform:uppercase; margin-bottom:0.9rem; }
.hero-title { font-size:3rem; font-weight:800; color:#fff; line-height:1.05; margin-bottom:0.9rem; letter-spacing:-0.03em; }
.hero-overview { font-size:0.87rem; color:rgba(255,255,255,0.55); line-height:1.75; margin-bottom:0; max-width:460px; }
/* CTA button — rendered inside .hero-content, just below overview text */
.hero-cta-btn { display:inline-block; background:transparent; border:1px solid rgba(255,255,255,0.6); color:#fff !important; padding:0.75rem 2.2rem; border-radius:30px; font-weight:600; font-size:0.9rem; cursor:pointer; margin-top:1.75rem; text-decoration:none !important; letter-spacing:0.02em; transition:background 0.2s,border-color 0.2s; }
.hero-cta-btn:visited { color:#fff !important; text-decoration:none !important; }
.hero-cta-btn:active { color:#fff !important; text-decoration:none !important; }
.hero-cta-btn:hover { background:rgba(255,255,255,0.1); border-color:#fff; color:#fff !important; text-decoration:none !important; }
.hero-dots { position:absolute; bottom:1.5rem; left:50%; transform:translateX(-50%); display:flex; gap:0.5rem; z-index:3; }
.hero-dot { height:3px; width:18px; border-radius:2px; background:rgba(255,255,255,0.3); transition:all 0.3s ease; }
.hero-dot.active { background:#fff; width:28px; }

/* ── Carousel prev/next arrow buttons (3-column layout: side cols contain arrows) ── */
[data-testid="stHorizontalBlock"]:has(.hero-wrap) [data-testid="stColumn"]:first-child [data-testid="baseButton-secondary"],
[data-testid="stHorizontalBlock"]:has(.hero-wrap) [data-testid="stColumn"]:last-child  [data-testid="baseButton-secondary"] {
    border-radius: 50% !important;
    width: 52px !important;
    height: 52px !important;
    min-width: unset !important;
    padding: 0 !important;
    background: rgba(8,8,12,0.6) !important;
    border: 1px solid rgba(255,255,255,0.22) !important;
    color: #fff !important;
    font-size: 1.4rem !important;
    font-weight: 300 !important;
    line-height: 1 !important;
    backdrop-filter: blur(12px) !important;
    box-shadow: 0 4px 20px rgba(0,0,0,0.45) !important;
    margin: 0 auto !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
}
[data-testid="stHorizontalBlock"]:has(.hero-wrap) [data-testid="stColumn"]:first-child [data-testid="baseButton-secondary"]:hover,
[data-testid="stHorizontalBlock"]:has(.hero-wrap) [data-testid="stColumn"]:last-child  [data-testid="baseButton-secondary"]:hover {
    background: rgba(255,255,255,0.14) !important;
    border-color: rgba(255,255,255,0.38) !important;
    transform: none !important;
}


/* ── Section divider ── */
.section-divider { border: none; border-top: 1px solid rgba(255,255,255,0.07); margin: 1.75rem 0 0; }

/* ── Movie card ── */
.mc-item-link { text-decoration:none; display:block; color:inherit; }
.mc-card { border-radius:14px; overflow:hidden; background:rgba(14,14,16,0.9); border:1px solid rgba(255,255,255,0.06); cursor:pointer; position:relative; transition:transform 0.3s ease,border-color 0.3s,box-shadow 0.3s; margin-bottom:0.5rem; }
.mc-item-link:hover .mc-card { transform:translateY(-5px); border-color:rgba(255,255,255,0.15); box-shadow:0 14px 32px rgba(0,0,0,0.6); }
.mc-poster { width:100%; aspect-ratio:2/3; object-fit:cover; display:block; transition:transform 0.5s ease; }
.mc-item-link:hover .mc-poster { transform:scale(1.05); }
.mc-poster-fallback { width:100%; aspect-ratio:2/3; display:flex; align-items:center; justify-content:center; font-size:2.5rem; color:rgba(255,255,255,0.1); }
.mc-title { color:#fff; font-size:0.85rem; font-weight:600; line-height:1.3; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; margin:0.5rem 0 0.12rem; }
.mc-meta { color:rgba(255,255,255,0.35); font-size:0.73rem; margin-bottom:0.35rem; }

/* ── Badges (on cards) ── */
.mc-badge { position:absolute; top:0.45rem; left:0.45rem; z-index:2; border-radius:4px; padding:0.15rem 0.5rem; font-size:0.6rem; font-weight:700; letter-spacing:0.06em; text-transform:uppercase; }

/* ── Badge types (detail panel) ── */
.badge-rating { background:rgba(250,204,21,0.12); color:#FACC15; border:1px solid rgba(250,204,21,0.22); }
.badge-date   { background:rgba(255,255,255,0.05); color:#E2E8F0; border:1px solid rgba(255,255,255,0.08); }
.badge-genre  { background:rgba(255,255,255,0.07); color:rgba(255,255,255,0.78); border:1px solid rgba(255,255,255,0.1); }
.badge { display:inline-block; padding:5px 12px; border-radius:7px; font-size:0.78rem; font-weight:700; margin:0.1rem 0.2rem 0.1rem 0; text-transform:uppercase; letter-spacing:0.04em; }

/* ── Buttons (global) — transparent, white border, white text ── */
/* Primary */
.stApp [data-testid="baseButton-primary"],
.stApp [data-testid="baseButton-primary"]:not([disabled]) {
    background: rgba(0,0,0,0) !important;
    background-color: rgba(0,0,0,0) !important;
    border: 1.5px solid rgba(255,255,255,0.85) !important;
    color: #fff !important;
    font-weight: 600 !important;
    border-radius: 8px !important;
    box-shadow: none !important;
    letter-spacing: 0.02em !important;
    transition: background 0.18s, border-color 0.18s !important;
}
.stApp [data-testid="baseButton-primary"]:hover {
    background: rgba(255,255,255,0.1) !important;
    border-color: #fff !important;
    transform: none !important;
}
.stApp [data-testid="baseButton-primary"] p,
.stApp [data-testid="baseButton-primary"] span,
.stApp [data-testid="baseButton-primary"] div {
    color: #fff !important;
    background: transparent !important;
}
/* Secondary */
.stApp [data-testid="baseButton-secondary"],
.stApp [data-testid="baseButton-secondary"]:not([disabled]),
.stApp .stButton > button {
    background: rgba(0,0,0,0) !important;
    background-color: rgba(0,0,0,0) !important;
    border: 1px solid rgba(255,255,255,0.55) !important;
    border-radius: 8px !important;
    color: #fff !important;
    font-weight: 500 !important;
    font-size: 0.83rem !important;
    box-shadow: none !important;
    transition: background 0.15s, border-color 0.15s !important;
}
.stApp [data-testid="baseButton-secondary"]:hover,
.stApp .stButton > button:hover {
    background: rgba(255,255,255,0.08) !important;
    border-color: rgba(255,255,255,0.85) !important;
    transform: none !important;
}
.stApp [data-testid="baseButton-secondary"] p,
.stApp [data-testid="baseButton-secondary"] span,
.stApp [data-testid="baseButton-secondary"] div,
.stApp .stButton > button p {
    color: #fff !important;
    background: transparent !important;
}

/* ── Detail full page ── */
.detail-hero { position:relative; width:100%; border-radius:18px; overflow:hidden; margin-bottom:2rem; min-height:200px; }
.detail-hero-bg { position:absolute; inset:0; background-size:cover; background-position:center; filter:blur(15px) brightness(0.16); transform:scale(1.08); }
.detail-hero-grad { position:absolute; inset:0; background:linear-gradient(to bottom,rgba(0,0,0,0.5) 0%,rgba(10,10,10,0.97) 100%); }
.detail-hero-content { position:relative; z-index:2; padding:3rem 3.5rem 2.5rem; }
.detail-hero-title { font-size:2.5rem; font-weight:800; color:#fff; line-height:1.1; margin-bottom:0.35rem; }
.detail-hero-tagline { color:rgba(255,255,255,0.38); font-style:italic; font-size:0.95rem; }
.detail-overview { color:rgba(200,210,225,0.85); font-size:0.87rem; line-height:1.8; margin:0.5rem 0; }
.detail-section-label { color:rgba(255,255,255,0.28); font-size:0.62rem; font-weight:700; letter-spacing:0.12em; text-transform:uppercase; margin:1rem 0 0.5rem; }
.eco-item { background:rgba(14,14,16,0.7); border:1px solid rgba(255,255,255,0.06); border-radius:10px; padding:0.75rem 1rem; }
.eco-label { color:rgba(148,163,184,0.6); font-size:0.62rem; text-transform:uppercase; letter-spacing:0.08em; }
.eco-value { color:#fff; font-size:1.1rem; font-weight:700; margin-top:0.2rem; }
.cast-member { padding:0.4rem 0; border-bottom:1px solid rgba(255,255,255,0.04); font-size:0.82rem; }

/* ── Info boxes ── */
[data-testid="stInfo"] { background:rgba(14,14,16,0.6) !important; border-color:rgba(255,255,255,0.07) !important; color:rgba(255,255,255,0.6) !important; border-radius:10px !important; }

/* ── Suppress layout artifact of height-0 components.html iframes (used for JS injection) ── */
[data-testid="stCustomComponentV1"] {
    display: none !important;
    height: 0 !important;
    min-height: 0 !important;
    margin: 0 !important;
    padding: 0 !important;
}

/* ══════════════════════════════════════════════════════
   RESPONSIVE — MOBILE (≤ 768 px)
   ══════════════════════════════════════════════════════ */
@media screen and (max-width: 768px) {

    /* ── Hero : réduction des tailles ── */
    .hero-wrap    { min-height: 240px !important; border-radius: 12px !important; }
    .hero-content { padding: 1.25rem 1.1rem 1rem !important; max-width: 88% !important; }
    .hero-genre   { font-size: 0.56rem !important; padding: 0.14rem 0.45rem !important;
                    margin-bottom: 0.5rem !important; }
    .hero-title   { font-size: 1.4rem !important; margin-bottom: 0.45rem !important; }
    .hero-overview{ font-size: 0.74rem !important; line-height: 1.5 !important; }
    .hero-cta-btn { padding: 0.5rem 1.1rem !important; font-size: 0.74rem !important;
                    margin-top: 0.85rem !important; border-radius: 20px !important; }
    .hero-dots    { bottom: 0.6rem !important; }
    .hero-dot     { height: 2px !important; width: 12px !important; }
    .hero-dot.active { width: 18px !important; }

    /* ── Grilles de cartes : scroll horizontal façon Netflix ──
       Les colonnes Streamlit s'empilent sur mobile par défaut.
       On force un scroll horizontal avec largeur fixe par carte. ── */
    [data-testid="stHorizontalBlock"]:has(.mc-card) {
        overflow-x: auto !important;
        flex-wrap: nowrap !important;
        -webkit-overflow-scrolling: touch !important;
        scrollbar-width: none !important;
        padding-bottom: 6px !important;
    }
    [data-testid="stHorizontalBlock"]:has(.mc-card)::-webkit-scrollbar {
        display: none !important;
    }
    /* Chaque colonne de carte : largeur fixe 105 px ≈ 3–4 cartes visibles */
    [data-testid="stHorizontalBlock"]:has(.mc-card) > [data-testid="stColumn"] {
        min-width: 105px !important;
        max-width: 105px !important;
        flex: 0 0 105px !important;
        width: 105px !important;
    }

    /* ── Texte sous les cartes ── */
    .mc-card  { border-radius: 9px !important; }
    .mc-title { font-size: 0.68rem !important; margin: 0.28rem 0 0.06rem !important; }
    .mc-meta  { font-size: 0.6rem !important; margin-bottom: 0.2rem !important; }
    .mc-badge { font-size: 0.5rem !important; padding: 0.08rem 0.28rem !important; }

    /* ── Page de détail : réduction de padding/titres ── */
    .detail-hero-content { padding: 1.5rem 1.25rem 1.25rem !important; }
    .detail-hero-title   { font-size: 1.6rem !important; }
    .detail-hero-tagline { font-size: 0.82rem !important; }
}

</style>
"""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _genre_gradient(genres_str: str) -> str:
    if not genres_str:
        return _GENRE_GRADIENTS["default"]
    first = genres_str.split("|")[0].lower().strip()
    return _GENRE_GRADIENTS.get(first, _GENRE_GRADIENTS["default"])


def _section_label(text: str) -> None:
    st.markdown(
        f'<p style="color:rgba(255,255,255,0.42);font-size:0.68rem;font-weight:600;'
        f'letter-spacing:0.1em;text-transform:uppercase;margin:0.85rem 0 0.4rem;">'
        f'{text}</p>',
        unsafe_allow_html=True,
    )


def _get_badge(avg_rating: float, rating_count: int, release_year: int
               ) -> Optional[Tuple[str, str, str, str]]:
    """Return (label, color, bg, border) for the most relevant badge, or None."""
    if avg_rating >= 4.3:
        return ("TOP RATED", "#FACC15", "rgba(250,204,21,0.18)", "rgba(250,204,21,0.35)")
    if rating_count >= 500:
        return ("POPULAR",   "#60A5FA", "rgba(96,165,250,0.18)",  "rgba(96,165,250,0.35)")
    if release_year >= 2015:
        return ("RÉCENT",    "#34D399", "rgba(52,211,153,0.18)",  "rgba(52,211,153,0.35)")
    if release_year and release_year <= 1985:
        return ("CLASSIQUE", "#A78BFA", "rgba(167,139,250,0.18)", "rgba(167,139,250,0.35)")
    return None


# ── Page-level ────────────────────────────────────────────────────────────────

_LOADING_SCREEN = """
<div id="cine-loader">
    <div class="cine-loader-logo">CinéSearch</div>
    <div class="cine-loader-bar"><div class="cine-loader-fill"></div></div>
    <div class="cine-loader-sub">Chargement en cours…</div>
</div>
<style>
#cine-loader {
    position: fixed; top: 0; left: 0;
    width: 100vw; height: 100vh;
    background: #0a0a0a; z-index: 2147483647;
    display: flex; flex-direction: column; align-items: center;
    justify-content: center; gap: 1.5rem;
    font-family: 'Montserrat', -apple-system, sans-serif;
    /* Fallback de sécurité : disparaît après 8s si le JS ne se déclenche pas */
    animation: cine-hide 0.6s ease 8s forwards;
}
.cine-loader-logo {
    font-size: 2.4rem; font-weight: 800; color: #fff;
    letter-spacing: -0.03em;
}
.cine-loader-bar {
    width: 160px; height: 1.5px; background: rgba(255,255,255,0.12);
    border-radius: 2px; overflow: hidden;
}
.cine-loader-fill {
    height: 100%; width: 0%; background: #fff;
    animation: cine-load 1.8s cubic-bezier(0.4,0,0.2,1) forwards;
}
.cine-loader-sub {
    font-size: 0.72rem; color: rgba(255,255,255,0.28);
    letter-spacing: 0.18em; text-transform: uppercase; font-weight: 500;
}
@keyframes cine-load { from { width: 0% } to { width: 100% } }
@keyframes cine-hide {
    0%   { opacity: 1; pointer-events: all; }
    99%  { opacity: 0; pointer-events: all; }
    100% { opacity: 0; pointer-events: none; visibility: hidden; }
}
</style>
"""


def inject_css() -> None:
    """
    Injecte le CSS global.
    Le loader plein écran n'est injecté qu'une seule fois par session (premier chargement).
    Les re-runs Streamlit (changements de filtres, etc.) ne réaffichent pas le loader.
    """
    if "_loader_shown" not in st.session_state:
        st.session_state["_loader_shown"] = True
        st.markdown(_CSS + _LOADING_SCREEN, unsafe_allow_html=True)
    else:
        st.markdown(_CSS, unsafe_allow_html=True)


def hide_loader() -> None:
    """
    Cache le loader plein écran via JavaScript.
    À appeler EN FIN de chaque chemin de rendu, une fois que tout le contenu est prêt.
    Utilise st.components.v1.html (height=0) pour exécuter du JS dans Streamlit.
    Le CSS [data-testid="stCustomComponentV1"] supprime tout artefact visuel.
    """
    import streamlit.components.v1 as components
    components.html(
        """<script>
        (function() {
            function doHide() {
                var el = window.parent.document.getElementById('cine-loader');
                if (!el) return;
                el.style.transition = 'opacity 0.5s ease';
                el.style.opacity = '0';
                setTimeout(function() {
                    el.style.visibility = 'hidden';
                    el.style.pointerEvents = 'none';
                }, 500);
            }
            // Petit délai pour laisser React terminer son paint
            setTimeout(doHide, 200);
        })();
        </script>""",
        height=0,
        scrolling=False,
    )


def render_sidebar_header() -> None:
    """CinéSearch branding only — no nav items."""
    st.markdown(
        """
        <div style="padding:0.1rem 0 1rem;">
            <div style="font-size:1.45rem;font-weight:700;color:#fff;
                        letter-spacing:-0.5px;line-height:1;margin:0;">CinéSearch</div>
            <div style="font-size:0.74rem;color:rgba(255,255,255,0.38);
                        margin:0.35rem 0 0;line-height:1;">Découvrez des films</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ── Landing page ──────────────────────────────────────────────────────────────


def render_landing_page(genres: Optional[List[str]] = None) -> bool:
    """
    Splash screen.
    Returns True when the user clicks the main CTA.
    """
    st.markdown(
        """
        <div class="landing-wrap">
            <div class="landing-ring">C</div>
            <div class="landing-title">CinéSearch</div>
            <div class="landing-sub">
                Plongez dans l'univers infini du cinéma.<br>
                Recherche intelligente &amp; expérience immersive.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Main CTA ──────────────────────────────────────────────────────────────
    _, col_btn, _ = st.columns([2, 1.2, 2])
    with col_btn:
        if st.button("Explorer le catalogue", use_container_width=True, type="primary"):
            return True

    return False


# ── Filters ────────────────────────────────────────────────────────────────────

def render_filters(
    languages: List[str],
    genres: List[str],
    default_min_rating: float = 0.0,
    default_min_year: int = 1900,
) -> Tuple[str, List[str], float, Tuple[int, int]]:
    """
    Sidebar filters.
    Rating scale: 0.0–10.0 (display scale, step 0.5).
    The caller must divide min_rating by 2 before sending it to the API (0–5 MovieLens scale).
    Returns (language, selected_genres, min_rating, (min_year, max_year)).
    """
    st.markdown(
        '<div style="height:1px;background:rgba(255,255,255,0.08);margin:0.6rem 0 0.75rem;"></div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<p style="color:rgba(255,255,255,0.45);font-size:0.65rem;font-weight:700;'
        'letter-spacing:0.1em;text-transform:uppercase;margin:0 0 0.6rem;">Filtres</p>',
        unsafe_allow_html=True,
    )
    reset = st.button("↺  Réinitialiser les filtres", key="_reset_filters",
                      use_container_width=True, type="secondary")

    # Appliquer le reset AVANT la création des widgets (bouton sidebar ou flag externe)
    if reset:
        st.session_state["_do_reset_filters"] = True
        st.rerun()

    if st.session_state.pop("_do_reset_filters", False):
        st.session_state["_fl_lang"]   = languages[0] if languages else "All"
        st.session_state["_fl_year"]   = (default_min_year, 2026)
        st.session_state["_fl_rating"] = 0.0
        for g in genres:
            if g != "All":
                st.session_state[f"_fl_genre_{g}"] = False

    # Language
    _section_label("Langue")
    language = st.selectbox("Language", languages, label_visibility="collapsed", key="_fl_lang")

    # Genres (checkboxes — "All" excluded, unchecked = All)
    _section_label("Genres")
    genre_options = [g for g in genres if g != "All"]
    selected_genres: List[str] = []
    for g in genre_options:
        if st.checkbox(g, key=f"_fl_genre_{g}"):
            selected_genres.append(g)

    # Year range (MovieLens: 1902–2026)
    _section_label("Année")
    year_range: Tuple[int, int] = st.slider(
        "Year range", min_value=1900, max_value=2026,
        value=(default_min_year, 2026), step=1,
        label_visibility="collapsed", key="_fl_year",
    )

    # Min rating (displayed as 0–10; internally the API uses 0–5 so caller divides by 2)
    _section_label("Note minimale (0–10)")
    min_rating: float = st.slider(
        "Min rating", min_value=0.0, max_value=10.0,
        value=default_min_rating, step=0.5,
        label_visibility="collapsed", key="_fl_rating",
        format="%.1f ★",
    )

    st.session_state["_filter_min_year"] = int(year_range[0])
    return language, selected_genres, min_rating, year_range


# ── Hero section (no buttons — navigation handled externally) ──────────────────

def render_hero_section(details: Dict, current_idx: int, total_count: int,
                        tmdb_id: Optional[int] = None) -> None:
    """Render the cinematic hero card with CTA button inside the card."""
    poster_url  = details.get("poster_url", "")
    title       = details.get("title", "Unknown")
    overview    = details.get("overview") or ""
    if len(overview) > 200:
        overview = overview[:200] + "…"
    genres_list: List[str] = details.get("genres", [])
    genre_label = genres_list[0] if genres_list else "Film"

    dots_html = "".join(
        f'<div class="hero-dot{"" if i != current_idx else " active"}"></div>'
        for i in range(total_count)
    )

    # CTA button: <a> tag with query param so click is handled by main()
    cta_html = ""
    if tmdb_id:
        cta_html = f'<a class="hero-cta-btn" href="?hero_tmdb={tmdb_id}" target="_self">&#9654;&nbsp; En savoir plus</a>'

    st.markdown(
        f"""
        <div class="hero-wrap">
            <div class="hero-bg-container">
                <div class="hero-bg" style="background-image:url('{poster_url}');"></div>
                <div class="hero-grad"></div>
            </div>
            <div class="hero-content">
                <div class="hero-genre">{genre_label}</div>
                <div class="hero-title">{title}</div>
                <div class="hero-overview">{overview}</div>
                {cta_html}
            </div>
            <div class="hero-dots">{dots_html}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ── Featured grid (À découvrir) ────────────────────────────────────────────────

def render_featured_grid(movies: List[Dict], poster_urls: Dict[int, str]) -> None:
    """Render the '12 À découvrir' section below the hero."""
    st.markdown(
        '<h3 style="color:#fff;font-size:1.25rem;font-weight:700;'
        'margin:1.75rem 0 1rem;letter-spacing:-0.01em;">À découvrir</h3>',
        unsafe_allow_html=True,
    )

    n_cols = 6
    cols = st.columns(n_cols, gap="small")

    for i, movie in enumerate(movies[:12]):
        title  = str(movie.get("title", ""))
        year   = int(movie.get("release_year", 0)) if movie.get("release_year") else 0
        rating = float(movie.get("avg_rating") or 0)
        votes  = int(movie.get("rating_count") or 0)

        tmdb_id = None
        try:
            raw = movie.get("tmdbId")
            if raw is not None and not pd.isna(raw):
                tmdb_id = int(raw)
        except (ValueError, TypeError):
            pass

        poster = poster_urls.get(tmdb_id) if tmdb_id else None
        badge_info = _get_badge(rating, votes, year) if year else None
        badge_html = ""
        if badge_info:
            label, color, bg, border = badge_info
            badge_html = (
                f'<span class="mc-badge" style="background:{bg};color:{color};'
                f'border:1px solid {border};">{label}</span>'
            )

        with cols[i % n_cols]:
            if poster:
                inner = f'<img class="mc-poster" src="{poster}" alt="{title}">'
            else:
                gradient = _genre_gradient(str(movie.get("genres", "")))
                inner = f'<div class="mc-poster-fallback" style="background:{gradient};"></div>'

            link_open = f'<a class="mc-item-link" href="?detail={tmdb_id}&src=home" target="_self">' if tmdb_id else '<div class="mc-item-link">'
            link_close = '</a>' if tmdb_id else '</div>'
            st.markdown(
                f'{link_open}'
                f'<div class="mc-card">{badge_html}{inner}</div>'
                f'{link_close}'
                f'<div class="mc-title">{title}</div>'
                f'<div class="mc-meta">★ {rating*2:.1f} · {year if year else "—"}</div>',
                unsafe_allow_html=True,
            )


def render_section_divider() -> None:
    """Thin horizontal rule between sections."""
    st.markdown('<hr class="section-divider">', unsafe_allow_html=True)


# ── Trending row (top-rated recent films) ─────────────────────────────────────

def render_trending_row(movies: List[Dict], poster_urls: Dict[int, str]) -> None:
    """Render a single horizontal row of up to 6 top-rated recent films."""
    st.markdown(
        '<h3 style="color:#fff;font-size:1.25rem;font-weight:700;'
        'margin:1.75rem 0 1rem;letter-spacing:-0.01em;">Tendances</h3>',
        unsafe_allow_html=True,
    )

    display = movies[:6]
    if not display:
        return

    n_cols = len(display)
    cols = st.columns(n_cols, gap="small")

    for i, movie in enumerate(display):
        title  = str(movie.get("title", ""))
        year   = int(movie.get("release_year", 0)) if movie.get("release_year") else 0
        rating = float(movie.get("avg_rating") or 0)
        votes  = int(movie.get("rating_count") or 0)

        tmdb_id = None
        try:
            raw = movie.get("tmdbId")
            if raw is not None and not pd.isna(raw):
                tmdb_id = int(raw)
        except (ValueError, TypeError):
            pass

        poster = poster_urls.get(tmdb_id) if tmdb_id else None
        badge_info = _get_badge(rating, votes, year) if year else None
        badge_html = ""
        if badge_info:
            label, color, bg, border = badge_info
            badge_html = (
                f'<span class="mc-badge" style="background:{bg};color:{color};'
                f'border:1px solid {border};">{label}</span>'
            )

        with cols[i]:
            if poster:
                inner = f'<img class="mc-poster" src="{poster}" alt="{title}">'
            else:
                gradient = _genre_gradient(str(movie.get("genres", "")))
                inner = f'<div class="mc-poster-fallback" style="background:{gradient};"></div>'

            link_open = f'<a class="mc-item-link" href="?detail={tmdb_id}&src=home" target="_self">' if tmdb_id else '<div class="mc-item-link">'
            link_close = '</a>' if tmdb_id else '</div>'
            st.markdown(
                f'{link_open}'
                f'<div class="mc-card">{badge_html}{inner}</div>'
                f'{link_close}'
                f'<div class="mc-title">{title}</div>'
                f'<div class="mc-meta">★ {rating*2:.1f} · {year if year else "—"}</div>',
                unsafe_allow_html=True,
            )


# ── Results grid ──────────────────────────────────────────────────────────────

def render_results_cards(
    df: pd.DataFrame,
    poster_urls: Optional[Dict[int, str]] = None,
    return_q: str = "",
) -> None:
    """
    3-column poster cards with visual badges.
    Clicking a card navigates to the full detail page via query params.
    return_q is embedded in the URL so it survives the page reload.
    """
    import urllib.parse
    q_encoded = urllib.parse.quote(return_q, safe="") if return_q else ""
    n_cols = 4
    cols = st.columns(n_cols, gap="small")

    for i, (_, row) in enumerate(df.iterrows()):
        title  = str(row.get("title", ""))
        year   = int(row.get("release_year", 0)) if row.get("release_year") else 0
        rating = float(row.get("avg_rating") or 0)
        votes  = int(row.get("rating_count") or 0)

        tmdb_id = None
        try:
            raw = row.get("tmdbId")
            if raw is not None and not pd.isna(raw):
                tmdb_id = int(raw)
        except (ValueError, TypeError):
            pass

        poster     = (poster_urls or {}).get(tmdb_id) if tmdb_id else None
        badge_info = _get_badge(rating, votes, year) if year else None
        badge_html = ""
        if badge_info:
            label, color, bg, border = badge_info
            badge_html = (
                f'<span class="mc-badge" style="background:{bg};color:{color};'
                f'border:1px solid {border};">{label}</span>'
            )

        with cols[i % n_cols]:
            if poster:
                inner = f'<img class="mc-poster" src="{poster}" alt="{title}">'
            else:
                gradient = _genre_gradient(str(row.get("genres", "")))
                inner = f'<div class="mc-poster-fallback" style="background:{gradient};"></div>'

            year_str = str(year) if year else "—"
            link_open = f'<a class="mc-item-link" href="?detail={tmdb_id}&src=search&q={q_encoded}" target="_self">' if tmdb_id else '<div class="mc-item-link">'
            link_close = '</a>' if tmdb_id else '</div>'
            st.markdown(
                f'{link_open}'
                f'<div class="mc-card">{badge_html}{inner}</div>'
                f'{link_close}'
                f'<div class="mc-title">{title}</div>'
                f'<div class="mc-meta">★ {rating*2:.1f} · {year_str}</div>',
                unsafe_allow_html=True,
            )


# ── Empty state ────────────────────────────────────────────────────────────────

def render_empty_state(q: str, has_active_filters: bool) -> bool:
    """
    Friendly no-results message.
    Returns True if the user clicks 'Réinitialiser les filtres'.
    """
    st.markdown(
        f"""
        <div style="text-align:center;padding:3.5rem 1rem;">
            <div style="font-size:3rem;margin-bottom:1rem;color:rgba(255,255,255,0.2);">—</div>
            <div style="font-size:1.05rem;font-weight:600;color:rgba(255,255,255,0.75);
                        margin-bottom:0.5rem;">
                Aucun film trouvé pour <em>"{q}"</em>
            </div>
            <div style="font-size:0.85rem;color:rgba(255,255,255,0.35);
                        max-width:380px;margin:0 auto 1.5rem;line-height:1.6;">
                {"Essayez d'élargir vos filtres (note, année, genre) ou d'utiliser d'autres mots-clés." if has_active_filters else "Essayez un terme plus général ou vérifiez l'orthographe."}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if has_active_filters:
        _, col_btn, _ = st.columns([2, 1.5, 2])
        with col_btn:
            return st.button("↺  Réinitialiser les filtres", use_container_width=True, type="secondary")
    return False


# ── Full-page structured detail view ─────────────────────────────────────────

def render_movie_detail_full(details: Dict) -> None:
    """Full structured detail page: cinematic header + poster + info + box-office + cast."""
    poster_url   = details.get("poster_url", "")
    title        = details.get("title", "Film inconnu")
    tagline      = details.get("tagline", "")
    overview     = details.get("overview", "")
    release_date = details.get("release_date", "")
    runtime      = details.get("runtime")
    vote_avg     = details.get("vote_average")
    vote_count   = details.get("vote_count")
    budget       = details.get("budget")
    revenue      = details.get("revenue")
    orig_lang    = (details.get("original_language") or "").upper()
    genres_list: List[str] = details.get("genres", [])
    cast: List[Dict]       = details.get("cast", [])

    # ── Cinematic blurred header ───────────────────────────────────────────────
    tagline_html = f'<div class="detail-hero-tagline">"{tagline}"</div>' if tagline else ""
    st.markdown(
        '<div class="detail-hero">'
        f'<div class="detail-hero-bg" style="background-image:url(\'{poster_url}\');"></div>'
        '<div class="detail-hero-grad"></div>'
        '<div class="detail-hero-content">'
        f'<div class="detail-hero-title">{title}</div>'
        + tagline_html
        + '</div></div>',
        unsafe_allow_html=True,
    )

    # ── Two-column: poster + info ──────────────────────────────────────────────
    col_poster, col_info = st.columns([1, 2.4], gap="large")

    with col_poster:
        if poster_url:
            st.image(poster_url, use_container_width=True)

    with col_info:
        # Rating / date / runtime badges
        badges_html = ""
        if vote_avg is not None:
            votes_str = f" ({vote_count:,} votes)" if vote_count else ""
            badges_html += f'<span class="badge badge-rating">★ {vote_avg}/10{votes_str}</span>'
        if release_date:
            badges_html += f'<span class="badge badge-date">{release_date[:4]}</span>'
        if runtime:
            badges_html += f'<span class="badge badge-date">{runtime} min</span>'
        if badges_html:
            st.markdown(badges_html, unsafe_allow_html=True)

        # Genre badges
        if genres_list:
            st.markdown(
                '<div style="margin-top:0.4rem;">'
                + "".join(f'<span class="badge badge-genre">{g}</span>' for g in genres_list)
                + "</div>",
                unsafe_allow_html=True,
            )

        # Synopsis
        if overview:
            st.markdown(
                '<div class="detail-section-label">Synopsis</div>'
                f'<div class="detail-overview">{overview}</div>',
                unsafe_allow_html=True,
            )

    # ── Box-office / info ─────────────────────────────────────────────────────
    eco_items: List[Tuple[str, str]] = []
    if budget and budget > 0:
        eco_items.append(("BUDGET",  f"${budget:,.0f}"))
    if revenue and revenue > 0:
        eco_items.append(("REVENUS", f"${revenue:,.0f}"))
    if orig_lang:
        eco_items.append(("LANGUE",  orig_lang))

    if eco_items:
        st.divider()
        st.markdown('<div class="detail-section-label">Informations</div>', unsafe_allow_html=True)
        eco_cols = st.columns(len(eco_items))
        for idx, (label, value) in enumerate(eco_items):
            with eco_cols[idx]:
                st.markdown(
                    f'<div class="eco-item">'
                    f'<div class="eco-label">{label}</div>'
                    f'<div class="eco-value">{value}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

    # ── Cast ──────────────────────────────────────────────────────────────────
    if cast:
        st.divider()
        st.markdown('<div class="detail-section-label">Distribution</div>', unsafe_allow_html=True)
        cast_cols = st.columns(3)
        for i, member in enumerate(cast[:12]):
            name      = member.get("name", "")
            character = member.get("character", "")
            with cast_cols[i % 3]:
                st.markdown(
                    f'<div class="cast-member">'
                    f'<strong style="color:#fff;">{name}</strong>'
                    f'<span style="color:rgba(148,163,184,0.65);display:block;font-size:0.75rem;">'
                    f'{character}</span></div>',
                    unsafe_allow_html=True,
                )
