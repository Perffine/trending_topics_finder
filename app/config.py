from __future__ import annotations

import json
from functools import lru_cache

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class FeedDefinition(BaseModel):
    name: str
    url: str
    source_type: str = "news"
    region: str = "GTA"


DEFAULT_FEEDS = [
    FeedDefinition(
        name="CBC Toronto",
        url="https://www.cbc.ca/cmlink/rss-canada-toronto",
        source_type="local_news",
    ),
    FeedDefinition(
        name="CityNews Toronto",
        url="https://toronto.citynews.ca/feed/",
        source_type="local_news",
    ),
    FeedDefinition(
        name="Global News Toronto",
        url="https://globalnews.ca/toronto/feed/",
        source_type="local_news",
    ),
    FeedDefinition(
        name="CBC Arts",
        url="https://www.cbc.ca/cmlink/rss-arts",
        source_type="culture",
        region="Canada",
    ),
    FeedDefinition(
        name="CBC Technology & Science",
        url="https://www.cbc.ca/cmlink/rss-technology",
        source_type="science_technology",
        region="Canada",
    ),
]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Promo Radar"
    app_base_url: str = "http://localhost:8000"
    app_timezone: str = "America/Toronto"
    environment: str = "development"
    database_url: str = (
        "postgresql+psycopg://promo_radar:promo_radar@localhost:5432/promo_radar"
    )
    job_token: str = ""
    rss_feeds_json: str = ""
    http_user_agent: str = (
        "PromoRadar/0.1 (library trend research; contact@example.org)"
    )
    ingest_lookback_hours: int = Field(default=48, ge=1, le=168)
    active_cluster_hours: int = Field(default=48, ge=6, le=336)
    tfidf_cluster_threshold: float = Field(default=0.32, ge=0, le=1)
    keyword_overlap_threshold: float = Field(default=0.20, ge=0, le=1)
    fuzzy_dedupe_threshold: float = Field(default=0.93, ge=0, le=1)
    min_topic_evidence: int = Field(default=2, ge=1, le=20)
    public_refresh_cooldown_seconds: int = Field(default=300, ge=0, le=3600)
    request_timeout_seconds: float = Field(default=15, ge=1, le=60)
    request_retries: int = Field(default=2, ge=0, le=5)

    @field_validator("database_url")
    @classmethod
    def normalize_postgres_scheme(cls, value: str) -> str:
        if value.startswith("postgres://"):
            return value.replace("postgres://", "postgresql+psycopg://", 1)
        if value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+psycopg://", 1)
        return value

    @property
    def feeds(self) -> list[FeedDefinition]:
        if not self.rss_feeds_json.strip():
            return DEFAULT_FEEDS
        raw = json.loads(self.rss_feeds_json)
        return [FeedDefinition.model_validate(item) for item in raw]


@lru_cache
def get_settings() -> Settings:
    return Settings()
