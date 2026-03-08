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

SQL queries are handled by dedicated **Google Cloud Functions** (the logic sublayer of Layer 2). Each function prints the full SQL command it executes — with its parameters and result count — to stdout, which is captured by **Google Cloud Logging**.

To view SQL queries live:

```bash
gcloud beta run services logs tail cinesearch --region europe-west6
```

Code structure:

```
streamlit_app/
├── app.py            ← orchestrator, caching, navigation state
├── config.py         ← Cloud Function URLs and UI constants
├── api_client.py     ← HTTP calls to Cloud Functions (no SQL here)
└── ui_components.py  ← Streamlit rendering helpers (no HTTP, no SQL here)

cloud_functions/
├── movies_search/       ← SQL: JOIN + GROUP BY + HAVING AVG(rating) + all filters
├── movies_autocomplete/ ← SQL: LIKE autocomplete on title
├── movie_details/       ← TMDB API: poster, overview, cast, runtime, providers, director
└── movies_sample/       ← SQL: random sample for home page
```

---

## Features

- **Title autocomplete** — SQL `LIKE` suggestions as you type
- **Language filter** — `WHERE language = ?`
- **Genre filter** — `WHERE genres LIKE ?`
- **Average rating filter** — SQL `JOIN ratings + GROUP BY + HAVING AVG(rating) ≥ threshold`
- **Release year filter** — `WHERE release_year BETWEEN ? AND ?`
- **Movie detail panel** — TMDB poster, tagline, synopsis, cast, runtime, budget, revenue
- **Streaming providers** — where to watch (streaming / rent / buy) via TMDB API
- **Director filmography** — director name + up to 6 other films by the same director
- **Sort options** — relevance, title, year, rating
- **Hero carousel** — auto-rotating banner with inline search form

---

## Run with Docker (local)

```bash
cd streamlit_app

docker build -t cinesearch .

docker run -p 8080:8080 \
  -v "$HOME/.config/gcloud:/root/.config/gcloud" \
  cinesearch
```

Open http://localhost:8080

---

## Run without Docker (local)

```bash
# Authenticate with Google Cloud (one-time)
gcloud auth application-default login

cd streamlit_app
pip install -r requirements.txt
streamlit run app.py
```

---

## Deploy to Cloud Run

```bash
cd streamlit_app

gcloud run deploy cinesearch \
  --source . \
  --region europe-west6 \
  --allow-unauthenticated \
  --port 8080
```

---

## BigQuery tables

| Table | Key columns |
|---|---|
| `ASSIGNEMENT1.movies` | `movieId`, `title`, `genres`, `language`, `release_year`, `country`, `tmdbId` |
| `ASSIGNEMENT1.rating` | `userId`, `movieId`, `rating`, `timestamp` |
