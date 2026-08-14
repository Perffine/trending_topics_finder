from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

JSON_TYPE = JSON().with_variant(JSONB, "postgresql")


class SourceItem(Base):
    __tablename__ = "source_items"
    __table_args__ = (
        UniqueConstraint("source_name", "external_id", name="uq_source_external_id"),
        Index("ix_source_items_published_at", "published_at"),
        Index("ix_source_items_cluster_id", "cluster_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    external_id: Mapped[str] = mapped_column(String(512))
    source_name: Mapped[str] = mapped_column(String(200), index=True)
    source_type: Mapped[str] = mapped_column(String(100), index=True)
    title: Mapped[str] = mapped_column(Text)
    normalized_title: Mapped[str] = mapped_column(Text, index=True)
    summary: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text)
    canonical_url: Mapped[str] = mapped_column(Text, index=True)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    author: Mapped[str | None] = mapped_column(String(300))
    categories: Mapped[list[str]] = mapped_column(JSON_TYPE, default=list)
    engagement_value: Mapped[float | None] = mapped_column(Float)
    engagement_type: Mapped[str | None] = mapped_column(String(100))
    raw_metadata: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, default=dict)
    cluster_id: Mapped[int | None] = mapped_column(
        ForeignKey("topic_clusters.id", ondelete="SET NULL")
    )
    duplicate_of_id: Mapped[int | None] = mapped_column(
        ForeignKey("source_items.id", ondelete="SET NULL")
    )

    cluster: Mapped[TopicCluster | None] = relationship(back_populates="items")
    duplicate_of: Mapped[SourceItem | None] = relationship(remote_side=[id])


class TopicCluster(Base):
    __tablename__ = "topic_clusters"
    __table_args__ = (Index("ix_topic_clusters_last_seen_at", "last_seen_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    canonical_title: Mapped[str] = mapped_column(Text)
    short_description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    item_count: Mapped[int] = mapped_column(Integer, default=0)
    source_count: Mapped[int] = mapped_column(Integer, default=0)
    current_trend_score: Mapped[float] = mapped_column(Float, default=0)
    state: Mapped[str] = mapped_column(String(30), default="emerging", index=True)

    items: Mapped[list[SourceItem]] = relationship(back_populates="cluster")
    snapshots: Mapped[list[TrendSnapshot]] = relationship(
        back_populates="cluster",
        cascade="all, delete-orphan",
    )


class TrendSnapshot(Base):
    __tablename__ = "trend_snapshots"
    __table_args__ = (
        Index("ix_trend_snapshots_cluster_observed", "cluster_id", "observed_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cluster_id: Mapped[int] = mapped_column(
        ForeignKey("topic_clusters.id", ondelete="CASCADE")
    )
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    mentions_1h: Mapped[int] = mapped_column(Integer, default=0)
    mentions_6h: Mapped[int] = mapped_column(Integer, default=0)
    mentions_previous_6h: Mapped[int] = mapped_column(Integer, default=0)
    mentions_24h: Mapped[int] = mapped_column(Integer, default=0)
    unique_sources_6h: Mapped[int] = mapped_column(Integer, default=0)
    unique_sources_24h: Mapped[int] = mapped_column(Integer, default=0)
    external_interest_signal: Mapped[float | None] = mapped_column(Float)
    velocity: Mapped[float] = mapped_column(Float)
    acceleration: Mapped[float] = mapped_column(Float)
    source_diversity: Mapped[float] = mapped_column(Float)
    external_interest: Mapped[float] = mapped_column(Float)
    novelty: Mapped[float] = mapped_column(Float)
    freshness: Mapped[float] = mapped_column(Float)
    saturation_penalty: Mapped[float] = mapped_column(Float)
    growth_percent_6h: Mapped[float | None] = mapped_column(Float)
    trend_score: Mapped[float] = mapped_column(Float)

    cluster: Mapped[TopicCluster] = relationship(back_populates="snapshots")


class JobRun(Base):
    __tablename__ = "job_runs"
    __table_args__ = (Index("ix_job_runs_job_started", "job_name", "started_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_name: Mapped[str] = mapped_column(String(100))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(30))
    counts: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, default=dict)
    error: Mapped[str | None] = mapped_column(Text)
