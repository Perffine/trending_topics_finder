from __future__ import annotations

import logging
import ssl
from dataclasses import dataclass, field
from datetime import timedelta

import httpx
import truststore
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import SourceItem
from app.schemas import SourceItemData
from app.services.dedupe import is_probable_duplicate
from app.sources import RSSSourceAdapter
from app.utils import canonicalize_url, ensure_utc, normalize_title, utc_now

logger = logging.getLogger(__name__)


@dataclass
class IngestionResult:
    fetched: int = 0
    inserted: int = 0
    exact_duplicates: int = 0
    fuzzy_duplicates: int = 0
    source_errors: dict[str, str] = field(default_factory=dict)


def ingest_items(
    session: Session,
    items: list[SourceItemData],
    settings: Settings,
) -> IngestionResult:
    result = IngestionResult(fetched=len(items))
    cutoff = utc_now() - timedelta(hours=settings.ingest_lookback_hours)
    recent_items = list(
        session.scalars(
            select(SourceItem)
            .where(SourceItem.published_at >= cutoff)
            .order_by(SourceItem.published_at.desc())
            .limit(1500)
        )
    )

    for item in sorted(items, key=lambda value: value.published_at):
        canonical_url = canonicalize_url(str(item.url))
        exact = session.scalar(
            select(SourceItem.id).where(
                or_(
                    (SourceItem.source_name == item.source_name)
                    & (SourceItem.external_id == item.external_id),
                    SourceItem.canonical_url == canonical_url,
                )
            )
        )
        if exact is not None:
            result.exact_duplicates += 1
            continue

        duplicate = next(
            (
                candidate
                for candidate in recent_items
                if is_probable_duplicate(
                    item.title,
                    candidate.title,
                    settings.fuzzy_dedupe_threshold,
                )
            ),
            None,
        )
        model = SourceItem(
            external_id=item.external_id,
            source_name=item.source_name,
            source_type=item.source_type,
            title=item.title,
            normalized_title=normalize_title(item.title),
            summary=item.summary,
            url=str(item.url),
            canonical_url=canonical_url,
            published_at=ensure_utc(item.published_at),
            fetched_at=ensure_utc(item.fetched_at),
            author=item.author,
            categories=item.categories,
            engagement_value=item.engagement_value,
            engagement_type=item.engagement_type,
            raw_metadata=item.raw_metadata,
            duplicate_of_id=duplicate.id if duplicate else None,
            cluster_id=duplicate.cluster_id if duplicate else None,
        )
        session.add(model)
        session.flush()
        recent_items.append(model)
        result.inserted += 1
        if duplicate:
            result.fuzzy_duplicates += 1

    session.commit()
    return result


async def ingest_configured_feeds(
    session: Session,
    settings: Settings,
) -> IngestionResult:
    headers = {"User-Agent": settings.http_user_agent}
    aggregate = IngestionResult()
    ssl_context = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    async with httpx.AsyncClient(
        headers=headers,
        timeout=settings.request_timeout_seconds,
        follow_redirects=True,
        verify=ssl_context,
    ) as client:
        adapter = RSSSourceAdapter(client, retries=settings.request_retries)
        for feed in settings.feeds:
            try:
                items = await adapter.fetch(feed)
                partial = ingest_items(session, items, settings)
                aggregate.fetched += partial.fetched
                aggregate.inserted += partial.inserted
                aggregate.exact_duplicates += partial.exact_duplicates
                aggregate.fuzzy_duplicates += partial.fuzzy_duplicates
                logger.info(
                    "source_fetch_complete",
                    extra={"source": feed.name, "item_count": len(items)},
                )
            except Exception as exc:
                session.rollback()
                aggregate.source_errors[feed.name] = str(exc)
                logger.exception("source_fetch_failed", extra={"source": feed.name})
    return aggregate
