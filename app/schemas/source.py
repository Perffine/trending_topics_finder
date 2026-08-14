from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, HttpUrl


class SourceItemData(BaseModel):
    external_id: str
    source_name: str
    source_type: str
    title: str
    summary: str | None = None
    url: HttpUrl
    published_at: datetime
    fetched_at: datetime
    author: str | None = None
    categories: list[str] = Field(default_factory=list)
    engagement_value: float | None = None
    engagement_type: str | None = None
    raw_metadata: dict[str, Any] = Field(default_factory=dict)
