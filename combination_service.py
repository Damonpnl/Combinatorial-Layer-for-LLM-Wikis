"""Core backend for the LLM Wiki combination game.

This module keeps the feature document-native: canonical markdown pages are
read as fixed ingredients, draft combinations are written separately, and
promotion remains explicit.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import shutil
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from combination_providers import PROMPT_VERSION, CombineInput, CombineOutput, CombineProvider, load_config, load_provider, validate_output
from pair_scorer import PAIR_SCORER_VERSION, PairScore, score_pair
from semantic_gate import SEMANTIC_GATE_VERSION, SemanticGateResult, evaluate_semantic_quality, save_gate_diagnostics


PROJECT_ROOT = Path(__file__).resolve().parent
EXCLUDED_CANONICAL_DIRS = {"sources", "outputs", "combinations", "promotion-queue"}
CANONICAL_TYPES = {"concept", "entity", "protocol", "tool", "comparison", "synthesis"}
STANDARD_TAGS = {
    "defi",
    "ai",
    "biohacking",
    "social-media",
    "startups",
    "politics",
    "philosophies",
    "markets",
    "cross-niche",
}
MERGE_STRATEGIES = {"create_new_canonical", "append_to_existing", "keep_as_draft", "reject"}
DEFAULT_PAIR_SCORE_THRESHOLD = 0.25
DEFAULT_BLOCK_LOW_SCORE = False
DEFAULT_NEEDS_REVISION_BEHAVIOR = "allow"
DEFAULT_SAVE_SEMANTIC_DIAGNOSTICS = False
DEFAULT_CACHE_ENABLED = True
EXTRACTOR_VERSION = "parent-extractor-v2"
CERTAINTY_LEVELS = {
    "protocol_defined",
    "empirical_human",
    "empirical_preclinical",
    "interpretive",
    "historical_pattern",
    "unknown",
}

FRONTMATTER_RE = re.compile(r"\A---\s*\n(?P<meta>.*?)\n---\s*\n?", re.DOTALL)
WIKILINK_RE = re.compile(r"\[\[([^\]#|]+)(?:#[^\]|]+)?(?:\|[^\]]+)?\]\]")
PROVIDER_WIKILINK_RE = re.compile(r"\[\[([^\]#|]+)(?:#[^\]|]+)?(?:\|([^\]]+))?\]\]")
CROSS_NICHE_RE = re.compile(r"^#+\s+Cross-Niche Implications\s*$", re.IGNORECASE | re.MULTILINE)


@dataclass(frozen=True)
class WikiPage:
    path: Path
    relative_path: str
    wikilink_path: str
    title: str
    summary: str
    tags: list[str]
    page_type: str
    status: str
    outgoing_wikilinks: list[str]
    body: str
    has_cross_niche_implications: bool
    metadata: dict[str, Any]


@dataclass(frozen=True)
class CombinationResult:
    title: str
    summary: str
    tags: list[str]
    parents: tuple[WikiPage, WikiPage]
    related_pages: list[WikiPage]
    sections: dict[str, str]
    prompt: str
    created_on: str
    provider_name: str
    output: CombineOutput
    pair_score: PairScore
    pair_score_threshold: float
    pair_score_blocked: bool
    pair_score_warning: str | None
    semantic_gate: SemanticGateResult
    generation_metadata: dict[str, Any]


def split_frontmatter(text: str) -> tuple[str, str]:
    match = FRONTMATTER_RE.match(text)
    if not match:
        return "", text
    return match.group("meta"), text[match.end() :]


def parse_scalar_or_inline_list(raw: str) -> Any:
    value = raw.strip()
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [item.strip().strip('"').strip("'") for item in next(csv.reader([inner]))]
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]
    return value


def parse_frontmatter(meta: str) -> dict[str, Any]:
    """Parse the small YAML subset used by this wiki.

    Supports scalar fields, inline lists, and indented dash lists. This is
    deliberately not a general YAML parser so v1 has no external dependency.
    """

    parsed: dict[str, Any] = {}
    lines = meta.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.strip() or line.lstrip().startswith("#") or ":" not in line:
            index += 1
            continue
        key, raw_value = line.split(":", 1)
        key = key.strip()
        raw_value = raw_value.strip()
        if raw_value:
            parsed[key] = parse_scalar_or_inline_list(raw_value)
            index += 1
            continue
        items: list[str] = []
        index += 1
        while index < len(lines):
            item_line = lines[index]
            stripped = item_line.strip()
            if not item_line.startswith((" ", "\t")):
                break
            if stripped.startswith("- "):
                items.append(stripped[2:].strip().strip('"').strip("'"))
            index += 1
        parsed[key] = items
    return parsed


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "combination-draft"


def yaml_inline_list(values: list[str]) -> str:
    return "[" + ", ".join(json.dumps(value) for value in values) + "]"


def unique_path(directory: Path, stem: str, suffix: str = ".md") -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    candidate = directory / f"{stem}{suffix}"
    counter = 2
    while candidate.exists():
        candidate = directory / f"{stem}-{counter}{suffix}"
        counter += 1
    return candidate


def strip_wikilink_syntax(value: str) -> str:
    stripped = value.strip()
    if stripped.startswith("[[") and stripped.endswith("]]"):
        stripped = stripped[2:-2].split("|", 1)[0].split("#", 1)[0]
    return stripped.strip()


def title_from_slug(value: str) -> str:
    return value.replace("-", " ").replace("_", " ").title()


def stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def hash_payload(value: Any) -> str:
    return hash_text(stable_json(value))


class CombinationService:
    """Service boundary for canonical discovery and combination drafts."""

    def __init__(
        self,
        root: Path = PROJECT_ROOT,
        provider: CombineProvider | None = None,
        config_path: Path | None = None,
        provider_type: str | None = None,
    ) -> None:
        self.root = root.resolve()
        self.wiki_root = self.root / "wiki"
        self.draft_dir = self.wiki_root / "combinations" / "drafts"
        self.pending_dir = self.wiki_root / "promotion-queue" / "pending"
        self.combinations_index = self.wiki_root / "combinations" / "index.md"
        self.cache_dir = self.wiki_root / "combinations" / "cache"
        self.semantic_diagnostics_dir = self.wiki_root / "combinations" / "diagnostics"
        self.main_index = self.wiki_root / "index.md"
        self.log = self.wiki_root / "log.md"
        self._provider = provider
        self.config_path = config_path
        self.provider_type = provider_type
        self.prompt_version = PROMPT_VERSION
        self.extractor_version = EXTRACTOR_VERSION
        self.pair_scorer_version = PAIR_SCORER_VERSION
        self.semantic_gate_version = SEMANTIC_GATE_VERSION

    @property
    def provider(self) -> CombineProvider:
        if self._provider is None:
            self._provider = load_provider(self.root, config_path=self.config_path, override_type=self.provider_type)
        return self._provider

    def pair_score_policy(self) -> tuple[float, bool]:
        config = load_config(self.root, self.config_path)
        scorer_config = config.get("pair_scoring", {})
        threshold = float(scorer_config.get("score_threshold", DEFAULT_PAIR_SCORE_THRESHOLD))
        block_low_score = bool(scorer_config.get("block_low_score", DEFAULT_BLOCK_LOW_SCORE))
        return threshold, block_low_score

    def semantic_gate_policy(self) -> tuple[str, bool]:
        config = load_config(self.root, self.config_path)
        gate_config = config.get("semantic_gate", {})
        needs_revision_behavior = str(
            gate_config.get("needs_revision_behavior", DEFAULT_NEEDS_REVISION_BEHAVIOR)
        ).lower()
        if needs_revision_behavior not in {"allow", "block"}:
            raise ValueError("semantic_gate.needs_revision_behavior must be 'allow' or 'block'.")
        save_diagnostics = bool(gate_config.get("save_diagnostics", DEFAULT_SAVE_SEMANTIC_DIAGNOSTICS))
        return needs_revision_behavior, save_diagnostics

    def cache_enabled(self) -> bool:
        config = load_config(self.root, self.config_path)
        return bool(config.get("cache", {}).get("enabled", DEFAULT_CACHE_ENABLED))

    def config_hash(self) -> str:
        return hash_payload(load_config(self.root, self.config_path))

    def provider_model(self) -> str:
        provider = self.provider
        model = getattr(provider, "model", None)
        if model:
            return str(model)
        provider_config = load_config(self.root, self.config_path).get("combine_provider", {})
        return str(provider_config.get("model") or provider_config.get("command") or provider.name)

    def page_content_hash(self, page: WikiPage) -> str:
        return hash_text(page.path.read_text(encoding="utf-8"))

    def canonical_paths_hash(self) -> str:
        paths: list[str] = []
        for path in sorted(self.wiki_root.rglob("*.md")):
            if self.is_canonical_path(path):
                paths.append(self.wikilink_path(path))
        return hash_payload(paths)

    def cache_key(self, layer: str, payload: dict[str, Any]) -> str:
        return hash_payload({"layer": layer, **payload})

    def read_cache(self, layer: str, key: str) -> dict[str, Any] | None:
        if not self.cache_enabled():
            return None
        path = self.cache_dir / layer / f"{key}.json"
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None

    def write_cache(self, layer: str, key: str, payload: dict[str, Any]) -> None:
        if not self.cache_enabled():
            return
        path = self.cache_dir / layer / f"{key}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    def relative_to_root(self, path: Path) -> str:
        return path.resolve().relative_to(self.root).as_posix()

    def wikilink_path(self, path: Path) -> str:
        return path.resolve().relative_to(self.wiki_root).with_suffix("").as_posix()

    def is_canonical_path(self, path: Path) -> bool:
        try:
            relative = path.resolve().relative_to(self.wiki_root.resolve())
        except ValueError:
            return False
        if path.suffix.lower() != ".md":
            return False
        return not (relative.parts and relative.parts[0] in EXCLUDED_CANONICAL_DIRS)

    def read_page(self, path: Path) -> WikiPage:
        text = path.read_text(encoding="utf-8")
        meta_text, body = split_frontmatter(text)
        metadata = parse_frontmatter(meta_text)
        title = str(metadata.get("title") or path.stem.replace("-", " ").title())
        summary = str(metadata.get("summary") or "No summary provided.")
        tags = [str(tag) for tag in metadata.get("tags", [])]
        page_type = str(metadata.get("type") or "")
        status = str(metadata.get("status") or "")
        return WikiPage(
            path=path.resolve(),
            relative_path=self.relative_to_root(path),
            wikilink_path=self.wikilink_path(path),
            title=title,
            summary=summary,
            tags=tags,
            page_type=page_type,
            status=status,
            outgoing_wikilinks=sorted(set(WIKILINK_RE.findall(body))),
            body=body,
            has_cross_niche_implications=bool(CROSS_NICHE_RE.search(body)),
            metadata=metadata,
        )

    def discover_canonical_pages(self) -> list[WikiPage]:
        pages: list[WikiPage] = []
        for path in sorted(self.wiki_root.rglob("*.md")):
            if not self.is_canonical_path(path):
                continue
            page = self.read_page(path)
            if page.page_type in CANONICAL_TYPES:
                pages.append(page)
        return pages

    def resolve_canonical_page(self, value: str) -> WikiPage:
        normalized = strip_wikilink_syntax(value).replace("\\", "/").strip("/")
        candidates: list[Path] = []
        raw = Path(normalized)
        if raw.is_absolute():
            candidates.append(raw)
        else:
            if normalized.startswith("wiki/"):
                candidates.append(self.root / normalized)
            candidates.append(self.wiki_root / normalized)
            if not normalized.endswith(".md"):
                if normalized.startswith("wiki/"):
                    candidates.append(self.root / f"{normalized}.md")
                candidates.append(self.wiki_root / f"{normalized}.md")

        for candidate in candidates:
            if not candidate.exists() or not candidate.is_file():
                continue
            if not self.is_canonical_path(candidate):
                continue
            page = self.read_page(candidate)
            if page.page_type in CANONICAL_TYPES:
                return page
        raise SystemExit(f"Canonical wiki page not found or not allowed: {value}")

    def resolve_existing_canonical_link(self, value: str) -> WikiPage | None:
        try:
            return self.resolve_canonical_page(value)
        except SystemExit:
            return None

    def combined_tags(self, parent_a: WikiPage, parent_b: WikiPage) -> list[str]:
        tags: list[str] = []
        for parent in (parent_a, parent_b):
            for tag in parent.tags:
                if tag in STANDARD_TAGS and tag not in tags:
                    tags.append(tag)
        if "cross-niche" not in tags:
            tags.append("cross-niche")
        return tags

    def related_pages(self, parent_a: WikiPage, parent_b: WikiPage) -> list[WikiPage]:
        parent_paths = {parent_a.wikilink_path, parent_b.wikilink_path}
        related: list[WikiPage] = []
        seen: set[str] = set(parent_paths)
        for link in parent_a.outgoing_wikilinks + parent_b.outgoing_wikilinks:
            page = self.resolve_existing_canonical_link(link)
            if not page or page.wikilink_path in seen:
                continue
            seen.add(page.wikilink_path)
            related.append(page)
        return related[:12]

    def extract_section_items(self, body: str, headings: set[str]) -> list[str]:
        lines = body.splitlines()
        items: list[str] = []
        capturing = False
        for line in lines:
            heading = re.match(r"^#+\s+(.+?)\s*$", line)
            if heading:
                normalized = slugify(heading.group(1))
                capturing = normalized in headings
                continue
            if not capturing:
                continue
            stripped = line.strip()
            if stripped.startswith(("- ", "* ")):
                items.append(stripped[2:].strip())
            elif stripped and len(items) < 3:
                items.append(stripped)
        return items[:8]

    def extract_first_section_item(self, body: str, headings: set[str]) -> str:
        items = self.extract_section_items(body, headings)
        return items[0] if items else "unknown"

    def match_certainty_level(self, text: str) -> str | None:
        normalized = slugify(text).replace("-", "_")
        if normalized in CERTAINTY_LEVELS:
            return normalized
        lowered = text.lower()
        if any(term in lowered for term in ["human clinical", "clinical trial", "randomized", "systematic review", "human study"]):
            return "empirical_human"
        if any(term in lowered for term in ["preclinical", "animal study", "rodent", "mouse", "mice", "in vitro"]):
            return "empirical_preclinical"
        if any(term in lowered for term in ["historical pattern", "historical cycle", "secular cycle", "case history"]):
            return "historical_pattern"
        if any(term in lowered for term in ["interpretive", "framework", "lens", "synthesis", "hypothesis"]):
            return "interpretive"
        if any(term in lowered for term in ["protocol-defined", "protocol defined", "formal protocol", "specification"]):
            return "protocol_defined"
        return None

    def extract_certainty_level(self, page: WikiPage) -> str:
        certainty_items = self.extract_section_items(page.body, {"certainty-level", "evidence-base", "evidence", "validation-status"})
        for item in certainty_items:
            matched = self.match_certainty_level(item)
            if matched:
                return matched

        text = f"{page.title}\n{page.summary}\n{page.body[:4000]}"
        matched = self.match_certainty_level(text)
        if matched:
            return matched
        if page.page_type in {"protocol", "tool"} and re.search(r"\b(protocol|specification|standard)\b", text, re.IGNORECASE):
            return "protocol_defined"
        if page.page_type in {"synthesis", "comparison"}:
            return "interpretive"
        return "unknown"

    def existing_link_paths(self, page: WikiPage) -> list[str]:
        links: list[str] = []
        for link in page.outgoing_wikilinks:
            linked = self.resolve_existing_canonical_link(link)
            if linked and linked.relative_path not in links:
                links.append(linked.relative_path)
        return links

    def build_page_payload(self, page: WikiPage) -> dict[str, Any]:
        return {
            "path": page.relative_path,
            "title": page.title,
            "summary": page.summary,
            "tags": page.tags,
            "type": page.page_type,
            "status": page.status,
            "mechanisms": self.extract_section_items(page.body, {"mechanisms", "mechanism", "core-mechanism"}),
            "incentives": self.extract_section_items(page.body, {"incentives", "incentive-design"}),
            "actors": self.extract_section_items(page.body, {"actors", "key-actors", "stakeholders"}),
            "risks": self.extract_section_items(page.body, {"risks", "risk", "failure-modes"}),
            "linked_concepts": self.existing_link_paths(page),
            "cross_niche_implications": self.extract_section_items(page.body, {"cross-niche-implications"}),
            "core_mechanism": self.extract_first_section_item(page.body, {"core-mechanism", "mechanism", "mechanisms"}),
            "control_variable": self.extract_first_section_item(page.body, {"control-variable", "control-variables", "key-variable", "key-variables"}),
            "primary_bottleneck": self.extract_first_section_item(page.body, {"primary-bottleneck", "bottleneck", "bottlenecks", "constraint", "constraints"}),
            "dominant_failure_mode": self.extract_first_section_item(page.body, {"dominant-failure-mode", "failure-mode", "failure-modes", "risks", "risk"}),
            "highest_leverage_use_case": self.extract_first_section_item(page.body, {"highest-leverage-use-case", "highest-leverage-use-cases", "use-case", "use-cases", "applications"}),
            "certainty_level": self.extract_certainty_level(page),
            "body_text": page.body.strip()[:12000],
        }

    def page_to_combine_input(self, page: WikiPage) -> dict[str, Any]:
        content_hash = self.page_content_hash(page)
        key = self.cache_key(
            "extraction",
            {
                "path": page.relative_path,
                "content_hash": content_hash,
                "canonical_paths_hash": self.canonical_paths_hash(),
                "extractor_version": self.extractor_version,
                "config_hash": self.config_hash(),
            },
        )
        cached = self.read_cache("extractions", key)
        if cached and cached.get("payload"):
            return cached["payload"]
        payload = self.build_page_payload(page)
        self.write_cache(
            "extractions",
            key,
            {
                "metadata": {
                    "cache_layer": "extractions",
                    "cache_key": key,
                    "path": page.relative_path,
                    "content_hash": content_hash,
                    "extractor_version": self.extractor_version,
                    "config_hash": self.config_hash(),
                },
                "payload": payload,
            },
        )
        return payload

    def build_combine_input(self, parent_a: WikiPage, parent_b: WikiPage) -> CombineInput:
        return {
            "parent_a": self.page_to_combine_input(parent_a),
            "parent_b": self.page_to_combine_input(parent_b),
        }

    def build_generation_prompt(self, parent_a: WikiPage, parent_b: WikiPage) -> str:
        return f"""Generate a speculative combination draft for a structured markdown LLM Wiki.

Rules:
- Use only the two canonical parent pages as primary grounding.
- Treat the output as hypothesis generation, not canonical truth.
- Preserve lineage to both parent pages.
- Do not invent related wiki links; only use existing canonical pages.
- Produce these sections exactly: Fusion Summary, Mechanistic Interaction, Product Opportunity, System Design, Research Question, Falsification Test, Cross-Niche Implications, Failure Modes, Related Canonical Pages.

Parent A:
- Path: {parent_a.relative_path}
- Title: {parent_a.title}
- Summary: {parent_a.summary}
- Tags: {', '.join(parent_a.tags)}
- Type/status: {parent_a.page_type}/{parent_a.status}
- Has Cross-Niche Implications section: {parent_a.has_cross_niche_implications}
- Outgoing links: {', '.join(parent_a.outgoing_wikilinks)}

Parent B:
- Path: {parent_b.relative_path}
- Title: {parent_b.title}
- Summary: {parent_b.summary}
- Tags: {', '.join(parent_b.tags)}
- Type/status: {parent_b.page_type}/{parent_b.status}
- Has Cross-Niche Implications section: {parent_b.has_cross_niche_implications}
- Outgoing links: {', '.join(parent_b.outgoing_wikilinks)}
"""

    def sanitize_provider_wikilinks(self, text: str) -> str:
        def replace(match: re.Match[str]) -> str:
            target = match.group(1).strip()
            label = (match.group(2) or target).strip()
            page = self.resolve_existing_canonical_link(target)
            if page:
                return f"[[{page.wikilink_path}|{label}]]"
            return label

        return PROVIDER_WIKILINK_RE.sub(replace, text)

    def markdown_list(self, values: list[str], sanitize_wikilinks: bool = False) -> str:
        if not values:
            return "- No provider output."
        if sanitize_wikilinks:
            values = [self.sanitize_provider_wikilinks(value) for value in values]
        return "\n".join(f"- {value}" for value in values)

    def high_risk_pair(self, output: CombineOutput, parents: tuple[WikiPage, WikiPage] | None = None) -> bool:
        tags = {str(tag).lower() for tag in output.get("tags", [])}
        if parents:
            for parent in parents:
                tags.update(str(tag).lower() for tag in parent.tags)
        high_risk_tags = {"biohacking", "defi", "markets"}
        if tags & high_risk_tags:
            return True
        text = " ".join(
            [
                output.get("draft_title", ""),
                output.get("draft_summary", ""),
                output.get("fusion_summary", ""),
                output.get("mechanistic_interaction", ""),
            ]
        ).lower()
        return any(term in text for term in ["biomedical", "clinical", "peptide", "financial", "trading", "investment", "medical"])

    def interaction_boundary_section(self, output: CombineOutput, parents: tuple[WikiPage, WikiPage] | None = None) -> str:
        interaction_type = output["interaction_type"]
        lines = [f"- Interaction type: `{interaction_type}`."]
        if interaction_type == "analogical":
            lines.append("- This is an analogical comparison; it does not establish causal equivalence between the parent mechanisms.")
        elif interaction_type == "mechanistic":
            lines.append("- This draft proposes a mechanism, but the mechanism remains provisional until supported by evidence.")
        else:
            lines.append("- This interaction label describes the synthesis frame, not a promoted canonical claim.")
        if self.high_risk_pair(output, parents):
            lines.append("- High-risk domain caution: treat biomedical, financial, or operational claims as speculative until independently sourced and reviewed.")
        return "\n".join(lines)

    def safe_related_pages_from_output(self, output: CombineOutput, parent_a: WikiPage, parent_b: WikiPage) -> list[WikiPage]:
        parent_paths = {parent_a.relative_path, parent_b.relative_path, parent_a.wikilink_path, parent_b.wikilink_path}
        related: list[WikiPage] = []
        seen: set[str] = set(parent_paths)
        for link in output.get("related_canonical_pages", []):
            page = self.resolve_existing_canonical_link(link)
            if not page or page.wikilink_path in seen or page.relative_path in seen:
                continue
            seen.add(page.wikilink_path)
            related.append(page)
        if related:
            return related[:12]
        return self.related_pages(parent_a, parent_b)

    def output_sections(self, output: CombineOutput, related: list[WikiPage], parents: tuple[WikiPage, WikiPage] | None = None) -> dict[str, str]:
        return {
            "Fusion Summary": self.sanitize_provider_wikilinks(output["fusion_summary"]),
            "Interaction Boundary": self.interaction_boundary_section(output, parents),
            "Mechanistic Interaction": self.sanitize_provider_wikilinks(output["mechanistic_interaction"]),
            "Product Opportunity": self.sanitize_provider_wikilinks(output["product_opportunity"]),
            "Non-Obviousness Reason": self.sanitize_provider_wikilinks(output["non_obviousness_reason"]),
            "Primary Bottleneck": self.sanitize_provider_wikilinks(output["primary_bottleneck"]),
            "Specific User Or Buyer": self.sanitize_provider_wikilinks(output["specific_user_or_buyer"]),
            "Interaction Type": output["interaction_type"],
            "Grounded Points": self.markdown_list(output["grounded_points"], sanitize_wikilinks=True),
            "Speculative Extensions": self.markdown_list(output["speculative_extensions"], sanitize_wikilinks=True),
            "Evidence Needed Before Promotion": self.markdown_list(output["evidence_needed_before_promotion"], sanitize_wikilinks=True),
            "Novelty Score": f"{output['novelty_score']:.2f}",
            "Plausibility Score": f"{output['plausibility_score']:.2f}",
            "Promotion Readiness": output["promotion_readiness"],
            "System Design": self.sanitize_provider_wikilinks(output["system_design"]),
            "Research Question": self.sanitize_provider_wikilinks(output["research_question"]),
            "Falsification Test": self.sanitize_provider_wikilinks(output["falsification_test"]),
            "Cross-Niche Implications": self.markdown_list(output["cross_niche_implications"], sanitize_wikilinks=True),
            "Failure Modes": self.markdown_list(output["failure_modes"], sanitize_wikilinks=True),
            "Related Canonical Pages": self.related_pages_section(related),
        }

    def pair_score_for(self, combine_input: CombineInput, parent_a: WikiPage, parent_b: WikiPage) -> PairScore:
        input_hash = hash_payload(combine_input)
        key = self.cache_key(
            "pair_score",
            {
                "parent_a_path": parent_a.relative_path,
                "parent_a_content_hash": self.page_content_hash(parent_a),
                "parent_b_path": parent_b.relative_path,
                "parent_b_content_hash": self.page_content_hash(parent_b),
                "input_hash": input_hash,
                "pair_scorer_version": self.pair_scorer_version,
                "config_hash": self.config_hash(),
            },
        )
        cached = self.read_cache("pair_scores", key)
        if cached and cached.get("payload"):
            return cached["payload"]
        payload = score_pair(combine_input["parent_a"], combine_input["parent_b"])
        self.write_cache(
            "pair_scores",
            key,
            {
                "metadata": {
                    "cache_layer": "pair_scores",
                    "cache_key": key,
                    "input_hash": input_hash,
                    "pair_scorer_version": self.pair_scorer_version,
                    "config_hash": self.config_hash(),
                },
                "payload": payload,
            },
        )
        return payload

    def synthesis_output_for(self, combine_input: CombineInput, parent_a: WikiPage, parent_b: WikiPage) -> tuple[CombineOutput, str, bool]:
        provider_name = self.provider.name
        provider_model = self.provider_model()
        key = self.cache_key(
            "synthesis",
            {
                "parent_a_path": parent_a.relative_path,
                "parent_a_content_hash": self.page_content_hash(parent_a),
                "parent_b_path": parent_b.relative_path,
                "parent_b_content_hash": self.page_content_hash(parent_b),
                "input_hash": hash_payload(combine_input),
                "prompt_version": self.prompt_version,
                "provider_name": provider_name,
                "provider_model": provider_model,
                "config_hash": self.config_hash(),
            },
        )
        cached = self.read_cache("synthesis", key)
        if cached and cached.get("payload"):
            try:
                return validate_output(cached["payload"]), key, True
            except ValueError:
                pass
        output = validate_output(self.provider.synthesize(combine_input))
        self.write_cache(
            "synthesis",
            key,
            {
                "metadata": {
                    "cache_layer": "synthesis",
                    "cache_key": key,
                    "prompt_version": self.prompt_version,
                    "provider_name": provider_name,
                    "provider_model": provider_model,
                    "config_hash": self.config_hash(),
                },
                "payload": output,
            },
        )
        return output, key, False

    def generation_metadata(
        self,
        parent_a: WikiPage,
        parent_b: WikiPage,
        synthesis_cache_key: str,
        synthesis_cache_hit: bool,
    ) -> dict[str, Any]:
        return {
            "prompt_version": self.prompt_version,
            "provider_name": self.provider.name,
            "provider_model": self.provider_model(),
            "extractor_version": self.extractor_version,
            "pair_scorer_version": self.pair_scorer_version,
            "semantic_gate_version": self.semantic_gate_version,
            "config_hash": self.config_hash(),
            "parent_a": {
                "path": parent_a.relative_path,
                "content_hash": self.page_content_hash(parent_a),
            },
            "parent_b": {
                "path": parent_b.relative_path,
                "content_hash": self.page_content_hash(parent_b),
            },
            "synthesis_cache_key": synthesis_cache_key,
            "synthesis_cache_hit": synthesis_cache_hit,
        }

    def combine_pages(self, parent_a_arg: str, parent_b_arg: str, title: str | None = None) -> CombinationResult:
        parent_a = self.resolve_canonical_page(parent_a_arg)
        parent_b = self.resolve_canonical_page(parent_b_arg)
        combine_input = self.build_combine_input(parent_a, parent_b)
        pair_score = self.pair_score_for(combine_input, parent_a, parent_b)
        score_threshold, block_low_score = self.pair_score_policy()
        score_warning = None
        if pair_score["overall_score"] < score_threshold:
            score_warning = (
                f"Pair score {pair_score['overall_score']:.3f} is below the configured "
                f"threshold {score_threshold:.3f}."
            )
            if block_low_score:
                raise SystemExit(score_warning)
        output, synthesis_cache_key, synthesis_cache_hit = self.synthesis_output_for(combine_input, parent_a, parent_b)
        semantic_gate = evaluate_semantic_quality(output, combine_input["parent_a"], combine_input["parent_b"])
        needs_revision_behavior, save_semantic_diagnostics = self.semantic_gate_policy()
        if save_semantic_diagnostics and semantic_gate["status"] != "accept":
            diagnostics_path = unique_path(self.semantic_diagnostics_dir, slugify(output["draft_title"]), ".json")
            save_gate_diagnostics(diagnostics_path, semantic_gate, output)
        if semantic_gate["status"] == "reject":
            raise SystemExit("Semantic gate rejected provider output: " + "; ".join(semantic_gate["reasons"]))
        if semantic_gate["status"] == "needs_revision" and needs_revision_behavior == "block":
            raise SystemExit("Semantic gate requires revision: " + "; ".join(semantic_gate["reasons"]))
        draft_title = title or output["draft_title"]
        tags = output["tags"] or self.combined_tags(parent_a, parent_b)
        if "cross-niche" not in tags:
            tags.append("cross-niche")
        related = self.safe_related_pages_from_output(output, parent_a, parent_b)
        today = date.today().isoformat()
        summary = output["draft_summary"]
        sections = self.output_sections(output, related, (parent_a, parent_b))
        return CombinationResult(
            title=draft_title,
            summary=summary,
            tags=tags,
            parents=(parent_a, parent_b),
            related_pages=related,
            sections=sections,
            prompt=self.build_generation_prompt(parent_a, parent_b),
            created_on=today,
            provider_name=self.provider.name,
            output=output,
            pair_score=pair_score,
            pair_score_threshold=score_threshold,
            pair_score_blocked=block_low_score,
            pair_score_warning=score_warning,
            semantic_gate=semantic_gate,
            generation_metadata=self.generation_metadata(parent_a, parent_b, synthesis_cache_key, synthesis_cache_hit),
        )

    def fusion_summary(self, parent_a: WikiPage, parent_b: WikiPage) -> str:
        return "\n".join(
            [
                f"- Combine [[{parent_a.wikilink_path}|{parent_a.title}]] with [[{parent_b.wikilink_path}|{parent_b.title}]] as a speculative mechanism-to-context pairing.",
                f"- Parent A grounding: {parent_a.summary}",
                f"- Parent B grounding: {parent_b.summary}",
                "- This is a hypothesis map, not a new canonical claim.",
            ]
        )

    def product_opportunity(self) -> str:
        return "\n".join(
            [
                "- Search for a narrow product wedge where one parent supplies the operating mechanism and the other supplies a market, behavior, workflow, or constraint.",
                "- Favor opportunities that can be validated with a small user loop before any canonical page is updated.",
                "- Strong candidates should improve decision quality, capital efficiency, distribution leverage, or founder execution speed.",
            ]
        )

    def system_design(self, parent_a: WikiPage, parent_b: WikiPage) -> str:
        return "\n".join(
            [
                "- Ingredient layer: canonical parents remain immutable inputs for the draft.",
                "- Synthesis layer: the combination draft explores mechanisms, product patterns, and implications.",
                "- Review layer: promotion requires a pending review artifact before canonical pages are edited.",
                f"- Parent lineage is preserved through `{parent_a.relative_path}` and `{parent_b.relative_path}`.",
            ]
        )

    def research_question(self, parent_a: WikiPage, parent_b: WikiPage) -> str:
        return "\n".join(
            [
                f"- What becomes possible if the mechanism in [[{parent_a.wikilink_path}|{parent_a.title}]] is applied to the constraints in [[{parent_b.wikilink_path}|{parent_b.title}]]?",
                "- Which claims would require raw-source support before promotion?",
                "- What observation would quickly falsify the usefulness of this fusion?",
            ]
        )

    def cross_niche_implications(self, parent_a: WikiPage, parent_b: WikiPage, tags: list[str]) -> str:
        lines = [
            f"- `{tag}`: inspect whether this tag contributes mechanism, market context, risk, or distribution leverage."
            for tag in tags
        ]
        if parent_a.has_cross_niche_implications:
            lines.append(f"- [[{parent_a.wikilink_path}|{parent_a.title}]] already has a cross-niche section; treat it as a stronger bridge signal.")
        if parent_b.has_cross_niche_implications:
            lines.append(f"- [[{parent_b.wikilink_path}|{parent_b.title}]] already has a cross-niche section; treat it as a stronger bridge signal.")
        return "\n".join(lines)

    def failure_modes(self) -> str:
        return "\n".join(
            [
                "- False analogy: shared vocabulary may hide different causal mechanisms.",
                "- Overextension: a useful speculative frame can become an unsupported factual claim.",
                "- Canonical contamination: parent pages must not backlink to this draft unless it is promoted.",
                "- Staleness: verify either parent before operational use if the underlying niche is fast-moving.",
            ]
        )

    def related_pages_section(self, related: list[WikiPage]) -> str:
        if not related:
            return "- No existing related canonical pages detected."
        return "\n".join(f"- [[{page.wikilink_path}|{page.title}]]" for page in related)

    def draft_filename_stem(self, parent_a: WikiPage, parent_b: WikiPage) -> str:
        return f"{slugify(Path(parent_a.wikilink_path).name)}-x-{slugify(Path(parent_b.wikilink_path).name)}"

    def render_draft(self, result: CombinationResult) -> str:
        parent_a, parent_b = result.parents
        parent_lines = "\n".join(f"  - {parent.relative_path}" for parent in result.parents)
        section_blocks = "\n\n".join(f"# {name}\n\n{body}" for name, body in result.sections.items())
        score_warning = json.dumps(result.pair_score_warning) if result.pair_score_warning else "null"
        return f"""---
title: {json.dumps(result.title)}
date_created: {result.created_on}
date_modified: {result.created_on}
last_verified: {result.created_on}
summary: {json.dumps(result.summary)}
tags: {yaml_inline_list(result.tags)}
type: synthesis
status: draft
origin: combination
parents:
{parent_lines}
promotion_state: not-submitted
combination_mode: canonical-canonical
pair_score: {json.dumps(result.pair_score)}
pair_score_threshold: {result.pair_score_threshold:.3f}
pair_score_block_low: {str(result.pair_score_blocked).lower()}
pair_score_warning: {score_warning}
generation_metadata: {json.dumps(result.generation_metadata)}
---

This is a speculative draft derived from combining two canonical wiki pages: [[{parent_a.wikilink_path}|{parent_a.title}]] and [[{parent_b.wikilink_path}|{parent_b.title}]]. It is not canonical, source-grounded truth until explicitly reviewed and promoted.

{section_blocks}
"""

    def create_draft(
        self,
        parent_a_arg: str,
        parent_b_arg: str,
        title: str | None = None,
        update_indexes: bool = True,
    ) -> Path:
        result = self.combine_pages(parent_a_arg, parent_b_arg, title)
        path = self.write_draft_result(result, update_indexes=update_indexes)
        return path

    def create_draft_with_result(
        self,
        parent_a_arg: str,
        parent_b_arg: str,
        title: str | None = None,
        update_indexes: bool = True,
    ) -> tuple[Path, CombinationResult]:
        result = self.combine_pages(parent_a_arg, parent_b_arg, title)
        path = self.write_draft_result(result, update_indexes=update_indexes)
        return path, result

    def write_draft_result(self, result: CombinationResult, update_indexes: bool = True) -> Path:
        parent_a, parent_b = result.parents
        path = unique_path(self.draft_dir, self.draft_filename_stem(parent_a, parent_b))
        path.write_text(self.render_draft(result), encoding="utf-8")
        if update_indexes:
            self.update_combination_index(path, result)
            self.update_main_index(path, result)
            self.append_log_event(path, result)
        return path

    def update_combination_index(self, draft_path: Path, result: CombinationResult) -> None:
        if not self.combinations_index.exists():
            return
        text = self.combinations_index.read_text(encoding="utf-8")
        link = self.wikilink_path(draft_path)
        if f"[[{link}" in text:
            return
        parent_a, parent_b = result.parents
        row = f"| [[{link}|{result.title}]] | [[{parent_a.wikilink_path}]] + [[{parent_b.wikilink_path}]] | not-submitted |"
        marker = "|---|---|---|"
        if marker in text:
            text = text.replace(marker, f"{marker}\n{row}", 1)
        else:
            text += f"\n\n## Current Draft Index\n\n| Draft | Parents | Promotion State |\n|---|---|---|\n{row}\n"
        self.combinations_index.write_text(text, encoding="utf-8")

    def update_main_index(self, draft_path: Path, result: CombinationResult) -> None:
        if not self.main_index.exists():
            return
        text = self.main_index.read_text(encoding="utf-8")
        link = self.wikilink_path(draft_path)
        should_increment = f"[[{link}" not in text
        if should_increment:
            parent_a, parent_b = result.parents
            row = f"| [[{link}|{result.title}]] | [[{parent_a.wikilink_path}]] + [[{parent_b.wikilink_path}]] | not-submitted |"
            section = "## Combination Drafts"
            if section not in text:
                insert = f"\n{section}\n\n| Draft | Parents | Promotion State |\n|---|---|---|\n{row}\n"
                anchor = "\n---\n\n## Source Summaries"
                if anchor in text:
                    text = text.replace(anchor, f"\n{insert}\n---\n\n## Source Summaries", 1)
                else:
                    text += insert
            else:
                marker = "|---|---|---|"
                start = text.index(section)
                marker_index = text.find(marker, start)
                if marker_index != -1:
                    insert_at = marker_index + len(marker)
                    text = text[:insert_at] + f"\n{row}" + text[insert_at:]
            text = self.increment_page_count(text)
        self.main_index.write_text(text, encoding="utf-8")

    def increment_page_count(self, text: str) -> str:
        def replace_status(match: re.Match[str]) -> str:
            return f"{int(match.group(1)) + 1} wiki pages created"

        text = re.sub(r"(\d+) wiki pages created", replace_status, text, count=1)

        def replace_summary(match: re.Match[str]) -> str:
            return f"{match.group(1)}{int(match.group(2)) + 1}{match.group(3)}"

        return re.sub(
            r'(summary: "Master catalog.*?31 sources, )(\d+)( pages)',
            replace_summary,
            text,
            count=1,
        )

    def append_log_event(self, draft_path: Path, result: CombinationResult) -> None:
        if not self.log.exists():
            return
        parent_a, parent_b = result.parents
        link = self.wikilink_path(draft_path)
        entry = (
            f"\n---\n\n## [{result.created_on}] COMBINE - {result.title}\n\n"
            f"- Created combination draft from [[{parent_a.wikilink_path}]] + [[{parent_b.wikilink_path}]] -> [[{link}]].\n"
            "- Canonical parent pages were not modified.\n"
        )
        with self.log.open("a", encoding="utf-8") as handle:
            handle.write(entry)

    def set_frontmatter_value(self, path: Path, key: str, value: str) -> None:
        text = path.read_text(encoding="utf-8")
        match = FRONTMATTER_RE.match(text)
        if not match:
            raise SystemExit(f"Draft has no YAML frontmatter: {path}")
        meta_lines = match.group("meta").splitlines()
        replacement = f"{key}: {value}"
        changed = False
        for index, line in enumerate(meta_lines):
            if line.startswith(f"{key}:"):
                meta_lines[index] = replacement
                changed = True
                break
        if not changed:
            meta_lines.append(replacement)
        updated = "---\n" + "\n".join(meta_lines) + "\n---\n" + text[match.end() :]
        path.write_text(updated, encoding="utf-8")

    def resolve_project_path(self, value: str) -> Path:
        path = Path(value)
        if not path.is_absolute():
            path = self.root / value
        return path.resolve()

    def default_promotion_destination(self, draft: WikiPage) -> str:
        return f"wiki/cross-niche/{draft.path.stem}.md"

    def normalize_merge_strategy(self, strategy: str | None) -> str:
        normalized = strategy or "create_new_canonical"
        if normalized not in MERGE_STRATEGIES:
            raise SystemExit(f"Unsupported merge strategy: {normalized}")
        return normalized

    def request_path_from_arg(self, request_arg: str) -> Path:
        path = self.resolve_project_path(request_arg)
        if path.exists() and path.is_file():
            try:
                path.relative_to(self.pending_dir.resolve())
            except ValueError:
                raise SystemExit("Promotion approval/rejection requires a pending review artifact.")
            return path
        candidate = self.pending_dir / request_arg
        if candidate.exists():
            return candidate.resolve()
        if not request_arg.endswith(".md"):
            candidate = self.pending_dir / f"{request_arg}.md"
            if candidate.exists():
                return candidate.resolve()
        raise SystemExit(f"Promotion request not found: {request_arg}")

    def move_unique(self, source: Path, destination_dir: Path) -> Path:
        destination = unique_path(destination_dir, source.stem)
        destination_dir.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(destination))
        return destination

    def append_log_text(self, entry: str) -> None:
        if not self.log.exists():
            return
        with self.log.open("a", encoding="utf-8") as handle:
            handle.write(entry)

    def create_promotion_request(
        self,
        draft_arg: str,
        note: str | None,
        suggested_destination: str | None = None,
        suggested_merge_strategy: str | None = None,
    ) -> Path:
        draft_path = Path(draft_arg)
        if not draft_path.is_absolute():
            draft_path = self.root / draft_arg
        if not draft_path.exists():
            raise SystemExit(f"Draft not found: {draft_arg}")
        try:
            draft_path.resolve().relative_to(self.draft_dir.resolve())
        except ValueError:
            raise SystemExit("Only drafts under wiki/combinations/drafts/ can be submitted.")
        draft = self.read_page(draft_path.resolve())
        if draft.metadata.get("origin") != "combination":
            raise SystemExit("Only combination drafts can be submitted to the promotion queue.")

        today = date.today().isoformat()
        title = f"Promote {draft.title}"
        strategy = self.normalize_merge_strategy(suggested_merge_strategy)
        destination = suggested_destination or self.default_promotion_destination(draft)
        request_path = unique_path(self.pending_dir, f"{draft.path.stem}-promotion")
        parents = [str(parent) for parent in draft.metadata.get("parents", [])]
        parent_meta_lines = "\n".join(f"  - {parent}" for parent in parents)
        parent_body_lines = "\n".join(f"- {parent}" for parent in parents)
        note_block = note or "No submitter note provided."
        request_text = f"""---
title: {json.dumps(title)}
date_created: {today}
date_modified: {today}
last_verified: {today}
summary: {json.dumps(f"Promotion review request for {draft.title}.")}
tags: {yaml_inline_list([tag for tag in draft.tags if tag in STANDARD_TAGS])}
type: output
status: review
origin: promotion-review
review_state: pending
draft_path: {draft.relative_path}
parents:
{parent_meta_lines or "  - parent-lineage-missing"}
suggested_destination: {destination}
suggested_merge_strategy: {strategy}
---

# {title}

## Draft
- Draft page: [[{draft.wikilink_path}|{draft.title}]]
- Current state: pending review.

## Parent Lineage
{parent_body_lines or "- Parent lineage missing."}

## Suggested Destination
- `{destination}`

## Suggested Merge Strategy
- `{strategy}`

## Submitter Note
- {note_block}

## Review Checklist
- Confirm the draft has useful cross-niche insight, not just word association.
- Verify factual claims against canonical pages and raw sources where needed.
- Decide whether the canonical destination should be an existing page update or a new page.
- If approved, move this request to approved tracking and update canonical pages explicitly.
"""
        request_path.write_text(request_text, encoding="utf-8")
        self.set_frontmatter_value(draft_path.resolve(), "promotion_state", "pending")
        self.append_log_text(
            f"\n---\n\n## [{today}] PROMOTION SUBMITTED - {draft.title}\n\n"
            f"- Marked [[{draft.wikilink_path}]] as pending promotion.\n"
            f"- Created review artifact [[{self.wikilink_path(request_path)}]].\n"
            f"- Suggested destination: `{destination}`.\n"
            f"- Suggested merge strategy: `{strategy}`.\n"
        )
        return request_path

    def canonicalize_draft_body(self, draft: WikiPage, canonical_title: str) -> str:
        body = draft.body
        lines = body.splitlines()
        if lines and lines[0].startswith("This is a speculative draft derived"):
            lines = lines[1:]
        cleaned = "\n".join(lines).strip()
        cleaned = cleaned.replace("speculative draft", "promoted synthesis")
        cleaned = cleaned.replace("hypothesis map, not a new canonical claim", "synthesis promoted after review")
        cleaned = cleaned.replace("not canonical", "reviewed")
        parents = draft.metadata.get("parents", [])
        lineage = "\n".join(f"- Derived from: `{parent}`" for parent in parents) or "- Derived from combination draft lineage."
        return f"# {canonical_title}\n\n{cleaned}\n\n## Promotion Lineage\n{lineage}\n- Original draft: [[{draft.wikilink_path}|{draft.title}]]\n"

    def render_new_canonical_page(self, draft: WikiPage, destination: Path) -> str:
        today = date.today().isoformat()
        canonical_title = draft.title
        tags = [tag for tag in draft.tags if tag in STANDARD_TAGS]
        if "cross-niche" not in tags:
            tags.append("cross-niche")
        return f"""---
title: {json.dumps(canonical_title)}
date_created: {today}
date_modified: {today}
last_verified: {today}
summary: {json.dumps(draft.summary.replace("Speculative combination draft", "Promoted combination synthesis"))}
tags: {yaml_inline_list(tags)}
type: synthesis
status: final
---

{self.canonicalize_draft_body(draft, canonical_title)}
"""

    def approve_promotion_request(
        self,
        request_arg: str,
        strategy: str | None = None,
        destination: str | None = None,
        note: str | None = None,
    ) -> Path:
        request_path = self.request_path_from_arg(request_arg)
        request = self.read_page(request_path)
        metadata = request.metadata
        merge_strategy = self.normalize_merge_strategy(strategy or str(metadata.get("suggested_merge_strategy") or "create_new_canonical"))
        if merge_strategy in {"reject", "keep_as_draft"}:
            return self.reject_promotion_request(request_arg, merge_strategy, note)

        draft_path = self.resolve_project_path(str(metadata.get("draft_path") or ""))
        if not draft_path.exists():
            raise SystemExit(f"Draft referenced by request does not exist: {draft_path}")
        draft = self.read_page(draft_path)
        target_value = destination or str(metadata.get("suggested_destination") or self.default_promotion_destination(draft))
        target = self.resolve_project_path(target_value)
        try:
            target.relative_to(self.wiki_root.resolve())
        except ValueError:
            raise SystemExit("Promotion destination must stay inside wiki/.")

        if merge_strategy == "create_new_canonical":
            if target.exists():
                raise SystemExit(f"Canonical destination already exists: {self.relative_to_root(target)}")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(self.render_new_canonical_page(draft, target), encoding="utf-8")
            self.update_index_for_canonical_promotion(target, draft, created=True)
        elif merge_strategy == "append_to_existing":
            if not target.exists():
                raise SystemExit(f"Append target does not exist: {self.relative_to_root(target)}")
            existing = target.read_text(encoding="utf-8").rstrip()
            addition = "\n\n---\n\n## Promoted Combination Addition\n\n" + self.canonicalize_draft_body(draft, draft.title)
            target.write_text(existing + addition + "\n", encoding="utf-8")
            self.set_frontmatter_value(target, "date_modified", date.today().isoformat())
            self.update_index_for_canonical_promotion(target, draft, created=False)

        self.set_frontmatter_value(draft_path, "promotion_state", "approved")
        self.set_frontmatter_value(request_path, "review_state", "approved")
        self.set_frontmatter_value(request_path, "suggested_merge_strategy", merge_strategy)
        approved_path = self.move_unique(request_path, self.wiki_root / "promotion-queue" / "approved")
        today = date.today().isoformat()
        self.append_log_text(
            f"\n---\n\n## [{today}] PROMOTION APPROVED - {draft.title}\n\n"
            f"- Approved [[{draft.wikilink_path}]] using `{merge_strategy}`.\n"
            f"- Canonical destination: [[{self.wikilink_path(target)}]].\n"
            f"- Review artifact moved to [[{self.wikilink_path(approved_path)}]].\n"
            f"- Note: {note or 'No reviewer note provided.'}\n"
        )
        return target

    def reject_promotion_request(self, request_arg: str, strategy: str = "reject", note: str | None = None) -> Path:
        request_path = self.request_path_from_arg(request_arg)
        request = self.read_page(request_path)
        close_strategy = self.normalize_merge_strategy(strategy)
        if close_strategy not in {"reject", "keep_as_draft"}:
            raise SystemExit("Rejection flow only supports reject or keep_as_draft.")
        draft_path = self.resolve_project_path(str(request.metadata.get("draft_path") or ""))
        draft = self.read_page(draft_path) if draft_path.exists() else None
        if draft:
            self.set_frontmatter_value(draft_path, "promotion_state", "rejected" if close_strategy == "reject" else "not-submitted")
        self.set_frontmatter_value(request_path, "review_state", "rejected")
        self.set_frontmatter_value(request_path, "suggested_merge_strategy", close_strategy)
        rejected_path = self.move_unique(request_path, self.wiki_root / "promotion-queue" / "rejected")
        today = date.today().isoformat()
        draft_link = f"[[{draft.wikilink_path}]]" if draft else "`missing draft`"
        self.append_log_text(
            f"\n---\n\n## [{today}] PROMOTION CLOSED - {request.title}\n\n"
            f"- Closed promotion review for {draft_link} using `{close_strategy}`.\n"
            f"- Review artifact moved to [[{self.wikilink_path(rejected_path)}]].\n"
            f"- Note: {note or 'No reviewer note provided.'}\n"
        )
        return rejected_path

    def update_index_for_canonical_promotion(self, target: Path, draft: WikiPage, created: bool) -> None:
        if not self.main_index.exists():
            return
        text = self.main_index.read_text(encoding="utf-8")
        link = self.wikilink_path(target)
        row = f"| [[{link}|{draft.title}]] | Promoted from [[{draft.wikilink_path}]] | Final |"
        section = "## Promoted Canonical Updates"
        if f"[[{link}" not in text:
            if section not in text:
                insert = f"\n{section}\n\n| Page | Source Draft | Status |\n|------|--------------|--------|\n{row}\n"
                anchor = "\n---\n\n## Source Summaries"
                if anchor in text:
                    text = text.replace(anchor, f"\n{insert}\n---\n\n## Source Summaries", 1)
                else:
                    text += insert
            else:
                marker = "|------|--------------|--------|"
                start = text.index(section)
                marker_index = text.find(marker, start)
                if marker_index != -1:
                    insert_at = marker_index + len(marker)
                    text = text[:insert_at] + f"\n{row}" + text[insert_at:]
        if created:
            text = self.increment_page_count(text)
        self.main_index.write_text(text, encoding="utf-8")
