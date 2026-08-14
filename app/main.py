from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.config import Settings, get_settings
from app.db import Database
from app.logging_config import configure_logging
from app.routes import dashboard_router, jobs_router


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.database = Database(resolved_settings.database_url)
        app.state.settings = resolved_settings
        app.state.pipeline_lock = asyncio.Lock()
        yield
        app.state.database.dispose()

    configure_logging()
    app = FastAPI(
        title=resolved_settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
    )
    app.mount(
        "/static",
        StaticFiles(directory=Path(__file__).parent / "static"),
        name="static",
    )
    app.include_router(dashboard_router)
    app.include_router(jobs_router)

    @app.get("/healthz")
    def healthz(request: Request) -> JSONResponse:
        try:
            with request.app.state.database.session() as session:
                session.execute(text("SELECT 1"))
            return JSONResponse({"status": "ok", "database": "connected"})
        except SQLAlchemyError:
            return JSONResponse(
                {"status": "unhealthy", "database": "unavailable"},
                status_code=503,
            )

    return app


app = create_app()
