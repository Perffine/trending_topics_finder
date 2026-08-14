from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import JobRun
from app.services.dashboard import get_dashboard_data
from app.services.pipeline import run_phase_b_pipeline
from app.utils import ensure_utc, utc_now

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).parents[1] / "templates")


@router.get("/", response_class=HTMLResponse)
def dashboard(
    request: Request,
    notice: str | None = Query(default=None),
    session: Session = Depends(get_db),
) -> HTMLResponse:
    data = get_dashboard_data(session, request.app.state.settings)
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={"data": data, "notice": notice},
    )


@router.post("/refresh")
async def refresh_dashboard(
    request: Request,
    session: Session = Depends(get_db),
) -> RedirectResponse:
    settings = request.app.state.settings
    lock = request.app.state.pipeline_lock
    if lock.locked():
        return RedirectResponse("/?notice=Refresh+already+running", status_code=303)

    last_job = session.scalar(
        select(JobRun)
        .where(
            JobRun.job_name == "phase_b_pipeline",
            JobRun.status == "succeeded",
        )
        .order_by(JobRun.finished_at.desc())
        .limit(1)
    )
    if last_job and last_job.finished_at:
        elapsed = utc_now() - ensure_utc(last_job.finished_at)
        cooldown = timedelta(seconds=settings.public_refresh_cooldown_seconds)
        if elapsed < cooldown:
            remaining = max(int((cooldown - elapsed).total_seconds()), 1)
            return RedirectResponse(
                f"/?notice=Refresh+available+in+{remaining}+seconds",
                status_code=303,
            )

    async with lock:
        try:
            counts = await run_phase_b_pipeline(session, settings)
            inserted = counts["ingestion"]["inserted"]
            notice = f"Refresh complete: {inserted} new item(s)"
        except Exception:  # noqa: BLE001 - every pipeline failure preserves the old page.
            notice = "Refresh failed; the previous results are still available"
    return RedirectResponse(f"/?notice={notice.replace(' ', '+')}", status_code=303)


@router.get("/scoreboard", response_class=HTMLResponse)
def scoreboard(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="scoreboard.html",
        context={},
    )
