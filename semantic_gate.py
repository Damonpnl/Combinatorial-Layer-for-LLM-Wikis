"""Deterministic semantic quality gate for combination provider output."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Literal, TypedDict


SEMANTIC_GATE_VERSION = "semantic-gate-v1"

GateStatus = Literal["accept", "needs_revision", "reject"]


class SemanticGateResult(TypedDict):
    status: GateStatus
    reasons: list[str]
    flags: list[str]


GENERIC_PHRASES = {
    "mechanism-to-context",
    "constraint space",
    "create a new leverage point",
    "decision quality",
    "capital efficiency",
    "distribution leverage",
    "founder execution speed",
    "broad platform",
    "unlock value",
    "synergy",
    "optimize outcomes",
}

GENERIC_BUYERS = {
    "user",
    "users",
    "customer",
    "customers",
    "founder",
    "founders",
    "operator",
    "operators",
    "researcher",
    "researchers",
    "business",
    "businesses",
    "people",
    "anyone",
    "everyone",
}

WEAK_BOTTLENECKS = {
    "unknown",
    "none",
    "n/a",
    "not specified",
    "lack of adoption",
    "execution",
    "finding product market fit",
}

BOILERPLATE_IMPLICATION_PATTERNS = [
    "inspect whether this tag contributes",
    "market context, risk, or distribution leverage",
    "applies across domains",
    "could be useful",
]

VAGUE_FALSIFICATION_PATTERNS = [
    "if it cannot produce",
    "if it doesn't work",
    "if it does not work",
    "if no value",
    "observable behavior change",
    "hard to test",
    "fails to create impact",
]

STOPWORDS = {
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


def normalize_text(value: Any) -> str:
    return str(value or "").strip().lower()


def content_tokens(value: Any) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9][a-z0-9-]{2,}", normalize_text(value))
        if token not in STOPWORDS
    }


def jaccard_similarity(left: set[str], right: set[str]) -> float:
    if not left and not right:
        return 0.0
    union = left | right
    if not union:
        return 0.0
    return len(left & right) / len(union)


def has_generic_phrase(text: str) -> bool:
    lowered = normalize_text(text)
    return any(phrase in lowered for phrase in GENERIC_PHRASES)


def specificity_score(text: str) -> int:
    tokens = content_tokens(text)
    concrete_markers = len(re.findall(r"\b[a-z]+-[a-z]+\b|\b\d+[%x]?\b", normalize_text(text)))
    return len(tokens) + concrete_markers


def is_generic_buyer(text: str) -> bool:
    tokens = content_tokens(text)
    lowered = normalize_text(text)
    if not lowered:
        return True
    if lowered in GENERIC_BUYERS:
        return True
    return len(tokens - GENERIC_BUYERS) < 2


def weak_bottleneck(text: str) -> bool:
    lowered = normalize_text(text)
    if lowered in WEAK_BOTTLENECKS:
        return True
    return specificity_score(text) < 5


def vague_falsification(text: str) -> bool:
    lowered = normalize_text(text)
    if any(pattern in lowered for pattern in VAGUE_FALSIFICATION_PATTERNS):
        return True
    if not any(marker in lowered for marker in ["if", "unless", "when", "within", "after", "before"]):
        return True
    return specificity_score(text) < 7


def boilerplate_implications(values: list[str]) -> bool:
    if not values:
        return True
    boilerplate_count = 0
    for value in values:
        lowered = normalize_text(value)
        if any(pattern in lowered for pattern in BOILERPLATE_IMPLICATION_PATTERNS):
            boilerplate_count += 1
    return boilerplate_count == len(values)


def restates_parent_summaries(output: dict[str, Any], parent_a: dict[str, Any], parent_b: dict[str, Any]) -> bool:
    parent_tokens = content_tokens(parent_a.get("summary", "")) | content_tokens(parent_b.get("summary", ""))
    if not parent_tokens:
        return False
    output_tokens = content_tokens(
        " ".join(
            str(output.get(field, ""))
            for field in ["fusion_summary", "mechanistic_interaction", "product_opportunity", "non_obviousness_reason"]
        )
    )
    if not output_tokens:
        return False
    return jaccard_similarity(output_tokens, parent_tokens) >= 0.55


def irrelevant_related_pages(output: dict[str, Any], parent_a: dict[str, Any], parent_b: dict[str, Any]) -> list[str]:
    allowed = {
        str(value).strip().replace("\\", "/").removesuffix(".md")
        for value in [
            *parent_a.get("linked_concepts", []),
            *parent_b.get("linked_concepts", []),
            parent_a.get("path", ""),
            parent_b.get("path", ""),
        ]
        if str(value).strip()
    }
    irrelevant: list[str] = []
    for related in output.get("related_canonical_pages", []):
        normalized = str(related).strip().replace("\\", "/").removesuffix(".md")
        if normalized not in allowed:
            irrelevant.append(str(related))
    return irrelevant


def score_inconsistency(output: dict[str, Any], flags: list[str]) -> bool:
    novelty = float(output.get("novelty_score", 0.0))
    plausibility = float(output.get("plausibility_score", 0.0))
    weak_novelty_flags = {"generic_mechanism", "generic_product", "restates_parent_summaries", "boilerplate_implications"}
    weak_plausibility_flags = {"vague_falsification", "weak_bottleneck", "generic_buyer"}
    if novelty >= 0.75 and any(flag in flags for flag in weak_novelty_flags):
        return True
    if plausibility >= 0.75 and any(flag in flags for flag in weak_plausibility_flags):
        return True
    return False


def evaluate_semantic_quality(output: dict[str, Any], parent_a: dict[str, Any], parent_b: dict[str, Any]) -> SemanticGateResult:
    reasons: list[str] = []
    flags: list[str] = []
    severe = 0

    if has_generic_phrase(output.get("mechanistic_interaction", "")) or specificity_score(output.get("mechanistic_interaction", "")) < 7:
        flags.append("generic_mechanism")
        reasons.append("Mechanistic interaction is generic or underspecified.")
        severe += 1

    if has_generic_phrase(output.get("product_opportunity", "")) or "platform" in normalize_text(output.get("product_opportunity", "")):
        flags.append("generic_product")
        reasons.append("Product opportunity is too broad or platform-like.")
        severe += 1

    if vague_falsification(output.get("falsification_test", "")):
        flags.append("vague_falsification")
        reasons.append("Falsification test is vague or not observably testable.")
        severe += 1

    if boilerplate_implications(output.get("cross_niche_implications", [])):
        flags.append("boilerplate_implications")
        reasons.append("Cross-niche implications look boilerplate.")

    if restates_parent_summaries(output, parent_a, parent_b):
        flags.append("restates_parent_summaries")
        reasons.append("Output mostly restates parent summaries.")
        severe += 1

    irrelevant = irrelevant_related_pages(output, parent_a, parent_b)
    if irrelevant:
        flags.append("irrelevant_related_pages")
        reasons.append("Related canonical pages include suggestions not grounded in parent links.")
        if len(irrelevant) == len(output.get("related_canonical_pages", [])):
            severe += 1

    if is_generic_buyer(output.get("specific_user_or_buyer", "")):
        flags.append("generic_buyer")
        reasons.append("Specific user or buyer is empty or generic.")
        severe += 1

    if weak_bottleneck(output.get("primary_bottleneck", "")):
        flags.append("weak_bottleneck")
        reasons.append("Primary bottleneck is missing or weak.")
        severe += 1

    if score_inconsistency(output, flags):
        flags.append("score_inconsistency")
        reasons.append("Novelty or plausibility scores are too high for the text quality.")
        severe += 1

    if severe >= 3:
        status: GateStatus = "reject"
    elif flags:
        status = "needs_revision"
    else:
        status = "accept"

    return {"status": status, "reasons": reasons, "flags": flags}


def save_gate_diagnostics(path: Path, result: SemanticGateResult, output: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"semantic_gate": result, "draft_title": output.get("draft_title")}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
