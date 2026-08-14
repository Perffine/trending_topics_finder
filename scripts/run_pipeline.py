from __future__ import annotations

import argparse
import asyncio

from app.config import Settings, get_settings
from app.db import Database
from app.logging_config import configure_logging
from app.services.pipeline import run_phase_b_pipeline


async def main(database_url: str | None = None) -> None:
    configure_logging()
    settings = Settings(database_url=database_url) if database_url else get_settings()
    database = Database(settings.database_url)
    try:
        with database.session() as session:
            counts = await run_phase_b_pipeline(session, settings)
            print(counts)
    finally:
        database.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the Phase B signal pipeline.")
    parser.add_argument("--database-url", help="Override DATABASE_URL for this run.")
    arguments = parser.parse_args()
    asyncio.run(main(arguments.database_url))
