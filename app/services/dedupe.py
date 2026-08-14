from __future__ import annotations

from difflib import SequenceMatcher

from app.utils import normalize_title


def token_jaccard(left: str, right: str) -> float:
    left_tokens = set(normalize_title(left).split())
    right_tokens = set(normalize_title(right).split())
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def title_similarity(left: str, right: str) -> float:
    return SequenceMatcher(None, normalize_title(left), normalize_title(right)).ratio()


def is_probable_duplicate(left: str, right: str, threshold: float = 0.93) -> bool:
    normalized_left = normalize_title(left)
    normalized_right = normalize_title(right)
    if normalized_left == normalized_right:
        return True
    return (
        title_similarity(normalized_left, normalized_right) >= threshold
        and token_jaccard(normalized_left, normalized_right) >= 0.72
    )
