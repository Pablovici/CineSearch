# CineSearch — Cloud & Advanced Analytics 2026 · Assignment 2

## Live Application

**URL:** https://my-streamlit-app-120497552025.europe-west6.run.app

- **Frontend (Streamlit):** https://my-streamlit-app-120497552025.europe-west6.run.app
- **Backend (Flask API):** https://cinesearch-backend-120497552025.europe-west6.run.app

---

## Architecture — 2-Tier (Backend + Frontend)

The application follows the required **2-tier microservice architecture** with two separate Docker containers deployed on Google Cloud Run:

```
                        ┌─────────────────────────────────────────┐
  User (browser)  ───>  │  Tier 1 — Streamlit Frontend            │
                        │  (Docker container on Cloud Run)        │
                        │  - Movie search with ES autocomplete    │
                        │  - Like movies to seed recommendations  │
                        │  - Recommendation display with posters  │
                        │  - Filters (language, genre, year,      │
                        │    rating)                               │
                        └───────────────┬─────────────────────────┘
                                        │ HTTP (REST API)
                        ┌───────────────▼─────────────────────────┐
                        │  Tier 2 — Flask Backend API              │
                        │  (Docker container on Cloud Run)         │
                        │  - Elasticsearch (autocomplete)          │
                        │  - BigQuery ML (ML.RECOMMEND)            │
                        │  - Similar users computation             │
                        │  - Cold start handling                   │
                        └───────────────┬─────────────────────────┘
                                        │
                   ┌────────────────────┼────────────────────┐
                   ▼                    ▼                    ▼
            ┌────────────┐     ┌──────────────┐     ┌──────────────┐
            │ BigQuery    │     │ Elasticsearch│     │ TMDB API     │
            │ (ASSIGNEMENT│     │ (Elastic     │     │ (posters,    │
            │  2 dataset) │     │  Cloud)      │     │  metadata)   │
            └────────────┘     └──────────────┘     └──────────────┘
```

### Cloud Functions (Assignment 1 — reused)

Three Google Cloud Functions handle catalogue search and TMDB enrichment, deployed on Cloud Run:

| Function | Purpose | URL |
|---|---|---|
| `movies_search` | Full-text search with filters (BigQuery JOIN + GROUP BY + HAVING) | `https://movies-search-120497552025.europe-west6.run.app` |
| `movies_autocomplete` | SQL LIKE fallback autocomplete (used when Elasticsearch is unavailable) | `https://movies-autocomplete-120497552025.europe-west6.run.app` |
| `movie_details` | TMDB API enrichment: poster, cast, overview, streaming providers, director filmography | `https://movie-details-120497552025.europe-west6.run.app` |

---

## Similarity Computation Method (Cold Start)

The web app user is a **cold start user** — they have no userId in the training dataset. We solve this as follows:

### Step 1 — User likes preferred movies

The user searches for movies using the **search bar** (powered by Elasticsearch autocomplete). They click on a movie to open its detail page, then click **"Add to Favorites" (♡)** to like it. Liked movies are persisted locally and displayed in the "Your Liked Movies" row on the home page. Each time the favorites list changes, a new recommendation batch is automatically computed.

### Step 2 — Find similar users in the dataset

We query the `ASSIGNEMENT2.ratings` table to find users who rated the same seed movies **highly** (with `rating_im >= 0.7`):

```sql
WITH overlap AS (
  SELECT
    r.userId,
    COUNT(DISTINCT r.movieId) AS overlap_count
  FROM ratings AS r
  WHERE r.movieId IN UNNEST(@selected_movie_ids)
    AND r.rating_im >= @min_rating_im
  GROUP BY r.userId
)
SELECT userId
FROM overlap
ORDER BY overlap_count DESC, userId ASC
LIMIT @top_k
```

**Ranking logic:** Users are ranked by **overlap count** — how many of the seed movies they rated highly. The more movies a user has in common with the cold-start user's selection, the higher they rank. Ties are broken by userId (deterministic). We keep the **top 10 most similar users**.

### Step 3 — Cross-dataset filtering

The user selects movies from the large catalogue (`ASSIGNEMENT1`, ~45K movies indexed in Elasticsearch). The ML model only knows movies from the smaller dataset (`ASSIGNEMENT2`). Before computing recommendations, we filter the selected movie IDs to keep only those present in `ASSIGNEMENT2.ratings`. If none of the selected movies exist in the ML dataset, we fall back to popular movies.

### Step 4 — Generate recommendations via BigQuery ML

We run `ML.RECOMMEND` on the pre-trained **Matrix Factorization** model (`first_MF_model`) for all similar users:

```sql
WITH ranked AS (
  SELECT
    rec.movieId,
    rec.predicted_rating_im_confidence AS confidence,
    ROW_NUMBER() OVER (
      PARTITION BY rec.userId
      ORDER BY rec.predicted_rating_im_confidence DESC
    ) AS rn
  FROM ML.RECOMMEND(
    MODEL `first_MF_model`,
    (SELECT user_id AS userId FROM UNNEST(@similar_user_ids) AS user_id)
  ) AS rec
  WHERE rec.movieId NOT IN UNNEST(@selected_movie_ids)
),
aggregated AS (
  SELECT movieId, AVG(confidence) AS avg_confidence, COUNT(*) AS user_count
  FROM ranked WHERE rn <= 20
  GROUP BY movieId
)
SELECT a.movieId, m.title, a.avg_confidence, a.user_count, l.tmdbId
FROM aggregated AS a
INNER JOIN movies AS m ON a.movieId = m.movieId
LEFT JOIN links AS l ON a.movieId = l.movieId
ORDER BY a.avg_confidence DESC, a.user_count DESC
LIMIT 10
```

**Aggregation strategy:**
1. For each similar user, keep only their **top 20 recommendations** (prevents one prolific user from dominating).
2. **Exclude** the seed movies the user already liked.
3. Average the ML confidence scores across all similar users.
4. Final ranking: `avg_confidence DESC`, then `user_count DESC` as tiebreaker.
5. Return the **top 10** recommendations with posters (from TMDB API).

### Fallbacks

- **No movies liked** → Display the top-10 most popular movies globally (ranked by `rating_count DESC, avg_rating DESC`).
- **Liked movies not in ML dataset** → Popular movies, excluding the user's seeds.
- **No similar users found** → Same popular fallback.

---

## Features

- **Elasticsearch autocomplete** — Real-time search-as-you-type via the Flask backend, with prefix boost, ngram matching, and Python-side re-ranking. Falls back to SQL LIKE via Cloud Function if Elasticsearch is unavailable.
- **Favorites system** — Like movies via the ❤️ button on any detail page; liked movies are persisted across sessions and automatically seed personalized recommendations on the home page.
- **Personalized recommendations** — BigQuery ML Matrix Factorization via similar users (cold start handling). Displayed in a "Recommended for You" row with ML confidence scores shown as match percentages.
- **Generic recommendations** — Top popular movies displayed when no movies have been liked yet.
- **Movie detail pages** — TMDB poster, synopsis, cast, runtime, budget, revenue, streaming providers (flatrate/rent/buy), director filmography.
- **Advanced filters** — Language, genre (multiselect), year range (min/max slider), minimum rating. Applied via the sidebar on search results.
- **Hero carousel** — Auto-rotating banner with 5 featured films, updating every 5 seconds.
- **Browse by Genre** — Clickable genre tiles with TMDB poster backgrounds, leading to filtered results.
- **Trending** — Top-rated recent films displayed on the home page.

---

## BigQuery Datasets

| Dataset | Tables | Purpose |
|---|---|---|
| `ASSIGNEMENT1` | `movies`, `rating` | Large catalogue (~45K movies) — used for search, filters, and indexed in Elasticsearch for autocomplete |
| `ASSIGNEMENT2` | `movies`, `ratings`, `links` | Small dataset (ml-small) — used for Matrix Factorization model training and recommendations |

### BigQuery ML Model

```sql
-- Model trained as per Lab 5 (Matrix Factorization)
-- Lives in: ferrous-store-487916-f8.ASSIGNEMENT2.first_MF_model
-- Used via: ML.RECOMMEND(MODEL `first_MF_model`, ...)
```

---

## Run Locally with Docker Compose

```bash
# Clone the repository
git clone <repo-url> && cd CineSearch

# Create backend/.env from the template
cp backend/.env.example backend/.env
# Edit backend/.env with your own ES_ENDPOINT, ES_API_KEY, etc.

# Build and start both containers
docker compose up --build
```

This starts:
- **Backend** (Flask API) on http://localhost:5001
- **Frontend** (Streamlit) on http://localhost:8501

The terminal will display all executed SQL queries and their results.

### Run Locally Without Docker

```bash
# 1. Authenticate with Google Cloud
gcloud auth application-default login

# 2. Start the backend
cd backend
set -a && source .env && set +a
pip install -r requirements.txt
python app.py
# → Runs on http://localhost:8080

# 3. In another terminal, start the frontend
cd streamlit_app
export BACKEND_URL=http://localhost:8080
pip install -r requirements.txt
python -m streamlit run app.py
# → Runs on http://localhost:8501
```

---

## Deploy to Cloud Run

```bash
# Deploy the Flask backend
cd backend
gcloud run deploy cinesearch-backend \
  --source . \
  --region europe-west6 \
  --allow-unauthenticated \
  --port 8080

# Deploy the Streamlit frontend
cd streamlit_app
gcloud run deploy my-streamlit-app \
  --source . \
  --region europe-west6 \
  --allow-unauthenticated \
  --port 8080
```

---

## Code Structure

```
CineSearch/
├── README.md                  ← This file
├── docker-compose.yml         ← Local dev: runs both containers
├── .env.example               ← Environment variables template
│
├── backend/                   ← Tier 2: Flask API (Docker container)
│   ├── Dockerfile             ← Python 3.11 + gunicorn
│   ├── app.py                 ← /health, /autocomplete, /recommend
│   ├── es_service.py          ← Elasticsearch autocomplete + title fetching
│   ├── index_movies_to_es.py  ← One-shot BigQuery → ES indexing script
│   ├── requirements.txt
│   └── .env.example
│
├── streamlit_app/             ← Tier 1: Streamlit UI (Docker container)
│   ├── Dockerfile             ← Python 3.11 + streamlit
│   ├── app.py                 ← Orchestrator: caching, navigation, state
│   ├── config.py              ← Cloud Function URLs + UI constants
│   ├── api_client.py          ← HTTP calls to backend + Cloud Functions
│   ├── ui_components.py       ← All Streamlit rendering (glassmorphic design)
│   └── requirements.txt
│
└── cloud_functions/           ← Google Cloud Functions (reference copies)
    ├── movies_search/         ← SQL full-text search with filters
    ├── movies_autocomplete/   ← SQL LIKE autocomplete (ES fallback)
    ├── movie_details/         ← TMDB API: poster, cast, providers
    └── movies_sample/         ← Random movie samples
```

---

## Evaluation Checklist

| Requirement | Status |
|---|---|
| Movie recommendation functionality | Implemented (BQML Matrix Factorization + similar users + popular fallback) |
| 2-tier structure (separate Docker containers) | Backend (Flask) + Frontend (Streamlit) on Cloud Run |
| Elasticsearch for autocomplete | Elastic Cloud with `search_as_you_type` mapping, prefix + bool_prefix + Python re-ranking |
| Cold start handling | Overlap-based user similarity → cross-dataset filtering → ML.RECOMMEND |
| Movie posters | TMDB API via Cloud Function (`movie_details`) |
| Multiple movie selection | Users like movies via ❤️ on detail pages; liked movies seed recommendations |
| Generic recommendations (no selection) | Top-10 popular movies (rating_count DESC, avg_rating DESC) |
| Dockerized | Both services have Dockerfiles + docker-compose.yml for local dev |
| Deployed on Google Cloud | Cloud Run (europe-west6) |
| SQL queries logged in terminal | All BigQuery queries printed to stdout via `run_bigquery_to_dicts()` |
