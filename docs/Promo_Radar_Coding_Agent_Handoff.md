# Promo Radar
## Coding Agent Handoff / MVP Build Specification

**Purpose:** Build a small Google Cloud-hosted web application that continuously detects emerging news/culture topics, applies editorial judgment, matches promising topics to upcoming library programs, and presents a ranked daily Top 10 promotion list. A second dashboard measures whether the system's trend predictions were actually correct.

**Working name:** Promo Radar (rename freely)
**Primary timezone:** America/Toronto
**Primary users:** Library staff selecting programs to promote
**Product principle:** Detect *what is becoming interesting*, not merely what is already popular.

---

## 1. MVP Outcome

At the end of the MVP, a staff member should be able to open a minimal HTML dashboard and immediately see:

1. The 10 strongest current promotion opportunities.
2. The news/topic cluster that caused each recommendation.
3. A short explanation of why the topic is heating up.
4. Relevant upcoming library programs that could ride the trend.
5. Trend, editorial, program-match, and overall opportunity scores.
6. A confidence level and estimated shelf life.
7. Links to representative source stories and to the relevant library programs.

A second page, **Scoreboard**, should show how well previous predictions performed at 6, 12, 24, and 48 hours and summarize accuracy over time.

The MVP does **not** need to autonomously publish promotions, post to social media, buy ads, or replace human editorial review.

---

## 2. System Pipeline

```text
RSS / APIs / Trends
        ↓
headline database
        ↓
topic clustering + deduplication
        ↓
trend velocity calculation
        ↓
LLM editorial scoring
        ↓
match against library programs
        ↓
rank promotion opportunities
        ↓
daily/current Top 10 dashboard
        ↓
prediction snapshots
        ↓
6h / 12h / 24h / 48h self-check
        ↓
Scoreboard + calibration history
```

The architecture should deliberately separate **observable signals** from **LLM judgment**. The LLM may interpret a trend, but it must not invent the trend signal itself.

---

## 3. Recommended MVP Stack

### Backend
- Python 3.12+
- FastAPI
- SQLAlchemy + Alembic
- PostgreSQL in production
- `pgvector` if available for embedding similarity
- `feedparser` for RSS/Atom
- `httpx` for API calls
- Pydantic models for all structured LLM responses

### Frontend
Keep it intentionally boring and fast:
- Server-rendered HTML using Jinja2
- Plain CSS or a very small CSS framework
- Optional HTMX for refresh/filter interactions
- No React/Vue build pipeline for MVP
- Responsive enough to work on desktop and phone

### Google Cloud
- Cloud Run: web app/API
- Cloud SQL for PostgreSQL: persistent data
- Cloud Scheduler: ingestion, scoring, and evaluation triggers
- Secret Manager: API keys and DB credentials
- Cloud Logging: structured job/application logs
- Optional Cloud Storage: raw source snapshots or exported reports

### LLM provider
Create a small provider abstraction rather than hard-coding a model. Configuration should select:
- editorial/scoring model
- embedding model
- API key

Use low-cost models initially. The scoring prompt and structured response format matter more than using the largest model.

---

## 4. Data Sources

Build sources as adapters. Every adapter should output the same normalized `SourceItem` structure.

### Start with 3-5 reliable sources
Good MVP categories:
- RSS/Atom feeds from major and local news outlets
- Google News RSS searches for selected beats/keywords
- Wikipedia pageview signals
- Reddit via approved API/RSS where practical
- A trends/search-interest provider if available

Optional later:
- YouTube Data API
- GDELT or another broad news/event feed
- Bluesky/Mastodon
- event calendars
- entertainment/game release calendars

Do not block the MVP on obtaining every source. A useful first version can operate on RSS + one independent popularity signal.

### Normalized source item

```python
SourceItem(
    external_id: str,
    source_name: str,
    source_type: str,
    title: str,
    summary: str | None,
    url: str,
    published_at: datetime,
    fetched_at: datetime,
    author: str | None,
    categories: list[str],
    engagement_value: float | None,
    engagement_type: str | None,
    raw_metadata: dict,
)
```

Store source name/type separately so source diversity can be measured.

---

## 5. Database Model

Use migrations from the beginning. Suggested core tables:

### `source_items`
- id
- external_id
- source_name
- source_type
- title
- normalized_title
- summary
- url
- published_at
- fetched_at
- engagement_value
- raw_metadata JSONB
- embedding vector (optional)
- cluster_id nullable
- duplicate_of_id nullable

Unique constraint should prevent the same external item from being inserted repeatedly.

### `topic_clusters`
- id
- canonical_title
- short_description
- created_at
- last_seen_at
- first_seen_at
- item_count
- source_count
- embedding/centroid
- current_trend_score
- current_editorial_score
- breakout_probability
- estimated_shelf_life_hours
- state (`emerging`, `hot`, `cooling`, `stale`)

### `trend_snapshots`
Time-series values for each topic:
- id
- cluster_id
- observed_at
- mentions_1h
- mentions_6h
- mentions_24h
- unique_sources_6h
- unique_sources_24h
- external_interest_signal
- velocity
- acceleration
- novelty
- trend_score

### `editorial_scores`
Keep LLM output auditable:
- id
- cluster_id
- scored_at
- model/provider
- prompt_version
- novelty
- public_curiosity
- conversation_potential
- cultural_significance
- local_relevance
- library_relevance
- promotability
- shelf_life_score
- clickbait_risk
- breakout_probability
- estimated_shelf_life_hours
- explanation
- tags JSONB
- full_response JSONB

### `library_programs`
- id
- external_id
- title
- description
- branch/location
- start_at
- end_at
- audience
- tags
- url
- status
- embedding
- imported_at

### `program_matches`
- id
- cluster_id
- program_id
- matched_at
- semantic_similarity
- keyword_overlap
- timing_score
- local_relevance_score
- match_score
- rationale

### `opportunity_rankings`
Snapshot the final rankings so history is preserved:
- id
- ranking_date
- generated_at
- rank
- cluster_id
- trend_score
- editorial_score
- program_match_score
- overall_score
- why_now
- suggested_angle
- confidence

### `predictions`
- id
- cluster_id
- prediction_time
- predicted_probability
- predicted_trend_score
- predicted_rank
- horizon_hours
- baseline_metrics JSONB
- evaluation_due_at
- evaluated_at nullable
- actual_metrics JSONB nullable
- outcome_label nullable
- brier_score nullable
- growth_ratio nullable

### `staff_feedback`
For future taste learning:
- id
- ranking_id or cluster_id
- created_at
- rating (`great`, `maybe`, `nope`)
- optional_note

---

## 6. Ingestion and Deduplication

### Frequency
Default: every 15 minutes.

### Steps
1. Fetch each configured source.
2. Normalize timestamps and titles.
3. Create a normalized title: lowercase, strip punctuation/boilerplate, collapse whitespace.
4. Exact-dedupe by canonical URL/external ID where possible.
5. Fuzzy-dedupe obvious syndicated copies.
6. Insert new items only.
7. Generate embeddings only for genuinely new items.

Do not treat syndicated copies from 30 outlets as 30 independent confirmations. Track the difference between **article count** and **independent source count**.

---

## 7. Topic Clustering

The goal is to turn dozens of headlines about the same underlying event into one topic.

### MVP approach
For each unclustered item from a recent rolling window (suggested: 48 hours):
1. Compare its embedding with active cluster centroids.
2. Require a minimum semantic similarity threshold.
3. Add simple named-entity/keyword overlap as a guardrail.
4. Attach it to the best cluster if above threshold.
5. Otherwise create a new cluster.
6. Recalculate the cluster centroid and canonical title.

Start with a configurable similarity threshold around **0.80-0.85** and tune from observed results. Do not bury this value in code.

### Cluster title
The canonical title can be generated cheaply by an LLM only after the cluster contains multiple items, e.g.:

> "Nintendo announces new mainline Zelda game"

not:

> "Fans are losing their minds over this huge Nintendo reveal"

Prefer factual, neutral labels.

---

## 8. Trend Velocity / Hotness Score

This should be deterministic and inspectable.

For each cluster calculate normalized 0-100 components:
- `velocity`: how fast mentions are increasing
- `acceleration`: whether velocity itself is rising
- `source_diversity`: number/quality of independent source types
- `external_interest`: search/pageview/social interest when available
- `novelty`: uncommon/new versus perpetually popular topic
- `freshness`: penalty as the story ages
- `saturation`: penalty for topics that have already been overwhelmingly dominant for a long period

Suggested starting formula:

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

Clamp to 0-100.

### Important principle
A topic with 500 → 8,000 mentions may outrank one with 50,000 → 52,000 mentions. We are searching for **change in attention**, not absolute attention.

Store every component so the UI can explain why a score is high.

---

## 9. LLM Editorial / "Taste" Scoring

Only send the LLM a **cluster summary**, not every raw article. Provide:
- neutral cluster title
- representative headlines (max ~8)
- first/last seen
- source count
- trend metrics
- local/Canadian source indicators
- optional external interest signals

The model must return strict JSON validated by Pydantic.

### Editorial dimensions (0-100)
- novelty
- public curiosity
- conversation potential
- cultural significance
- local relevance
- library relevance
- promotability
- shelf-life quality
- clickbait/artificial-hype risk
- breakout probability

Also return:
- `estimated_shelf_life_hours`
- `explanation` (2-4 sentences)
- `topic_tags`
- `promotion_angles` (max 3 short suggestions)

### Editorial score
Suggested starting formula:

```text
EditorialScore =
    0.15 * novelty
  + 0.20 * public_curiosity
  + 0.15 * conversation_potential
  + 0.10 * cultural_significance
  + 0.10 * local_relevance
  + 0.15 * library_relevance
  + 0.15 * promotability
  - clickbait_penalty
```

Keep the raw dimensions visible; the aggregate is merely a sorting convenience.

### Prompt rule
The LLM must be told explicitly:
- Do not inflate a score because a famous person/topic is inherently popular.
- Reward unusual upward movement and plausible public curiosity.
- Penalize repetitive outrage/clickbait without meaningful library relevance.
- Distinguish "already huge" from "becoming hot now."
- Avoid political/ideological favoritism; judge promotion usefulness and observed attention.

Version every prompt (`EDITORIAL_PROMPT_VERSION=v1`).

---

## 10. Library Program Matching

### Program import
MVP should accept a CSV upload or scheduled CSV fetch with columns similar to:

```text
external_id,title,description,branch,start_at,end_at,audience,tags,url,status
```

Only match active future programs, defaulting to the next 60 days.

### Matching
For each high-scoring topic:
1. Embed the topic summary.
2. Retrieve the nearest program embeddings.
3. Add keyword/tag overlap.
4. Add timing compatibility: a fast 24-hour meme is a poor match for an event 7 weeks away.
5. Add local relevance where applicable.
6. Ask the LLM for a short rationale only for the top candidate matches.

Suggested formula:

```text
ProgramMatchScore =
    0.60 * semantic_similarity
  + 0.15 * keyword_overlap
  + 0.15 * timing_score
  + 0.10 * local_relevance
```

Return the best 1-5 matching programs. If no program is a credible match, say so; do not force one.

---

## 11. Final Opportunity Ranking

Suggested starting formula:

```text
OverallOpportunityScore =
    0.45 * TrendScore
  + 0.35 * EditorialScore
  + 0.20 * ProgramMatchScore
```

Apply hard/soft rules afterward:
- suppress stale topics
- suppress clusters with insufficient independent evidence
- suppress inappropriate/unsafe promotional pairings
- avoid more than 2 near-identical topics in the Top 10
- optionally reserve 1-2 slots for local/emerging/serendipitous stories

The final Top 10 should feel like an editor's page, not a list sorted by celebrity fame.

---

## 12. Dashboard Page 1: Promo Radar

Route: `/`

Visual direction: **simple/minimal HTML**, closer to an old-school useful web tool than a glossy SaaS dashboard.

### Header
- Promo Radar
- Last updated timestamp
- Manual `Refresh` button
- Links: `Top 10` | `Scoreboard`

### Summary strip
Show small text metrics:
- items scanned (24h)
- active topic clusters
- emerging/hot clusters
- programs indexed
- next scheduled refresh

### Top 10 table/cards
Each row/card should show:

**#1 Topic Title** — Overall 91

- `TREND 94` `EDITORIAL 86` `PROGRAM 92`
- State: Emerging / Hot / Cooling
- Confidence: High/Medium/Low
- Why now: 1-2 sentence explanation
- Signal: e.g. `+340% 6h · 9 independent sources · Wikipedia +180%`
- Shelf life: e.g. `~36 hours`
- Best library match(es): title + date + branch + link
- Suggested angle: one short promotional hook
- Representative source links: 2-4
- Staff buttons: `👍 Great` `😐 Maybe` `👎 Nope`

### Filters
Keep lightweight:
- All / Local / Books / Tech / Entertainment / Science / Kids-Teens / Other
- Emerging / Hot / Cooling
- Optional minimum program-match score

No complex charting is required for MVP. Tiny sparkline SVGs may be added later.

---

## 13. Dashboard Page 2: Prediction Scoreboard

Route: `/scoreboard`

Purpose: force the system to prove it has a nose for trends.

### Top summary metrics
For trailing 7 / 30 / 90 days:
- Precision@10: percentage of daily Top 10 predictions that later qualified as a breakout
- Average Brier score (lower is better)
- Mean lead time before peak/hot state
- Correct direction rate
- Number of evaluated predictions

### Prediction table
Columns:
- Prediction time
- Topic
- Rank at prediction
- Predicted breakout probability
- 6h result
- 12h result
- 24h result
- 48h result
- Peak growth
- Outcome (`Hit`, `Partial`, `Miss`)
- Brier score

Clicking a topic may expand:
- baseline signals
- subsequent measurements
- representative headlines at prediction time
- editorial explanation originally given

### Calibration section
Bucket predictions by probability:

```text
Predicted 0-20%   → actual breakout rate
Predicted 21-40%  → actual breakout rate
Predicted 41-60%  → actual breakout rate
Predicted 61-80%  → actual breakout rate
Predicted 81-100% → actual breakout rate
```

This exposes overconfidence quickly.

---

## 14. Defining a "Breakout" for Self-Scoring

The definition must be objective and stored in configuration.

Suggested initial 24-hour breakout rule:

A prediction is a **Hit** if, compared with the baseline snapshot, at least two of the following are true:
- mention rate grows by >= 100%
- independent source count grows by >= 50% and by at least 2 sources
- external interest signal grows by >= 75%
- trend score rises by >= 20 points and reaches >= 70

A **Partial** occurs if attention grows materially but misses the breakout threshold.
A **Miss** occurs if the topic stays flat or declines.

These thresholds are starting values, not sacred constants. Put them in settings/environment configuration.

### Probability accuracy
For Hit vs non-Hit, calculate a Brier score:

```text
Brier = (predicted_probability - actual_outcome)^2
```

Use probability as 0.0-1.0 and outcome as 1 for Hit, 0 otherwise.

Also preserve the raw metrics; never reduce evaluation to a single score.

---

## 15. Scheduling

All times should be stored in UTC; display in America/Toronto.

Suggested jobs:

```text
Every 15 min: ingest_sources
Every 15 min: cluster_new_items
Every 30 min: compute_trend_snapshots
Every 60 min: score_hot_clusters + program matching
Daily ~06:30: create daily Top 10 snapshot
Every 60 min: evaluate_due_predictions
Daily ~02:00: cleanup/archive stale working data
```

For MVP, Cloud Scheduler can call authenticated internal job routes on Cloud Run. Make each job idempotent and safe to retry.

Suggested internal routes:

```text
POST /internal/jobs/ingest
POST /internal/jobs/cluster
POST /internal/jobs/trends
POST /internal/jobs/score
POST /internal/jobs/rank
POST /internal/jobs/evaluate
```

Protect internal job routes using Cloud Run/IAM identity rather than an easily guessed shared URL.

---

## 16. Public/Application Routes

```text
GET  /                      Top 10 dashboard
GET  /scoreboard            prediction scoreboard
GET  /topic/{id}            optional detail page
POST /feedback/{cluster_id} staff Great/Maybe/Nope feedback
POST /admin/programs/import CSV import (protect this route)
GET  /healthz               health check
```

Optional JSON API for future MCP/tool integration:

```text
GET /api/opportunities?limit=10
GET /api/topics/{id}
GET /api/scoreboard
GET /api/programs
```

Do not make MCP a blocking dependency for the initial web product. If an MCP server is later desired, expose these same application services through thin MCP tools such as `get_top_opportunities`, `get_topic`, and `get_scoreboard`.

---

## 17. Suggested Project Layout

```text
promo-radar/
├── app/
│   ├── main.py
│   ├── config.py
│   ├── db.py
│   ├── models/
│   ├── schemas/
│   ├── routes/
│   │   ├── dashboard.py
│   │   ├── api.py
│   │   ├── feedback.py
│   │   └── jobs.py
│   ├── services/
│   │   ├── ingestion.py
│   │   ├── dedupe.py
│   │   ├── clustering.py
│   │   ├── trend_scoring.py
│   │   ├── editorial.py
│   │   ├── program_matching.py
│   │   ├── ranking.py
│   │   └── evaluation.py
│   ├── sources/
│   │   ├── base.py
│   │   ├── rss.py
│   │   ├── wikipedia.py
│   │   └── ...
│   ├── llm/
│   │   ├── provider.py
│   │   ├── prompts.py
│   │   └── schemas.py
│   ├── templates/
│   └── static/
├── migrations/
├── tests/
├── scripts/
├── Dockerfile
├── pyproject.toml
├── .env.example
└── README.md
```

---

## 18. Environment Variables

Provide `.env.example` with at least:

```text
DATABASE_URL=
APP_BASE_URL=
APP_TIMEZONE=America/Toronto
LLM_PROVIDER=
LLM_API_KEY=
LLM_EDITORIAL_MODEL=
LLM_EMBEDDING_MODEL=
EDITORIAL_PROMPT_VERSION=v1
CLUSTER_SIMILARITY_THRESHOLD=0.83
ACTIVE_CLUSTER_HOURS=48
PROGRAM_LOOKAHEAD_DAYS=60
MIN_TOPIC_EVIDENCE=2
BREAKOUT_MENTION_GROWTH=2.0
BREAKOUT_SOURCE_GROWTH=1.5
BREAKOUT_EXTERNAL_GROWTH=1.75
BREAKOUT_TREND_SCORE_MIN=70
```

Never commit keys.

---

## 19. Observability and Failure Behaviour

The dashboard should still load if one source or the LLM is temporarily down.

Required behaviours:
- log source fetch failures individually
- continue ingesting other sources
- retry transient HTTP failures with backoff
- record LLM parse/failure state instead of silently substituting invented scores
- show last successful refresh time in the UI
- never delete a previous Top 10 solely because the current scoring job failed
- include job start/end/count/error structured logs

Add `/healthz` and basic database connectivity checks.

---

## 20. Taste Learning: Phase 2

Do **not** train a model in MVP. Collect the data first.

Staff feedback buttons create the future training set:
- Great = +1
- Maybe = 0
- Nope = -1

After a few hundred judgments, investigate a small learned ranker using features such as:
- trend components
- editorial dimensions
- topic category
- local relevance
- program-match score
- shelf life
- staff feedback

The learned ranker can eventually adjust the hand-written weights. Keep the human feedback and automated breakout outcome as two separate targets: one measures **editorial taste**, the other measures **predictive accuracy**.

---

## 21. Safety / Editorial Guardrails

This is a recommendation tool for human staff, not an automated publisher.

Include:
- source links so every recommendation is inspectable
- no fabricated facts in `why_now`
- clear distinction between measured signals and LLM interpretation
- suppression/flagging for breaking tragedies where opportunistic promotion would be inappropriate
- optional `sensitivity_risk` field in editorial scoring
- configurable exclusion keywords/categories
- no demographic profiling of library users

The system should recommend *topics and program connections*, not target individuals.

---

## 22. Tests Required for MVP

### Unit
- title normalization
- exact/fuzzy dedupe
- trend-score calculations
- saturation/freshness penalties
- final ranking formula
- breakout evaluation rules
- Brier score
- program timing score

### Integration
- feed adapter → database
- cluster assignment
- mocked LLM structured response
- program CSV import
- ranking snapshot creation
- prediction → scheduled evaluation lifecycle

### UI smoke tests
- `/` renders with zero data
- `/` renders Top 10
- `/scoreboard` renders before any predictions are evaluated
- feedback buttons save correctly
- one failed source does not break page rendering

Use deterministic fixtures containing a deliberately emerging topic and a perpetually popular topic. The emerging topic should outrank the static-popular topic when its velocity is much higher.

---

## 23. MVP Definition of Done

The build is MVP-complete when all of the following are true:

- [ ] Cloud Run-hosted dashboard loads successfully.
- [ ] At least 3 source adapters ingest on a schedule.
- [ ] Duplicate/syndicated headlines are substantially collapsed.
- [ ] Items are grouped into meaningful topic clusters.
- [ ] Each active cluster receives deterministic trend metrics.
- [ ] Promising clusters receive structured LLM editorial scores.
- [ ] Library programs can be imported and matched to topics.
- [ ] `/` displays a ranked Top 10 with explanations, scores, sources, and program matches.
- [ ] Every ranked topic creates prediction snapshots.
- [ ] Predictions are evaluated automatically at 6/12/24/48 hours.
- [ ] `/scoreboard` displays historical hits/misses and aggregate accuracy.
- [ ] Staff Great/Maybe/Nope feedback is stored.
- [ ] Failed feeds/LLM calls degrade gracefully.
- [ ] Secrets are stored outside source control.
- [ ] README contains local run, migration, test, and Google Cloud deploy instructions.

---

## 24. Recommended Build Order for the Coding Agent

### Phase A - Skeleton
1. FastAPI + Jinja app
2. PostgreSQL models/migrations
3. Empty Top 10 and Scoreboard pages
4. Dockerfile and local configuration

### Phase B - News pipeline
5. RSS source adapter
6. ingestion + dedupe
7. clustering
8. deterministic trend scoring
9. dashboard populated from real clusters

### Phase C - Editorial intelligence
10. LLM provider abstraction
11. structured editorial prompt/schema
12. score only sufficiently active clusters
13. final opportunity ranking

### Phase D - Library connection
14. program CSV import
15. program embeddings/matching
16. display best matches and suggested promotional angles

### Phase E - Self-evaluation
17. prediction snapshots
18. 6/12/24/48 evaluation jobs
19. Scoreboard metrics/calibration

### Phase F - Cloud deployment
20. Cloud SQL
21. Cloud Run
22. Secret Manager
23. Cloud Scheduler jobs
24. logging/health checks

### Phase G - Feedback
25. Great/Maybe/Nope controls
26. store editorial feedback for future learning

---

## 25. First Coding-Agent Instruction

Start by implementing **Phases A and B only**. Do not begin with the LLM.

The first milestone should prove that the system can ingest live headlines, deduplicate them, cluster them into topics, calculate explainable velocity-based trend scores, and render a useful `/` page from real data.

Once that works, add editorial scoring. This prevents the project from becoming an expensive news summarizer with no trustworthy trend signal.

**Core product question to preserve throughout the build:**

> "What is becoming unusually interesting right now, and which upcoming library program has a credible reason to join that conversation?"

