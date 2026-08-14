from __future__ import annotations

import math
import re
from collections import Counter
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import Settings
from app.models import SourceItem, TopicCluster
from app.utils import ensure_utc, normalize_title, utc_now

STOP_WORDS = {
    "about",
    "after",
    "again",
    "against",
    "also",
    "among",
    "because",
    "been",
    "before",
    "being",
    "between",
    "both",
    "could",
    "from",
    "have",
    "into",
    "just",
    "more",
    "most",
    "news",
    "over",
    "says",
    "than",
    "that",
    "their",
    "there",
    "these",
    "they",
    "this",
    "through",
    "under",
    "very",
    "what",
    "when",
    "where",
    "which",
    "while",
    "will",
    "with",
    "would",
    "your",
}


def significant_tokens(value: str) -> list[str]:
    return [
        token
        for token in re.findall(r"[a-z0-9]+", normalize_title(value))
        if len(token) >= 3 and token not in STOP_WORDS
    ]


def keyword_overlap(left: str, right: str) -> float:
    left_tokens = set(significant_tokens(left))
    right_tokens = set(significant_tokens(right))
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / min(len(left_tokens), len(right_tokens))


def tfidf_similarities(query: str, documents: list[str]) -> list[float]:
    tokenized = [
        significant_tokens(query),
        *(significant_tokens(doc) for doc in documents),
    ]
    document_count = len(tokenized)
    document_frequency: Counter[str] = Counter()
    for tokens in tokenized:
        document_frequency.update(set(tokens))

    def vector(tokens: list[str]) -> dict[str, float]:
        counts = Counter(tokens)
        total = max(sum(counts.values()), 1)
        return {
            term: (count / total)
            * (math.log((document_count + 1) / (document_frequency[term] + 1)) + 1)
            for term, count in counts.items()
        }

    vectors = [vector(tokens) for tokens in tokenized]
    query_vector = vectors[0]
    query_norm = math.sqrt(sum(weight * weight for weight in query_vector.values()))
    similarities: list[float] = []
    for candidate in vectors[1:]:
        candidate_norm = math.sqrt(
            sum(weight * weight for weight in candidate.values())
        )
        if not query_norm or not candidate_norm:
            similarities.append(0.0)
            continue
        dot_product = sum(
            weight * candidate.get(term, 0.0) for term, weight in query_vector.items()
        )
        similarities.append(dot_product / (query_norm * candidate_norm))
    return similarities


def cluster_document(cluster: TopicCluster) -> str:
    recent_items = sorted(
        (item for item in cluster.items if item.duplicate_of_id is None),
        key=lambda item: ensure_utc(item.published_at),
        reverse=True,
    )[:8]
    parts = [cluster.canonical_title]
    for item in recent_items:
        parts.append(item.title)
        if item.summary:
            parts.append(item.summary[:300])
    return " ".join(parts)


def _recalculate_cluster(cluster: TopicCluster) -> None:
    canonical_items = [item for item in cluster.items if item.duplicate_of_id is None]
    if not canonical_items:
        return
    cluster.item_count = len(canonical_items)
    cluster.source_count = len({item.source_name for item in canonical_items})
    cluster.first_seen_at = min(
        ensure_utc(item.published_at) for item in canonical_items
    )
    cluster.last_seen_at = max(
        ensure_utc(item.published_at) for item in canonical_items
    )


def cluster_new_items(session: Session, settings: Settings) -> dict[str, int]:
    now = utc_now()
    cutoff = now - timedelta(hours=settings.active_cluster_hours)
    clusters = list(
        session.scalars(
            select(TopicCluster)
            .options(selectinload(TopicCluster.items))
            .where(TopicCluster.last_seen_at >= cutoff)
            .order_by(TopicCluster.created_at)
        )
    )
    unclustered = list(
        session.scalars(
            select(SourceItem)
            .where(
                SourceItem.cluster_id.is_(None),
                SourceItem.duplicate_of_id.is_(None),
                SourceItem.published_at >= cutoff,
            )
            .order_by(SourceItem.published_at)
        )
    )
    created = 0
    assigned = 0

    for item in unclustered:
        best_cluster: TopicCluster | None = None
        best_similarity = 0.0
        if clusters:
            documents = [cluster_document(cluster) for cluster in clusters]
            similarities = tfidf_similarities(
                f"{item.title} {item.summary or ''}",
                documents,
            )
            for cluster, similarity, document in zip(
                clusters, similarities, documents, strict=True
            ):
                overlap = keyword_overlap(item.title, document)
                if (
                    similarity >= settings.tfidf_cluster_threshold
                    and overlap >= settings.keyword_overlap_threshold
                    and similarity > best_similarity
                ):
                    best_cluster = cluster
                    best_similarity = similarity

        if best_cluster is None:
            published_at = ensure_utc(item.published_at)
            best_cluster = TopicCluster(
                canonical_title=item.title,
                short_description=item.summary,
                created_at=now,
                first_seen_at=published_at,
                last_seen_at=published_at,
                item_count=0,
                source_count=0,
                state="emerging",
            )
            session.add(best_cluster)
            session.flush()
            clusters.append(best_cluster)
            created += 1
        else:
            assigned += 1

        item.cluster = best_cluster
        if item not in best_cluster.items:
            best_cluster.items.append(item)
        _recalculate_cluster(best_cluster)

    session.flush()

    duplicates = list(
        session.scalars(
            select(SourceItem)
            .options(selectinload(SourceItem.duplicate_of))
            .where(
                SourceItem.cluster_id.is_(None),
                SourceItem.duplicate_of_id.is_not(None),
                SourceItem.published_at >= cutoff,
            )
        )
    )
    duplicate_assignments = 0
    for item in duplicates:
        if item.duplicate_of and item.duplicate_of.cluster_id:
            item.cluster_id = item.duplicate_of.cluster_id
            duplicate_assignments += 1

    for cluster in clusters:
        _recalculate_cluster(cluster)
    session.commit()
    return {
        "created": created,
        "assigned": assigned,
        "duplicate_assignments": duplicate_assignments,
    }
