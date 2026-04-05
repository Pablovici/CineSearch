"""loading.py — Cinematic loading screen for CinéSearch.

Full-screen splash shown once per session:
  - Vertical scrolling poster columns (straight, alternating up/down)
  - Dark overlay with a moving circular spotlight (magnifying glass effect)
  - CinéSearch branding at the bottom

Triggered before main() on first visit; sets _loading_done in session_state
and reruns into the main app after the animation completes.
"""
import time

import streamlit as st

# 16 well-known movie posters from TMDB (w342 = fast loading, good quality)
_POSTERS = [
    "https://image.tmdb.org/t/p/w342/9gk7adOG2ooPpcO1mAmJFAtefeO.jpg",  # Inception
    "https://image.tmdb.org/t/p/w342/gEU2QniE6E77NI6lCU6MxlNBvIx.jpg",  # Interstellar
    "https://image.tmdb.org/t/p/w342/qJ2tW6WMUDux911r6m7haRef0WH.jpg",  # The Dark Knight
    "https://image.tmdb.org/t/p/w342/pB8BM7pdSp6B6Ih7QZ4DrQ3PmJK.jpg",  # Fight Club
    "https://image.tmdb.org/t/p/w342/f89U3ADr1oiB1s9GkdPOEpXUk5H.jpg",  # The Matrix
    "https://image.tmdb.org/t/p/w342/d5iIlFn5s0ImszYzBPbOYKQmG_1.jpg",  # Pulp Fiction
    "https://image.tmdb.org/t/p/w342/q6y0Go1tsGEsmtFryDOJo3dEmqu.jpg",  # The Shawshank Redemption
    "https://image.tmdb.org/t/p/w342/3bhkrj58Vtu7enYsRolD1fZdja1.jpg",  # The Godfather
    "https://image.tmdb.org/t/p/w342/saHP97rTPS5eLmrLQEcANmKrsFl.jpg",  # Forrest Gump
    "https://image.tmdb.org/t/p/w342/vQWk5YBFWFCPbV6sXl5EebieoT.jpg",   # The Lord of the Rings
    "https://image.tmdb.org/t/p/w342/8tZYtuWezp8JbcsvHYO0O46tFbo.jpg",  # Joker
    "https://image.tmdb.org/t/p/w342/cezWGskPY5x7GaglTTRN4Fugfb8.jpg",  # Whiplash
    "https://image.tmdb.org/t/p/w342/rSPw7tgCH9c6NqICZef4kZjFOQ5.jpg",  # Parasite
    "https://image.tmdb.org/t/p/w342/udDclJoHjfjb8Ekgsd4FDteOkCU.jpg",  # Goodfellas
    "https://image.tmdb.org/t/p/w342/7IiTTgloJzvGI1TAYymCfbfl3vT.jpg",  # Titanic
    "https://image.tmdb.org/t/p/w342/oxcMhA1WlW3M2t8e6b12Y153Eok.jpg",  # Avengers: Endgame
]

_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@300;800&display=swap');

#MainMenu { visibility: hidden; }
header    { visibility: hidden; }
footer    { visibility: hidden; }
.block-container {
    padding: 0 !important;
    max-width: 100% !important;
}
body, .stApp {
    background: #000 !important;
    overflow: hidden !important;
}

/* ── Vertical scroll ── */
@keyframes scrollUp {
    from { transform: translateY(0); }
    to   { transform: translateY(-50%); }
}
@keyframes scrollDown {
    from { transform: translateY(-50%); }
    to   { transform: translateY(0); }
}

/* ── Spotlight path — 8 waypoints across the screen ── */
@keyframes searchMove {
    0%   { top: 38%; left: 22%; }
    12%  { top: 18%; left: 50%; }
    24%  { top: 32%; left: 75%; }
    37%  { top: 60%; left: 82%; }
    50%  { top: 72%; left: 55%; }
    62%  { top: 62%; left: 28%; }
    75%  { top: 42%; left: 12%; }
    88%  { top: 22%; left: 38%; }
    100% { top: 38%; left: 22%; }
}

/* ── Branding fade ── */
@keyframes brandFade {
    0%   { opacity: 0; transform: translateY(10px); }
    20%  { opacity: 1; transform: translateY(0);    }
    80%  { opacity: 1; transform: translateY(0);    }
    100% { opacity: 0; transform: translateY(-6px); }
}

/* ── Whole screen fade out at the end ── */
@keyframes screenFade {
    0%   { opacity: 1; }
    88%  { opacity: 1; }
    100% { opacity: 0; pointer-events: none; }
}

/* ── Root wrapper ── */
.cs-loader {
    position: fixed;
    inset: 0;
    background: #000;
    z-index: 9999;
    overflow: hidden;
    animation: screenFade 4.5s ease forwards;
}

/* ── Columns ── */
.cs-columns {
    position: absolute;
    inset: 0;
    display: flex;
    gap: 5px;
    padding: 0 2px;
}

.cs-col {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 5px;
    will-change: transform;
}

.cs-col.up   { animation: scrollUp   linear infinite; }
.cs-col.down { animation: scrollDown linear infinite; }

.cs-col img {
    width: 100%;
    border-radius: 5px;
    object-fit: cover;
    display: block;
    opacity: 0.6;
}

/* ── Spotlight (magnifying glass circle) ── */
.cs-spotlight {
    position: absolute;
    width: 210px;
    height: 210px;
    border-radius: 50%;
    /* The massive box-shadow fills the screen black, leaving the circle transparent */
    box-shadow: 0 0 0 100vmax rgba(0, 0, 0, 0.93);
    border: 2.5px solid rgba(255, 255, 255, 0.18);
    animation: searchMove 5.2s cubic-bezier(0.45, 0, 0.55, 1) infinite;
    z-index: 3;
    /* transform keeps the circle centered on the animated top/left coords */
    transform: translate(-50%, -50%);
}

/* Magnifying glass handle */
.cs-spotlight::after {
    content: '';
    position: absolute;
    bottom: -48px;
    right: -42px;
    width: 8px;
    height: 58px;
    background: rgba(255, 255, 255, 0.22);
    border-radius: 4px;
    transform: rotate(42deg);
    transform-origin: top center;
}

/* ── Branding wrapper (flex center, immune to parent transforms) ── */
.cs-brand-wrap {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 10;
    pointer-events: none;
}

/* ── Branding ── */
.cs-brand {
    text-align: center;
    animation: brandFade 4.5s ease forwards;
    white-space: nowrap;
}

.cs-brand-title {
    font-family: 'Montserrat', -apple-system, sans-serif;
    font-size: 2rem;
    font-weight: 800;
    color: #fff;
    letter-spacing: -0.02em;
    line-height: 1;
}

.cs-brand-sub {
    font-family: 'Montserrat', -apple-system, sans-serif;
    font-size: 0.65rem;
    color: rgba(255, 255, 255, 0.32);
    letter-spacing: 0.25em;
    text-transform: uppercase;
    margin-top: 0.45rem;
}

/* ── Mobile (≤ 768px) ── */
@media (max-width: 768px) {
    /* Fewer, wider columns */
    .cs-col:nth-child(n+6) { display: none; }   /* keep only 5 columns */

    /* Smaller spotlight */
    .cs-spotlight {
        width: 140px;
        height: 140px;
    }
    .cs-spotlight::after {
        bottom: -32px;
        right: -28px;
        width: 6px;
        height: 40px;
    }

    /* Slightly smaller text */
    .cs-brand-title { font-size: 1.5rem; }
    .cs-brand-sub   { font-size: 0.58rem; letter-spacing: 0.18em; }
}

/* ── Small mobile (≤ 430px) ── */
@media (max-width: 430px) {
    .cs-col:nth-child(n+5) { display: none; }   /* keep only 4 columns */

    .cs-spotlight {
        width: 110px;
        height: 110px;
    }
    .cs-spotlight::after {
        bottom: -26px;
        right: -22px;
        width: 5px;
        height: 32px;
    }

    .cs-brand-title { font-size: 1.3rem; }
}
</style>
"""


def show_loading_screen() -> None:
    """Render the full-screen loading splash and block until animation completes.

    Call at the very top of main() when session_state['_loading_done'] is False.
    Sets _loading_done and _loader_shown before rerunning into the main app.
    """
    st.markdown(_CSS, unsafe_allow_html=True)

    # Build 8 vertical columns; alternate up/down and vary speed for depth effect.
    # Each column is offset into _POSTERS so adjacent columns show different films.
    # Content is duplicated (×2) to create a seamless infinite loop via -50% translateY.
    n_cols  = 8
    speeds  = [16, 22, 18, 26, 14, 20, 24, 17]   # seconds per full cycle, one per column
    cols_html = ""
    for i in range(n_cols):
        direction = "up" if i % 2 == 0 else "down"
        speed     = speeds[i]
        offset    = (i * 2) % len(_POSTERS)
        rotated   = _POSTERS[offset:] + _POSTERS[:offset]
        imgs      = "".join(
            f'<img src="{p}" loading="eager" alt="">'
            for p in rotated * 2          # ×2 for the seamless loop
        )
        cols_html += (
            f'<div class="cs-col {direction}" '
            f'style="animation-duration:{speed}s;">'
            f'{imgs}</div>'
        )

    st.markdown(
        f'<div class="cs-loader">'
        f'<div class="cs-columns">{cols_html}</div>'
        f'<div class="cs-spotlight"></div>'
        f'<div class="cs-brand-wrap">'
        f'<div class="cs-brand">'
        f'<div class="cs-brand-title">CinéSearch</div>'
        f'<div class="cs-brand-sub">Searching the world\'s films</div>'
        f'</div>'
        f'</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # Wait for CSS animations to finish, then hand off to the main app.
    time.sleep(4.2)
    st.session_state["_loading_done"] = True
    st.session_state["_loader_shown"] = True   # suppress the secondary CSS loader in inject_css()
    st.rerun()
