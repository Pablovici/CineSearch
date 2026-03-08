# CinéSearch — Cloud & Advanced Analytics · Assignment 1

## Live application

**URL:** https://my-streamlit-app-120497552025.europe-west6.run.app

---

## Important — how the app actually runs

**The Streamlit app does not query BigQuery directly.** All database logic is handled by **Google Cloud Functions already deployed on Google Cloud**. The Streamlit app only makes HTTP calls to those functions.

This means:

- Running the app locally (with or without Docker) still hits the **live Cloud Functions** on Google Cloud — there is nothing to deploy or start locally other than the Streamlit frontend.
- The Cloud Functions themselves connect to BigQuery using the service account credentials attached to the Cloud Run environment.
- If you run locally, you need valid Google Cloud credentials on your machine (see below), but **you do not need to deploy or run the Cloud Functions yourself** — they are already live.

The URLs of the deployed Cloud Functions are hardcoded as default values in `streamlit_app/config.py`:

```python
MOVIES_AUTOCOMPLETE_URL = os.getenv("MOVIES_AUTOCOMPLETE_URL",
    "https://movies-autocomplete-120497552025.europe-west6.run.app")

MOVIES_SEARCH_URL = os.getenv("MOVIES_SEARCH_URL",
    "https://movies-search-120497552025.europe-west6.run.app")

MOVIE_DETAILS_URL = os.getenv("MOVIE_DETAILS_URL",
    "https://movie-details-120497552025.europe-west6.run.app")
```

These can be overridden via environment variables (useful if you redeploy the functions under different URLs), but **by default no configuration is needed** — the app works out of the box against the already-deployed endpoints.

---

## Architecture

The application follows the **2-layer architecture** required by the assignment:

```
Layer 1 — Database  : BigQuery (movies + ratings tables, dataset ASSIGNEMENT1)
Layer 2 — Logic+UI  : Streamlit app  +  Google Cloud Functions
                               ↑                    ↑
                         Frontend UI          SQL / TMDB logic
                         (HTTP client)        (connects to BigQuery)
```

The Cloud Functions act as the **logic sublayer** of Layer 2. They receive HTTP requests from the Streamlit app, execute SQL against BigQuery, and return JSON. The Streamlit app never touches BigQuery or SQL directly.

Each Cloud Function prints the full SQL query it runs (with parameters and result count) to stdout, captured by **Google Cloud Logging**. To view live SQL logs:

```bash
gcloud beta run services logs tail cinesearch --region europe-west6
```

### Code structure

```
streamlit_app/
├── app.py            ← orchestrator: caching, navigation state, page routing
├── config.py         ← Cloud Function URLs (with hardcoded defaults) + UI constants
├── api_client.py     ← HTTP calls to Cloud Functions — no SQL, no BigQuery here
├── ui_components.py  ← all Streamlit rendering — no HTTP, no SQL here
├── requirements.txt
└── Dockerfile

cloud_functions/
├── movies_search/       ← SQL: full-text search with JOIN ratings + filters (language, genre,
│                              min rating, min year) + HAVING AVG(rating) ≥ threshold
├── movies_autocomplete/ ← SQL: LIKE autocomplete on movie title
├── movie_details/       ← TMDB API: poster, overview, cast, runtime, streaming providers,
│                              director + director filmography
└── movies_sample/       ← SQL: random sample used for home page sections
```

---

## Features

- **Hero carousel** — auto-rotating banner with inline search form (5-second rotation)
- **Title autocomplete** — SQL `LIKE` suggestions as you type
- **Language filter** — `WHERE language = ?`
- **Genre filter** — `WHERE genres LIKE ?`
- **Average rating filter** — SQL `JOIN ratings + GROUP BY + HAVING AVG(rating) ≥ threshold`
- **Release year filter** — `WHERE release_year BETWEEN ? AND ?`
- **Sort options** — relevance, title A→Z / Z→A, year ↑↓, rating ↑↓
- **Movie detail page** — TMDB poster, tagline, synopsis, cast, runtime, budget, revenue
- **Streaming providers** — where to watch (streaming / rent / buy) via TMDB API
- **Director filmography** — director name + up to 6 other films by the same director
- **Tendances & À découvrir** — curated home-page sections with poster cards

---

## Run locally (simplest — no Docker)

No `.env` file or special configuration needed. The Cloud Function URLs are already hardcoded in `config.py`.

```bash
# 1. Authenticate with Google Cloud (required so the app can call the Cloud Functions)
gcloud auth application-default login

# 2. Install dependencies and start the app
cd streamlit_app
pip install -r requirements.txt
python3 -m streamlit run app.py
```

Open http://localhost:8501

---

## Run locally with Docker

```bash
cd streamlit_app

docker build -t cinesearch .

docker run -p 8080:8080 \
  -v "$HOME/.config/gcloud:/root/.config/gcloud" \
  cinesearch
```

Open http://localhost:8080

The `-v` flag mounts your local Google Cloud credentials into the container so the app can reach the Cloud Functions.

---

## Override Cloud Function URLs (optional)

If you redeploy the Cloud Functions under different URLs, you can override the defaults without modifying `config.py` by setting environment variables:

```bash
export MOVIES_SEARCH_URL=https://your-function-url.run.app
export MOVIES_AUTOCOMPLETE_URL=https://your-function-url.run.app
export MOVIE_DETAILS_URL=https://your-function-url.run.app

python3 -m streamlit run app.py
```

Or create a `.env` file and load it before running. **This is only needed if you redeploy the functions yourself** — the defaults already point to the live deployed endpoints.

---

## Deploy the Streamlit app to Cloud Run

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

---

## View SQL queries (Cloud Logging)

Every Cloud Function logs the exact SQL it executes. To stream logs in real time:

```bash
gcloud beta run services logs tail cinesearch --region europe-west6
```
