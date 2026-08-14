from __future__ import annotations

import asyncio
import hashlib
from datetime import UTC, datetime
from time import struct_time
from typing import Any

import feedparser
import httpx

from app.config import FeedDefinition
from app.schemas import SourceItemData
from app.sources.base import SourceAdapter
from app.utils import strip_html, utc_now


def _parsed_datetime(value: struct_time | None, fallback: datetime) -> datetime:
    if value is None:
        return fallback
    return datetime(*value[:6], tzinfo=UTC)


class RSSSourceAdapter(SourceAdapter):
    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        retries: int = 2,
    ) -> None:
        self.client = client
        self.retries = retries

    async def fetch(self, source: FeedDefinition) -> list[SourceItemData]:
        response: httpx.Response | None = None
        for attempt in range(self.retries + 1):
            try:
                response = await self.client.get(source.url)
                response.raise_for_status()
                break
            except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError):
                if attempt >= self.retries:
                    raise
                await asyncio.sleep(0.4 * (2**attempt))

        assert response is not None
        return self.parse(response.content, source)

    @staticmethod
    def parse(content: bytes, source: FeedDefinition) -> list[SourceItemData]:
        parsed = feedparser.parse(content)
        fetched_at = utc_now()
        items: list[SourceItemData] = []
        for entry in parsed.entries:
            title = str(entry.get("title", "")).strip()
            link = str(entry.get("link", "")).strip()
            if not title or not link:
                continue
            external_id = str(entry.get("id") or entry.get("guid") or link)
            if not external_id:
                external_id = hashlib.sha256(
                    f"{source.name}:{link}".encode()
                ).hexdigest()
            published_at = _parsed_datetime(
                entry.get("published_parsed") or entry.get("updated_parsed"),
                fetched_at,
            )
            tags = [
                str(tag.get("term", "")).strip()
                for tag in entry.get("tags", [])
                if tag.get("term")
            ]
            metadata: dict[str, Any] = {
                "feed_title": parsed.feed.get("title"),
                "region": source.region,
            }
            items.append(
                SourceItemData(
                    external_id=external_id[:512],
                    source_name=source.name,
                    source_type=source.source_type,
                    title=title,
                    summary=strip_html(
                        entry.get("summary") or entry.get("description")
                    ),
                    url=link,
                    published_at=published_at,
                    fetched_at=fetched_at,
                    author=entry.get("author"),
                    categories=tags,
                    raw_metadata=metadata,
                )
            )
        return items
