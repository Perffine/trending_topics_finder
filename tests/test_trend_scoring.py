from __future__ import annotations

from datetime import timedelta

from app.models import SourceItem
from app.services.trend_scoring import calculate_trend_metrics, clamp, growth_component
from app.utils import canonicalize_url, normalize_title, utc_now


def signal_item(index: int, hours_ago: float, source: str) -> SourceItem:
    now = utc_now()
    url = f"https://example.com/{index}"
    title = f"Topic report {index}"
    return SourceItem(
        id=index,
        external_id=str(index),
        source_name=source,
        source_type="news",
        title=title,
        normalized_title=normalize_title(title),
        url=url,
        canonical_url=canonicalize_url(url),
        published_at=now - timedelta(hours=hours_ago),
        fetched_at=now,
        categories=[],
        raw_metadata={},
    )


def test_score_helpers_are_bounded() -> None:
    assert clamp(-20) == 0
    assert clamp(150) == 100
    assert growth_component(20, 0) == 100
    assert growth_component(0, 20) == 0


def test_emerging_topic_outranks_static_popular_topic() -> None:
    now = utc_now()
    sources = ["A", "B", "C", "D"]
    emerging = [
        signal_item(index, 0.25 + index * 0.25, sources[index % 4])
        for index in range(1, 9)
    ]
    static = [
        signal_item(100 + index, 0.3 + (index * 23 / 59), sources[index % 4])
        for index in range(60)
    ]
    emerging_score = calculate_trend_metrics(
        emerging, observed_at=now, first_seen_at=now - timedelta(hours=3)
    )
    static_score = calculate_trend_metrics(
        static, observed_at=now, first_seen_at=now - timedelta(hours=30)
    )
    assert emerging_score.velocity > static_score.velocity
    assert emerging_score.trend_score > static_score.trend_score
