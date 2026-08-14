from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Any

from sqlalchemy.orm import Session

from app.config import Settings
from app.models import JobRun
from app.services.clustering import cluster_new_items
from app.services.ingestion import ingest_configured_feeds
from app.services.trend_scoring import compute_trend_snapshots
from app.utils import utc_now

logger = logging.getLogger(__name__)


async def run_phase_b_pipeline(
    session: Session,
    settings: Settings,
) -> dict[str, Any]:
    job = JobRun(job_name="phase_b_pipeline", started_at=utc_now(), status="running")
    session.add(job)
    session.commit()
    logger.info("job_started", extra={"job_name": job.job_name, "job_id": job.id})
    try:
        ingestion = await ingest_configured_feeds(session, settings)
        clustering = cluster_new_items(session, settings)
        trends = compute_trend_snapshots(session, settings)
        counts: dict[str, Any] = {
            "ingestion": asdict(ingestion),
            "clustering": clustering,
            "trends": trends,
        }
        job.status = "succeeded"
        job.counts = counts
        job.finished_at = utc_now()
        session.commit()
        logger.info(
            "job_completed",
            extra={"job_name": job.job_name, "job_id": job.id, "counts": counts},
        )
        return counts
    except Exception as exc:
        session.rollback()
        failed_job = session.get(JobRun, job.id)
        if failed_job:
            failed_job.status = "failed"
            failed_job.error = str(exc)
            failed_job.finished_at = utc_now()
            session.commit()
        logger.exception(
            "job_failed",
            extra={"job_name": job.job_name, "job_id": job.id},
        )
        raise
