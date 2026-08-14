from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.db import Base, Database
from app.main import create_app


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        job_token="test-job-token",
        min_topic_evidence=1,
        public_refresh_cooldown_seconds=0,
        tfidf_cluster_threshold=0.20,
        keyword_overlap_threshold=0.20,
    )


@pytest.fixture
def database(settings: Settings) -> Iterator[Database]:
    database = Database(settings.database_url)
    Base.metadata.create_all(database.engine)
    yield database
    database.dispose()


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    app = create_app(settings)
    with TestClient(app) as test_client:
        Base.metadata.create_all(app.state.database.engine)
        yield test_client
