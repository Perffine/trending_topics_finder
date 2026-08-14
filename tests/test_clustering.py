from __future__ import annotations

from datetime import timedelta

from sqlalchemy import func, select

from app.models import SourceItem, TopicCluster
from app.services.clustering import cluster_new_items, keyword_overlap
from app.utils import canonicalize_url, normalize_title, utc_now


def model_item(index: int, source: str, title: str) -> SourceItem:
    now = utc_now()
    url = f"https://example.com/{index}"
    return SourceItem(
        external_id=str(index),
        source_name=source,
        source_type="local_news",
        title=title,
        normalized_title=normalize_title(title),
        summary=None,
        url=url,
        canonical_url=canonicalize_url(url),
        published_at=now - timedelta(minutes=index),
        fetched_at=now,
        categories=[],
        raw_metadata={},
    )


def test_keyword_overlap_uses_meaningful_terms() -> None:
    assert (
        keyword_overlap(
            "Toronto waterfront night market opens",
            "A new waterfront night market is opening in Toronto",
        )
        >= 0.8
    )


def test_cluster_assignment_groups_event_variants(database, settings) -> None:
    with database.session() as session:
        session.add_all(
            [
                model_item(
                    1, "Outlet A", "Toronto waterfront night market opens Friday"
                ),
                model_item(
                    2, "Outlet B", "New waterfront night market opens Friday in Toronto"
                ),
                model_item(
                    3, "Outlet C", "Ontario announces changes to fishing licences"
                ),
            ]
        )
        session.commit()
        result = cluster_new_items(session, settings)
        assert result["created"] == 2
        assert result["assigned"] == 1
        assert session.scalar(select(func.count(TopicCluster.id))) == 2
        clustered = session.scalar(
            select(TopicCluster).where(TopicCluster.item_count == 2)
        )
        assert clustered is not None
        assert clustered.source_count == 2
