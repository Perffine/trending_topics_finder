"""Create the observable signal pipeline tables.

Revision ID: 20260814_0001
Revises:
Create Date: 2026-08-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260814_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "topic_clusters",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("canonical_title", sa.Text(), nullable=False),
        sa.Column("short_description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("item_count", sa.Integer(), nullable=False),
        sa.Column("source_count", sa.Integer(), nullable=False),
        sa.Column("current_trend_score", sa.Float(), nullable=False),
        sa.Column("state", sa.String(length=30), nullable=False),
    )
    op.create_index(
        "ix_topic_clusters_last_seen_at", "topic_clusters", ["last_seen_at"]
    )
    op.create_index("ix_topic_clusters_state", "topic_clusters", ["state"])

    op.create_table(
        "source_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("external_id", sa.String(length=512), nullable=False),
        sa.Column("source_name", sa.String(length=200), nullable=False),
        sa.Column("source_type", sa.String(length=100), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("normalized_title", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("canonical_url", sa.Text(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("author", sa.String(length=300), nullable=True),
        sa.Column("categories", sa.JSON(), nullable=False),
        sa.Column("engagement_value", sa.Float(), nullable=True),
        sa.Column("engagement_type", sa.String(length=100), nullable=True),
        sa.Column("raw_metadata", sa.JSON(), nullable=False),
        sa.Column("cluster_id", sa.Integer(), nullable=True),
        sa.Column("duplicate_of_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["cluster_id"], ["topic_clusters.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["duplicate_of_id"], ["source_items.id"], ondelete="SET NULL"
        ),
        sa.UniqueConstraint("source_name", "external_id", name="uq_source_external_id"),
    )
    op.create_index("ix_source_items_canonical_url", "source_items", ["canonical_url"])
    op.create_index("ix_source_items_cluster_id", "source_items", ["cluster_id"])
    op.create_index(
        "ix_source_items_normalized_title", "source_items", ["normalized_title"]
    )
    op.create_index("ix_source_items_published_at", "source_items", ["published_at"])
    op.create_index("ix_source_items_source_name", "source_items", ["source_name"])
    op.create_index("ix_source_items_source_type", "source_items", ["source_type"])

    op.create_table(
        "trend_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("cluster_id", sa.Integer(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("mentions_1h", sa.Integer(), nullable=False),
        sa.Column("mentions_6h", sa.Integer(), nullable=False),
        sa.Column("mentions_previous_6h", sa.Integer(), nullable=False),
        sa.Column("mentions_24h", sa.Integer(), nullable=False),
        sa.Column("unique_sources_6h", sa.Integer(), nullable=False),
        sa.Column("unique_sources_24h", sa.Integer(), nullable=False),
        sa.Column("external_interest_signal", sa.Float(), nullable=True),
        sa.Column("velocity", sa.Float(), nullable=False),
        sa.Column("acceleration", sa.Float(), nullable=False),
        sa.Column("source_diversity", sa.Float(), nullable=False),
        sa.Column("external_interest", sa.Float(), nullable=False),
        sa.Column("novelty", sa.Float(), nullable=False),
        sa.Column("freshness", sa.Float(), nullable=False),
        sa.Column("saturation_penalty", sa.Float(), nullable=False),
        sa.Column("growth_percent_6h", sa.Float(), nullable=True),
        sa.Column("trend_score", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(
            ["cluster_id"], ["topic_clusters.id"], ondelete="CASCADE"
        ),
    )
    op.create_index(
        "ix_trend_snapshots_cluster_observed",
        "trend_snapshots",
        ["cluster_id", "observed_at"],
    )

    op.create_table(
        "job_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("job_name", sa.String(length=100), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("counts", sa.JSON(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
    )
    op.create_index("ix_job_runs_job_started", "job_runs", ["job_name", "started_at"])


def downgrade() -> None:
    op.drop_table("job_runs")
    op.drop_table("trend_snapshots")
    op.drop_table("source_items")
    op.drop_table("topic_clusters")
