from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import Settings
from app.models import SourceItem, TopicCluster, TrendSnapshot
from app.utils import ensure_utc, utc_now


def clamp(value: float, minimum: float = 0.0, maximum: float = 100.0) -> float:
    return max(minimum, min(maximum, value))


def growth_component(current: float, previous: float, scale: float = 25.0) -> float:
    ratio = (current + 1.0) / (previous + 1.0)
    return clamp(50.0 + scale * math.log2(ratio))


def age_component(age_hours: float, decay_per_hour: float) -> float:
    return clamp(100.0 - max(age_hours, 0.0) * decay_per_hour)


@dataclass(frozen=True)
class TrendMetrics:
    mentions_1h: int
    mentions_6h: int
    mentions_previous_6h: int
    mentions_24h: int
    unique_sources_6h: int
    unique_sources_24h: int
    velocity: float
    acceleration: float
    source_diversity: float
    external_interest: float
    novelty: float
    freshness: float
    saturation_penalty: float
    growth_percent_6h: float | None
    trend_score: float


def calculate_trend_metrics(
    items: list[SourceItem],
    *,
    observed_at: datetime,
    first_seen_at: datetime,
) -> TrendMetrics:
    observed_at = ensure_utc(observed_at)
    canonical_items = [item for item in items if item.duplicate_of_id is None]

    def since(hours: int) -> list[SourceItem]:
        cutoff = observed_at - timedelta(hours=hours)
        return [
            item for item in canonical_items if ensure_utc(item.published_at) >= cutoff
        ]

    items_1h = since(1)
    items_6h = since(6)
    items_24h = since(24)
    previous_6h = [
        item
        for item in canonical_items
        if observed_at - timedelta(hours=12)
        <= ensure_utc(item.published_at)
        < observed_at - timedelta(hours=6)
    ]
    previous_5h_count = max(len(items_6h) - len(items_1h), 0)

    velocity = growth_component(len(items_6h), len(previous_6h))
    acceleration = growth_component(len(items_1h), previous_5h_count / 5.0, 20.0)
    unique_sources_6h = len({item.source_name for item in items_6h})
    unique_sources_24h = len({item.source_name for item in items_24h})
    source_diversity = clamp(unique_sources_6h * 22.0)

    signals = [
        item.engagement_value for item in items_24h if item.engagement_value is not None
    ]
    external_interest = clamp(max(signals)) if signals else 0.0
    age_hours = max(
        (observed_at - ensure_utc(first_seen_at)).total_seconds() / 3600.0,
        0.0,
    )
    novelty = age_component(age_hours, 1.5)
    freshness = age_component(age_hours, 2.0)
    saturation_penalty = clamp(max(len(items_24h) - 30, 0) * 0.5, 0, 20)
    if age_hours > 24 and velocity < 40:
        saturation_penalty = clamp(saturation_penalty + 10, 0, 25)

    trend_score = clamp(
        0.30 * velocity
        + 0.15 * acceleration
        + 0.20 * source_diversity
        + 0.15 * external_interest
        + 0.10 * novelty
        + 0.10 * freshness
        - saturation_penalty
    )
    growth_percent = None
    if previous_6h:
        growth_percent = ((len(items_6h) - len(previous_6h)) / len(previous_6h)) * 100.0

    return TrendMetrics(
        mentions_1h=len(items_1h),
        mentions_6h=len(items_6h),
        mentions_previous_6h=len(previous_6h),
        mentions_24h=len(items_24h),
        unique_sources_6h=unique_sources_6h,
        unique_sources_24h=unique_sources_24h,
        velocity=round(velocity, 2),
        acceleration=round(acceleration, 2),
        source_diversity=round(source_diversity, 2),
        external_interest=round(external_interest, 2),
        novelty=round(novelty, 2),
        freshness=round(freshness, 2),
        saturation_penalty=round(saturation_penalty, 2),
        growth_percent_6h=(
            round(growth_percent, 1) if growth_percent is not None else None
        ),
        trend_score=round(trend_score, 2),
    )


def topic_state(metrics: TrendMetrics, age_hours: float) -> str:
    if age_hours >= 48 or metrics.mentions_24h == 0:
        return "stale"
    if metrics.trend_score >= 70 and metrics.velocity >= 50:
        return "hot"
    if metrics.velocity < 40:
        return "cooling"
    return "emerging"


def compute_trend_snapshots(
    session: Session,
    settings: Settings,
    *,
    observed_at: datetime | None = None,
) -> dict[str, int]:
    observed_at = ensure_utc(observed_at or utc_now())
    cutoff = observed_at - timedelta(hours=settings.active_cluster_hours)
    clusters = list(
        session.scalars(
            select(TopicCluster)
            .options(selectinload(TopicCluster.items))
            .where(TopicCluster.last_seen_at >= cutoff)
        )
    )
    scored = 0
    for cluster in clusters:
        metrics = calculate_trend_metrics(
            cluster.items,
            observed_at=observed_at,
            first_seen_at=cluster.first_seen_at,
        )
        age_hours = (
            observed_at - ensure_utc(cluster.first_seen_at)
        ).total_seconds() / 3600.0
        cluster.current_trend_score = metrics.trend_score
        cluster.state = topic_state(metrics, age_hours)
        session.add(
            TrendSnapshot(
                cluster=cluster,
                observed_at=observed_at,
                mentions_1h=metrics.mentions_1h,
                mentions_6h=metrics.mentions_6h,
                mentions_previous_6h=metrics.mentions_previous_6h,
                mentions_24h=metrics.mentions_24h,
                unique_sources_6h=metrics.unique_sources_6h,
                unique_sources_24h=metrics.unique_sources_24h,
                external_interest_signal=(
                    metrics.external_interest if metrics.external_interest else None
                ),
                velocity=metrics.velocity,
                acceleration=metrics.acceleration,
                source_diversity=metrics.source_diversity,
                external_interest=metrics.external_interest,
                novelty=metrics.novelty,
                freshness=metrics.freshness,
                saturation_penalty=metrics.saturation_penalty,
                growth_percent_6h=metrics.growth_percent_6h,
                trend_score=metrics.trend_score,
            )
        )
        scored += 1
    session.commit()
    return {"scored": scored}
