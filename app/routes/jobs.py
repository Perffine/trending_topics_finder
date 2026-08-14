from __future__ import annotations

import hmac

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.services.clustering import cluster_new_items
from app.services.ingestion import ingest_configured_feeds
from app.services.pipeline import run_phase_b_pipeline
from app.services.trend_scoring import compute_trend_snapshots

router = APIRouter(prefix="/internal/jobs", tags=["internal-jobs"])


def require_job_token(
    request: Request,
    authorization: str | None = Header(default=None),
) -> None:
    configured = request.app.state.settings.job_token
    if not configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Internal jobs are disabled until JOB_TOKEN is configured.",
        )
    supplied = authorization.removeprefix("Bearer ") if authorization else ""
    if not hmac.compare_digest(supplied, configured):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid job credentials.",
        )


@router.post("/pipeline", dependencies=[Depends(require_job_token)])
async def pipeline(request: Request, session: Session = Depends(get_db)) -> dict:
    lock = request.app.state.pipeline_lock
    if lock.locked():
        raise HTTPException(status_code=409, detail="Pipeline is already running.")
    async with lock:
        return await run_phase_b_pipeline(session, request.app.state.settings)


@router.post("/ingest", dependencies=[Depends(require_job_token)])
async def ingest(request: Request, session: Session = Depends(get_db)) -> dict:
    result = await ingest_configured_feeds(session, request.app.state.settings)
    return {
        "fetched": result.fetched,
        "inserted": result.inserted,
        "exact_duplicates": result.exact_duplicates,
        "fuzzy_duplicates": result.fuzzy_duplicates,
        "source_errors": result.source_errors,
    }


@router.post("/cluster", dependencies=[Depends(require_job_token)])
def cluster(request: Request, session: Session = Depends(get_db)) -> dict:
    return cluster_new_items(session, request.app.state.settings)


@router.post("/trends", dependencies=[Depends(require_job_token)])
def trends(request: Request, session: Session = Depends(get_db)) -> dict:
    return compute_trend_snapshots(session, request.app.state.settings)
