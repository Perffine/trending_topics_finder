from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import JobRun, SourceItem, TopicCluster, TrendSnapshot
from app.utils import ensure_utc, utc_now


@dataclass(frozen=True)
class SourceLink:
    title: str
    source_name: str
    url: str


@dataclass(frozen=True)
class Opportunity:
    rank: int
    cluster: TopicCluster
    snapshot: TrendSnapshot
    sources: list[SourceLink]
    confidence: str
    why_now: str


@dataclass(frozen=True)
class DashboardData:
    opportunities: list[Opportunity]
    items_24h: int
    active_clusters: int
    emerging_hot_clusters: int
    programs_indexed: int
    last_updated: datetime | None
    next_refresh: datetime


def confidence_for(cluster: TopicCluster, snapshot: TrendSnapshot) -> str:
    if cluster.source_count >= 3 and snapshot.trend_score >= 70:
        return "High"
    if cluster.source_count >= 2:
        return "Medium"
    return "Low"


def measured_explanation(cluster: TopicCluster, snapshot: TrendSnapshot) -> str:
    if snapshot.growth_percent_6h is None:
        movement = (
            f"{snapshot.mentions_6h} new mention(s) appeared in the last six hours"
        )
    elif snapshot.growth_percent_6h >= 0:
        movement = (
            f"six-hour coverage grew {snapshot.growth_percent_6h:.0f}% "
            "over the preceding window"
        )
    else:
        movement = (
            f"six-hour coverage fell {abs(snapshot.growth_percent_6h):.0f}% "
            "from the preceding window"
        )
    return (
        f"{movement}, with {snapshot.unique_sources_6h} independent source(s). "
        f"Its measured velocity is {snapshot.velocity:.0f}/100."
    )


def _next_quarter_hour(now: datetime) -> datetime:
    minute = ((now.minute // 15) + 1) * 15
    if minute == 60:
        return now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    return now.replace(minute=minute, second=0, microsecond=0)


def get_dashboard_data(session: Session, settings: Settings) -> DashboardData:
    now = utc_now()
    cutoff_24h = now - timedelta(hours=24)
    cutoff_active = now - timedelta(hours=settings.active_cluster_hours)
    latest_snapshot = (
        select(
            TrendSnapshot.cluster_id,
            func.max(TrendSnapshot.observed_at).label("observed_at"),
        )
        .group_by(TrendSnapshot.cluster_id)
        .subquery()
    )
    rows = session.execute(
        select(TopicCluster, TrendSnapshot)
        .join(latest_snapshot, latest_snapshot.c.cluster_id == TopicCluster.id)
        .join(
            TrendSnapshot,
            (TrendSnapshot.cluster_id == latest_snapshot.c.cluster_id)
            & (TrendSnapshot.observed_at == latest_snapshot.c.observed_at),
        )
        .where(
            TopicCluster.last_seen_at >= cutoff_active,
            TopicCluster.source_count >= settings.min_topic_evidence,
            TopicCluster.state != "stale",
        )
        .order_by(TrendSnapshot.trend_score.desc(), TopicCluster.last_seen_at.desc())
        .limit(10)
    ).all()

    opportunities: list[Opportunity] = []
    for rank, (cluster, snapshot) in enumerate(rows, start=1):
        source_rows = session.execute(
            select(SourceItem.title, SourceItem.source_name, SourceItem.url)
            .where(SourceItem.cluster_id == cluster.id)
            .order_by(SourceItem.published_at.desc())
            .limit(4)
        ).all()
        opportunities.append(
            Opportunity(
                rank=rank,
                cluster=cluster,
                snapshot=snapshot,
                sources=[SourceLink(*row) for row in source_rows],
                confidence=confidence_for(cluster, snapshot),
                why_now=measured_explanation(cluster, snapshot),
            )
        )

    items_24h = (
        session.scalar(
            select(func.count(SourceItem.id)).where(
                SourceItem.published_at >= cutoff_24h
            )
        )
        or 0
    )
    active_clusters = (
        session.scalar(
            select(func.count(TopicCluster.id)).where(
                TopicCluster.last_seen_at >= cutoff_active
            )
        )
        or 0
    )
    emerging_hot = (
        session.scalar(
            select(func.count(TopicCluster.id)).where(
                TopicCluster.last_seen_at >= cutoff_active,
                TopicCluster.state.in_(["emerging", "hot"]),
            )
        )
        or 0
    )
    last_job = session.scalar(
        select(JobRun)
        .where(
            JobRun.job_name == "phase_b_pipeline",
            JobRun.status == "succeeded",
        )
        .order_by(JobRun.finished_at.desc())
        .limit(1)
    )
    timezone = ZoneInfo(settings.app_timezone)
    last_updated = (
        ensure_utc(last_job.finished_at).astimezone(timezone)
        if last_job and last_job.finished_at
        else None
    )
    local_now = now.astimezone(timezone)
    return DashboardData(
        opportunities=opportunities,
        items_24h=items_24h,
        active_clusters=active_clusters,
        emerging_hot_clusters=emerging_hot,
        programs_indexed=0,
        last_updated=last_updated,
        next_refresh=_next_quarter_hour(local_now),
    )
