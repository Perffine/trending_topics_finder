from app.services.dedupe import is_probable_duplicate, token_jaccard
from app.utils import canonicalize_url, normalize_title


def test_normalize_title_removes_punctuation_spacing_and_outlet_suffix() -> None:
    assert (
        normalize_title("  Waterfront Night-Market Opens! | CBC  ")
        == "waterfront night market opens"
    )


def test_canonicalize_url_removes_tracking_but_preserves_content_query() -> None:
    assert (
        canonicalize_url(
            "HTTPS://Example.com/story/?utm_source=rss&id=42&fbclid=abc#top"
        )
        == "https://example.com/story?id=42"
    )


def test_fuzzy_dedupe_is_conservative() -> None:
    assert is_probable_duplicate(
        "Toronto opens a new waterfront night market this weekend",
        "Toronto opens new waterfront night market this weekend",
        threshold=0.90,
    )
    assert not is_probable_duplicate(
        "Toronto opens a new waterfront night market",
        "Toronto approves waterfront transit construction",
        threshold=0.90,
    )
    assert token_jaccard("alpha beta gamma", "alpha beta delta") == 0.5
