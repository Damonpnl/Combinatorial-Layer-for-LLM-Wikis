"""Deterministic pre-synthesis pair scoring for combination drafts."""

from __future__ import annotations

import re
from typing import Any, TypedDict


PAIR_SCORER_VERSION = "pair-scorer-v1"


class PairScore(TypedDict):
    overall_score: float
    domain_distance: float
    abstraction_gap: float
    mechanism_difference: float
    certainty_mismatch: float
    overlap_penalty: float
    reasons: list[str]


ABSTRACTION_LEVELS = {
    "entity": 0.2,
    "protocol": 0.3,
    "tool": 0.35,
    "concept": 0.55,
    "comparison": 0.7,
    "synthesis": 0.85,
    "output": 0.75,
}

STATUS_CERTAINTY = {
    "final": 1.0,
    "review": 0.65,
    "draft": 0.35,
}

LOW_SIGNAL_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "in",
    "into",
    "is",
    "it",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
}


def clamp(value: float) -> float:
    return round(max(0.0, min(1.0, value)), 3)


def normalized_set(values: list[str] | None) -> set[str]:
    return {str(value).strip().lower() for value in values or [] if str(value).strip()}


def domain_tags(page: dict[str, Any]) -> set[str]:
    tags = normalized_set(page.get("tags"))
    tags.discard("cross-niche")
    if not tags and page.get("path"):
        tags.add(str(page["path"]).split("/", 2)[1] if str(page["path"]).startswith("wiki/") else str(page["path"]).split("/", 1)[0])
    return tags


def jaccard_similarity(left: set[str], right: set[str]) -> float:
    if not left and not right:
        return 0.0
    union = left | right
    if not union:
        return 0.0
    return len(left & right) / len(union)


def jaccard_distance(left: set[str], right: set[str]) -> float:
    return 1.0 - jaccard_similarity(left, right)


def token_set(text: str) -> set[str]:
    tokens = {
        token
        for token in re.findall(r"[a-z0-9][a-z0-9-]{2,}", text.lower())
        if token not in LOW_SIGNAL_WORDS
    }
    return tokens


def mechanism_tokens(page: dict[str, Any]) -> set[str]:
    fields = [
        "mechanisms",
        "core_mechanism",
        "control_variable",
        "primary_bottleneck",
        "dominant_failure_mode",
        "highest_leverage_use_case",
        "incentives",
        "actors",
        "risks",
        "cross_niche_implications",
    ]
    parts: list[str] = []
    for field in fields:
        value = page.get(field, [])
        if isinstance(value, list):
            parts.extend(str(item) for item in value)
        elif value:
            parts.append(str(value))
    if not parts:
        parts = [str(page.get("title", "")), str(page.get("summary", ""))]
    return token_set(" ".join(parts))


def text_tokens(page: dict[str, Any]) -> set[str]:
    text = " ".join(
        [
            str(page.get("title", "")),
            str(page.get("summary", "")),
            " ".join(str(tag) for tag in page.get("tags", [])),
        ]
    )
    return token_set(text)


def abstraction_level(page: dict[str, Any]) -> float:
    return ABSTRACTION_LEVELS.get(str(page.get("type", "")).lower(), 0.5)


def certainty_level(page: dict[str, Any]) -> float:
    return STATUS_CERTAINTY.get(str(page.get("status", "")).lower(), 0.55)


def shared_link_similarity(parent_a: dict[str, Any], parent_b: dict[str, Any]) -> float:
    links_a = normalized_set(parent_a.get("linked_concepts"))
    links_b = normalized_set(parent_b.get("linked_concepts"))
    return jaccard_similarity(links_a, links_b)


def score_pair(parent_a: dict[str, Any], parent_b: dict[str, Any]) -> PairScore:
    """Score whether two canonical pages are a useful speculative pair.

    Higher scores mean more useful tension: enough distance and mechanism
    difference to produce novelty, with overlap penalized to avoid rewording.
    """

    tags_a = domain_tags(parent_a)
    tags_b = domain_tags(parent_b)
    domain_distance = clamp(jaccard_distance(tags_a, tags_b))

    abstraction_gap = clamp(abs(abstraction_level(parent_a) - abstraction_level(parent_b)))

    mechanisms_a = mechanism_tokens(parent_a)
    mechanisms_b = mechanism_tokens(parent_b)
    mechanism_similarity = jaccard_similarity(mechanisms_a, mechanisms_b)
    mechanism_difference = clamp(1.0 - mechanism_similarity)

    certainty_mismatch = clamp(abs(certainty_level(parent_a) - certainty_level(parent_b)))

    tag_similarity = jaccard_similarity(tags_a, tags_b)
    link_similarity = shared_link_similarity(parent_a, parent_b)
    text_similarity = jaccard_similarity(text_tokens(parent_a), text_tokens(parent_b))
    overlap_penalty = clamp(max(tag_similarity, link_similarity, text_similarity, mechanism_similarity))

    novelty_signal = (
        0.3 * domain_distance
        + 0.15 * abstraction_gap
        + 0.25 * mechanism_difference
        + 0.1 * certainty_mismatch
        + 0.2 * (1.0 - overlap_penalty)
    )
    overall_score = clamp(novelty_signal)

    reasons: list[str] = []
    if domain_distance >= 0.75:
        reasons.append("Parents sit in meaningfully different domains.")
    elif domain_distance <= 0.25:
        reasons.append("Parents share a close domain, reducing novelty.")
    else:
        reasons.append("Parents have some domain separation with a shared bridge.")

    if mechanism_difference >= 0.75:
        reasons.append("Extracted mechanisms and actors differ enough to create synthesis tension.")
    elif mechanism_difference <= 0.35:
        reasons.append("Extracted mechanisms overlap heavily, so the pair may restate known material.")

    if abstraction_gap >= 0.35:
        reasons.append("The pair crosses abstraction levels.")
    else:
        reasons.append("The pair sits at a similar abstraction level.")

    if certainty_mismatch >= 0.3:
        reasons.append("Parent status levels differ, so claims need careful handling.")

    if overlap_penalty >= 0.65:
        reasons.append("High overlap penalty: tags, links, text, or mechanisms are very similar.")
    elif overlap_penalty <= 0.25:
        reasons.append("Low overlap penalty: the pair is unlikely to be a duplicate.")

    return {
        "overall_score": overall_score,
        "domain_distance": domain_distance,
        "abstraction_gap": abstraction_gap,
        "mechanism_difference": mechanism_difference,
        "certainty_mismatch": certainty_mismatch,
        "overlap_penalty": overlap_penalty,
        "reasons": reasons,
    }
