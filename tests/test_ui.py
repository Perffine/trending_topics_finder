from __future__ import annotations

from datetime import timedelta

from app.models import JobRun, SourceItem, TopicCluster, TrendSnapshot
from app.utils import utc_now


def test_public_pages_render_with_zero_data(client) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "No qualified signals yet" in response.text
    scoreboard = client.get("/scoreboard")
    assert scoreboard.status_code == 200
    assert "No predictions evaluated" in scoreboard.text


def test_dashboard_renders_a_ranked_topic(client) -> None:
    now = utc_now()
    with client.app.state.database.session() as session:
        cluster = TopicCluster(
            canonical_title="Toronto waterfront night market opens",
            short_description=None,
            created_at=now,
            first_seen_at=now - timedelta(hours=2),
            last_seen_at=now,
            item_count=2,
            source_count=2,
            current_trend_score=81,
            state="emerging",
        )
        session.add(cluster)
        session.flush()
        session.add(
            SourceItem(
                external_id="one",
                source_name="GTA News",
                source_type="local_news",
                title="A waterfront night market opens Friday",
                normalized_title="a waterfront night market opens friday",
                url="https://example.com/story",
                canonical_url="https://example.com/story",
                published_at=now,
                fetched_at=now,
                categories=[],
                raw_metadata={},
                cluster_id=cluster.id,
            )
        )
        session.add(
            TrendSnapshot(
                cluster_id=cluster.id,
                observed_at=now,
                mentions_1h=2,
                mentions_6h=4,
                mentions_previous_6h=1,
                mentions_24h=4,
                unique_sources_6h=2,
                unique_sources_24h=2,
                velocity=85,
                acceleration=78,
                source_diversity=44,
                external_interest=0,
                novelty=97,
                freshness=96,
                saturation_penalty=0,
                growth_percent_6h=300,
                trend_score=81,
            )
        )
        session.add(
            JobRun(
                job_name="phase_b_pipeline",
                started_at=now,
                finished_at=now,
                status="succeeded",
                counts={},
            )
        )
        session.commit()
    response = client.get("/")
    assert response.status_code == 200
    assert "Toronto waterfront night market opens" in response.text
    assert "Velocity" in response.text
    assert "GTA News" in response.text


def test_internal_jobs_are_protected_and_health_checks_database(client) -> None:
    assert client.post("/internal/jobs/cluster").status_code == 401
    authorized = client.post(
        "/internal/jobs/cluster",
        headers={"Authorization": "Bearer test-job-token"},
    )
    assert authorized.status_code == 200
    assert client.get("/healthz").json() == {"status": "ok", "database": "connected"}
