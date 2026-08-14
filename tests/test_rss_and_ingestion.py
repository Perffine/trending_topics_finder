from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select

from app.config import FeedDefinition
from app.models import SourceItem
from app.schemas import SourceItemData
from app.services.ingestion import ingest_items
from app.sources.rss import RSSSourceAdapter

SAMPLE_RSS = b"""<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0"><channel><title>GTA Desk</title>
<item><guid>story-1</guid><title>Night market opens on waterfront</title>
<link>https://example.com/night-market?utm_source=rss</link>
<description><![CDATA[<p>A new evening market opens Friday.</p>]]></description>
<pubDate>Fri, 14 Aug 2026 12:00:00 GMT</pubDate>
<category>Local</category></item></channel></rss>"""


def source_item(external_id: str, source: str, title: str, url: str) -> SourceItemData:
    now = datetime(2026, 8, 14, 12, tzinfo=UTC)
    return SourceItemData(
        external_id=external_id,
        source_name=source,
        source_type="local_news",
        title=title,
        url=url,
        published_at=now,
        fetched_at=now,
    )


def test_rss_adapter_normalizes_a_feed_entry() -> None:
    items = RSSSourceAdapter.parse(
        SAMPLE_RSS,
        FeedDefinition(name="Test Feed", url="https://example.com/rss"),
    )
    assert len(items) == 1
    assert items[0].external_id == "story-1"
    assert items[0].summary == "A new evening market opens Friday."
    assert items[0].categories == ["Local"]
    assert items[0].published_at == datetime(2026, 8, 14, 12, tzinfo=UTC)


def test_ingestion_handles_exact_and_syndicated_duplicates(database, settings) -> None:
    with database.session() as session:
        first = ingest_items(
            session,
            [
                source_item(
                    "1",
                    "Outlet A",
                    "Toronto opens a new waterfront night market this weekend",
                    "https://example.com/a",
                ),
                source_item(
                    "2",
                    "Outlet B",
                    "Toronto opens new waterfront night market this weekend",
                    "https://other.example.com/b",
                ),
            ],
            settings,
        )
        second = ingest_items(
            session,
            [
                source_item(
                    "1",
                    "Outlet A",
                    "Toronto opens a new waterfront night market this weekend",
                    "https://example.com/a?utm_source=again",
                )
            ],
            settings,
        )
        assert first.inserted == 2
        assert first.fuzzy_duplicates == 1
        assert second.exact_duplicates == 1
        assert session.scalar(select(func.count(SourceItem.id))) == 2
        duplicate = session.scalar(
            select(SourceItem).where(SourceItem.source_name == "Outlet B")
        )
        assert duplicate is not None
        assert duplicate.duplicate_of_id is not None
