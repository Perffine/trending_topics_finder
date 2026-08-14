# Promo Radar

**Find what is becoming interesting, not merely what is already popular.**

Promo Radar is a small, inspectable trend-detection application for library staff in the Greater Toronto Area. It collects live news headlines, collapses duplicates, groups related stories, measures how quickly attention is changing, and presents the strongest current signals in a server-rendered dashboard.

The project is guided by one question:

> What is becoming unusually interesting right now, and which upcoming library program has a credible reason to join that conversation?

## Project status

Phases A and B of the [coding-agent handoff](docs/Promo_Radar_Coding_Agent_Handoff.md) are implemented.

| Capability | Status |
| --- | --- |
| FastAPI and Jinja dashboard | Complete |
| PostgreSQL models and Alembic migration | Complete |
| Live RSS/Atom ingestion | Complete |
| Exact and fuzzy deduplication | Complete |
| Deterministic TF-IDF topic clustering | Complete |
| Explainable trend scoring | Complete |
| Protected scheduler endpoints | Complete |
| Editorial LLM scoring | Planned, Phase C |
| Library program matching | Planned, Phase D |
| Prediction evaluation and calibration | Planned, Phase E |
| Automated Google Cloud deployment | Planned, Phase F |
| Staff feedback controls | Planned, Phase G |

No LLM or embedding provider is called in the current version. The dashboard ranks **observable signal strength**, not final editorial opportunity. This boundary is intentional: measured activity should remain separate from model judgment.

## How it works

```text
GTA and Canadian RSS feeds
            |
            v
 normalized source items
            |
            v
 exact + syndicated deduplication
            |
            v
 TF-IDF and keyword topic clustering
            |
            v
 deterministic trend snapshots
            |
            v
 public Top 10 signal dashboard
```

The default feed set includes:

- CBC Toronto
- CityNews Toronto
- Global News Toronto
- CBC Arts
- CBC Technology & Science

Each feed uses the same adapter and normalized data contract. A failing source is logged independently and does not prevent the remaining sources or dashboard from working.

## Highlights

- PostgreSQL-first persistence with SQLAlchemy and Alembic
- One reusable RSS/Atom adapter with retries and per-source failure isolation
- Canonical URL and external-ID deduplication
- Conservative fuzzy detection for syndicated headlines
- Deterministic TF-IDF similarity with keyword-overlap guardrails
- Stored trend components for auditing and tuning
- Responsive public dashboard with a cooldown-protected manual scan
- Public empty-state Scoreboard ready for later prediction work
- Bearer-token protection for internal scheduler routes
- Structured JSON application and job logs
- Native operating-system certificate trust without disabling TLS verification
- SQLite-backed deterministic tests that do not require live feeds

## Technology

| Area | Choice |
| --- | --- |
| Application | Python 3.12+, FastAPI |
| HTML | Jinja2, server-rendered templates |
| Styling | Plain responsive CSS |
| Database | PostgreSQL 16 |
| ORM and migrations | SQLAlchemy 2, Alembic |
| HTTP and feeds | HTTPX, feedparser |
| Configuration | Pydantic Settings |
| Local infrastructure | Docker Compose |
| Tests and quality | pytest, Ruff |

## Quick start with Docker

Docker Desktop or another Compose-compatible Docker installation is required.

1. Create the local environment file.

```powershell
Copy-Item .env.example .env
```

On macOS or Linux:

```bash
cp .env.example .env
```

2. Replace `JOB_TOKEN` in `.env` with a long random value. Do not commit `.env`.

3. Build and start the application and PostgreSQL.

```powershell
docker compose up --build
```

4. Open [http://localhost:8000](http://localhost:8000).

The web container waits for PostgreSQL, runs `alembic upgrade head`, and then starts the application. Select **Run fresh scan** to fetch the configured feeds and populate the first dashboard. The first scan can take several seconds.

Useful local URLs:

| URL | Purpose |
| --- | --- |
| `http://localhost:8000/` | Current Top 10 signal dashboard |
| `http://localhost:8000/scoreboard` | Prediction Scoreboard empty state |
| `http://localhost:8000/healthz` | Application and database health |
| `http://localhost:8000/docs` | FastAPI route documentation |

Stop the stack with:

```powershell
docker compose down
```

PostgreSQL data is stored in the `promo_radar_postgres` Docker volume, so a normal stop or rebuild does not discard it.

## Run without Docker

You need Python 3.12 or newer and a reachable PostgreSQL database.

1. Create and activate a virtual environment.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

2. Install the application and development dependencies.

```powershell
python -m pip install -e ".[dev]"
```

3. Create `.env` and update `DATABASE_URL` and `JOB_TOKEN`.

```powershell
Copy-Item .env.example .env
```

4. Apply migrations and start the server.

```powershell
alembic upgrade head
uvicorn app.main:app --reload
```

Run the complete Phase B pipeline directly from the terminal with:

```powershell
python scripts/run_pipeline.py
```

The runner also accepts a temporary database override, which is useful for diagnostics:

```powershell
python scripts/run_pipeline.py --database-url postgresql+psycopg://user:password@localhost:5432/promo_radar
```

## Pipeline behavior

The full pipeline performs three idempotent stages:

1. **Ingest:** fetch feeds, normalize entries, remove exact repeats, and mark probable syndicated copies.
2. **Cluster:** assign recent non-duplicate items to active topics using TF-IDF similarity and keyword overlap, or create a new topic.
3. **Score:** write a time-stamped trend snapshot and update each topic's current state and score.

All timestamps are stored in UTC and displayed in `America/Toronto` by default.

### Trend score

Every component is normalized to `0-100` and stored in `trend_snapshots`:

```text
TrendScore =
    0.30 * velocity
  + 0.15 * acceleration
  + 0.20 * source_diversity
  + 0.15 * external_interest
  + 0.10 * novelty
  + 0.10 * freshness
  - saturation_penalty
```

The scoring model rewards changes in attention. A rapidly growing topic can outrank a much larger topic whose coverage is flat.

The RSS-only milestone does not invent an external-interest signal. That component remains zero until an independent source such as pageviews or search interest is added.

### Evidence and states

`MIN_TOPIC_EVIDENCE=2` prevents a single independent item from entering the public Top 10. Syndicated copies are retained for auditability but do not count as independent confirmation.

Active topics are labelled:

| State | Meaning |
| --- | --- |
| `emerging` | Recent topic with stable or upward measured movement |
| `hot` | Strong score with positive velocity |
| `cooling` | Recent topic whose velocity has fallen |
| `stale` | Outside the active window or without recent evidence |

## Configuration

Copy `.env.example` to `.env` and override only what your environment needs.

### Application and database

| Variable | Default | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | Local PostgreSQL URL | SQLAlchemy database connection |
| `APP_BASE_URL` | `http://localhost:8000` | Public application origin |
| `APP_TIMEZONE` | `America/Toronto` | Dashboard display timezone |
| `ENVIRONMENT` | `development` | Runtime environment label |
| `JOB_TOKEN` | Placeholder | Protects internal job routes |
| `HTTP_USER_AGENT` | Promo Radar identifier | Identifies outbound feed requests |

### Ingestion and clustering

| Variable | Default | Purpose |
| --- | --- | --- |
| `RSS_FEEDS_JSON` | Built-in feed list | Replaces all configured feeds |
| `INGEST_LOOKBACK_HOURS` | `48` | Recent window used during deduplication |
| `ACTIVE_CLUSTER_HOURS` | `48` | Active topic-clustering window |
| `FUZZY_DEDUPE_THRESHOLD` | `0.93` | Syndicated-title similarity threshold |
| `TFIDF_CLUSTER_THRESHOLD` | `0.32` | Minimum TF-IDF similarity for assignment |
| `KEYWORD_OVERLAP_THRESHOLD` | `0.20` | Required lexical overlap guardrail |
| `MIN_TOPIC_EVIDENCE` | `2` | Minimum independent items for the Top 10 |
| `PUBLIC_REFRESH_COOLDOWN_SECONDS` | `300` | Minimum time between public manual scans |

Settings for embeddings, LLM editorial scoring, programs, and breakout evaluation are already reserved in `.env.example`, but they are not active in Phases A and B.

### Custom feeds

Set `RSS_FEEDS_JSON` to a JSON array. Each entry needs a name and URL; `source_type` and `region` support later filtering and source-diversity analysis.

```json
[
  {
    "name": "Example GTA News",
    "url": "https://example.org/feed.xml",
    "source_type": "local_news",
    "region": "GTA"
  },
  {
    "name": "Example Culture Desk",
    "url": "https://example.net/culture.rss",
    "source_type": "culture",
    "region": "Canada"
  }
]
```

When placing JSON in an environment file, keep the entire value on one line.

## Routes

### Public routes

| Method | Route | Purpose |
| --- | --- | --- |
| `GET` | `/` | Render the current Top 10 signals |
| `POST` | `/refresh` | Run the full pipeline, subject to cooldown and lock |
| `GET` | `/scoreboard` | Render the prediction Scoreboard empty state |
| `GET` | `/healthz` | Check application and database health |

The dashboard is intentionally public in this milestone. Internal jobs remain protected.

### Internal job routes

| Method | Route | Purpose |
| --- | --- | --- |
| `POST` | `/internal/jobs/ingest` | Fetch and store configured feeds |
| `POST` | `/internal/jobs/cluster` | Cluster recent unassigned items |
| `POST` | `/internal/jobs/trends` | Compute current trend snapshots |
| `POST` | `/internal/jobs/pipeline` | Run ingest, cluster, and score together |

Every internal request needs the configured bearer token:

```text
Authorization: Bearer <JOB_TOKEN>
```

PowerShell example:

```powershell
$headers = @{ Authorization = "Bearer replace-with-your-job-token" }
Invoke-RestMethod -Method Post -Uri http://localhost:8000/internal/jobs/pipeline -Headers $headers
```

The combined pipeline uses an application lock to reject overlapping work on the same instance. Its public Refresh action also checks the most recent successful job before starting another scan.

## Database and migrations

The first migration creates:

| Table | Purpose |
| --- | --- |
| `source_items` | Normalized feed entries and duplicate relationships |
| `topic_clusters` | Active topic identity and current state |
| `trend_snapshots` | Auditable time-series metrics and score components |
| `job_runs` | Durable pipeline status, counts, and errors |

Apply all pending migrations:

```powershell
alembic upgrade head
```

Create a migration after changing SQLAlchemy models:

```powershell
alembic revision --autogenerate -m "describe the schema change"
```

Review generated migrations before applying or committing them.

## Tests and quality checks

The tests use a temporary SQLite database and mocked feed data. They do not require Docker, PostgreSQL, or live internet access.

```powershell
python -m pytest
```

Run static analysis and formatting checks:

```powershell
python -m ruff check app tests scripts migrations
python -m ruff format --check app tests scripts migrations
```

The suite covers:

- Title and URL normalization
- Exact and fuzzy deduplication
- RSS parsing and ingestion idempotency
- Deterministic cluster assignment
- Trend-score bounds and calculations
- Emerging-topic versus static-popular ranking behavior
- Empty and populated dashboard rendering
- Internal route authorization
- Database health checks

## Project layout

```text
.
|-- app/
|   |-- main.py                 FastAPI application factory
|   |-- config.py               Environment settings and default feeds
|   |-- db.py                   Engine and session management
|   |-- models/                 SQLAlchemy persistence models
|   |-- routes/                 Dashboard and protected job routes
|   |-- schemas/                Normalized source contracts
|   |-- services/               Ingestion, clustering, scoring, dashboard
|   |-- sources/                Source adapter interfaces and RSS adapter
|   |-- templates/              Server-rendered pages
|   `-- static/                 Responsive dashboard CSS
|-- migrations/                 Alembic environment and revisions
|-- scripts/run_pipeline.py     Command-line pipeline runner
|-- tests/                      Unit, integration, and UI smoke tests
|-- compose.yaml                Local app and PostgreSQL stack
|-- Dockerfile                  Cloud Run-compatible application image
|-- pyproject.toml              Package, dependency, and tool configuration
`-- .env.example                Safe configuration template
```

## Reliability and security

- Feed failures are isolated and logged by source.
- Transient HTTP failures are retried with exponential backoff.
- TLS certificate verification stays enabled and uses the operating system trust store.
- Repeated source items do not create duplicate database records.
- Failed pipeline runs do not erase the previous dashboard results.
- Job start, completion, counts, and errors are recorded in `job_runs`.
- Internal routes fail closed when `JOB_TOKEN` is missing.
- Secrets belong in environment configuration or a secret manager, never source control.
- Source links remain visible so staff can inspect the evidence behind a signal.

The current public refresh lock is process-local. A multi-instance production deployment should add a PostgreSQL advisory lock or another distributed job lock before enabling unrestricted scaling.

## Google Cloud deployment direction

Cloud deployment automation is not part of the current milestone, but the application is structured for:

| Google Cloud service | Responsibility |
| --- | --- |
| Cloud Run | Public FastAPI application |
| Cloud SQL for PostgreSQL | Persistent application data |
| Secret Manager | `DATABASE_URL`, `JOB_TOKEN`, and future provider keys |
| Cloud Scheduler | Authenticated calls to internal pipeline routes |
| Cloud Logging | Structured application and job logs |

Before deploying:

1. Create Cloud SQL and apply `alembic upgrade head` as a controlled deployment job.
2. Store secrets in Secret Manager and expose them to Cloud Run as environment variables.
3. Keep the public dashboard unauthenticated only if that remains intentional.
4. Protect scheduler calls with Cloud Run IAM in addition to the application bearer token.
5. Schedule `/internal/jobs/pipeline` every 15 minutes for the Phase B milestone.
6. Add a distributed pipeline lock before configuring more than one active Cloud Run instance.

The included Docker image listens on the Cloud Run `PORT` environment variable.

## Troubleshooting

### The dashboard is empty

Run a fresh scan and inspect the returned job counts or structured logs. Topics need at least `MIN_TOPIC_EVIDENCE` independent items before they appear. Lowering this value is useful for development but weakens the evidence requirement.

### A feed fails

The remaining feeds should continue normally. Check the source-specific error in logs or the latest `job_runs.counts` value. Confirm that the feed URL still returns valid RSS/Atom and that the configured user agent is appropriate.

### HTTPS requests fail locally

Promo Radar uses the native operating-system certificate store. Ensure required corporate or proxy certificates are installed in that store. Do not disable TLS verification.

### PostgreSQL cannot start in Docker

Check whether local port `5432` is already in use. Change the host-side port in `compose.yaml` if another PostgreSQL instance owns it.

### Internal jobs return `401`

Confirm that the request uses `Authorization: Bearer <JOB_TOKEN>` and that the token matches the running application's environment.

### Internal jobs return `503`

`JOB_TOKEN` is empty, so job execution is intentionally disabled. Configure a token and restart the application.

## Next milestones

The next planned work follows the handoff order:

1. Add a provider-neutral LLM abstraction and strict editorial scoring schema.
2. Import library programs and calculate credible topic-program matches.
3. Create prediction snapshots and evaluate them at 6, 12, 24, and 48 hours.
4. Build calibration and historical accuracy views in the Scoreboard.
5. Deploy through Cloud Run, Cloud SQL, Secret Manager, and Cloud Scheduler.
6. Add Great, Maybe, and Nope staff feedback for future taste learning.

See [docs/Promo_Radar_Coding_Agent_Handoff.md](docs/Promo_Radar_Coding_Agent_Handoff.md) for the full product specification and definition of done.
