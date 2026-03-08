# CinéSearch — Cloud & Advanced Analytics · Assignment 1

## Live application

**URL:** https://my-streamlit-app-120497552025.europe-west6.run.app

---

## Architecture

The application follows the **2-layer architecture** required by the assignment:

```
Layer 1 — Database  : BigQuery (movies + ratings tables)
Layer 2 — Logic+UI  : Streamlit app + Google Cloud Functions
```

SQL queries live in **Google Cloud Functions** (the logic sublayer of Layer 2). Each Cloud Function prints every SQL command it executes — with its parameters and result count — to **Google Cloud Logging** (visible in Cloud Run logs).

Internal module structure (Streamlit app):

```
streamlit_app/
├── app.py            ← orchestrator, caching, navigation state
├── config.py         ← Cloud Function URLs and UI constants
├── api_client.py     ← HTTP calls to Cloud Functions (no SQL, no Streamlit)
└── ui_components.py  ← Streamlit rendering helpers (no HTTP, no SQL)

cloud_functions/
├── movies_search/       ← SQL: JOIN + GROUP BY + HAVING AVG(rating) + all filters
├── movies_autocomplete/ ← SQL: LIKE autocomplete on title
├── movie_details/       ← TMDB API: poster, overview, cast, runtime, providers, director
└── movies_sample/       ← SQL: random sample for home page
```

---

## Features

- **Hero carousel** — auto-rotating cinematic banner (5 featured films); includes an inline search form centred at the top of the card
- **Title autocomplete** — SQL `LIKE` suggestions as you type (starts-with prioritised)
- **Language filter** — filter by ISO language code (`en`, `fr`, `de`, …)
- **Genre filter** — matches pipe-separated genre strings (`Action|Comedy|Drama`)
- **Average rating filter** — SQL `JOIN` + `GROUP BY` + `HAVING AVG(rating) ≥ threshold`
- **Release year filter** — `WHERE release_year >= min_year` (+ client-side max_year)
- **Sort options** — relevance, title A→Z / Z→A, year ↑↓, rating ↑↓
- **Load more** — paginated results (9 cards per page, up to 100 results)
- **Movie detail panel** — TMDB poster, tagline, overview, cast, runtime, budget, revenue
- **Streaming providers** — where to watch (streaming, rent, buy) via TMDB watch/providers API; logos link to JustWatch
- **Director filmography** — director name displayed in the detail panel, with a row of up to 6 other films by the same director
- **Adaptive sidebar** — search bar hidden on the home page, visible only during a search session; on mobile, the sidebar auto-opens when the first search is made

---

## Deploy Streamlit app on Cloud Run

```bash
cd streamlit_app

gcloud run deploy cinesearch \
  --source . \
  --region europe-west6 \
  --allow-unauthenticated \
  --port 8080
```

BigQuery and Cloud Functions authentication is handled automatically by Cloud Run's service account. SQL queries are visible in Cloud Run logs:

```bash
gcloud run services logs read cinesearch --region europe-west6
```

---

## Run locally (development)

```bash
# 1. Authenticate with Google Cloud (one-time setup)
gcloud auth application-default login

# 2. Install dependencies
cd streamlit_app
pip install -r requirements.txt

# 3. Run
streamlit run app.py
```

---

## Run with Docker (local)

```bash
cd streamlit_app

# Build
docker build -t cinesearch .

# Run (pass your local Google Cloud credentials)
docker run -p 8080:8080 \
  -v "$HOME/.config/gcloud:/root/.config/gcloud" \
  cinesearch
```

Open http://localhost:8080

---

## BigQuery tables

| Table | Key columns |
|---|---|
| `ASSIGNEMENT1.movies` | `movieId`, `title`, `genres`, `language`, `release_year`, `country`, `tmdbId` |
| `ASSIGNEMENT1.rating` | `userId`, `movieId`, `rating`, `timestamp` |
