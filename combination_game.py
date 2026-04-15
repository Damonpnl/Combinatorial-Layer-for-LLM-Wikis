#!/usr/bin/env python3
"""Filesystem-first combination game utilities for Damon's LLM Wiki.

This script intentionally avoids databases and external packages. Canonical
wiki pages remain the source of truth; generated combinations are draft files.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from combination_service import CombinationService


ROOT = Path(__file__).resolve().parent
WIKI_ROOT = ROOT / "wiki"
DRAFT_DIR = WIKI_ROOT / "combinations" / "drafts"
PENDING_DIR = WIKI_ROOT / "promotion-queue" / "pending"

INTERNAL_DIRS = {"sources", "outputs", "combinations", "promotion-queue"}
INTERNAL_FILES = {"index.md", "log.md", "sources.md", "outputs.md"}
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

FRONTMATTER_RE = re.compile(r"\A---\s*\n(?P<meta>.*?)\n---\s*\n?", re.DOTALL)
WIKILINK_RE = re.compile(r"\[\[([^\]#|]+)(?:#[^\]|]+)?(?:\|[^\]]+)?\]\]")


@dataclass(frozen=True)
class WikiPage:
    path: Path
    wiki_path: str
    metadata: dict[str, Any]
    body: str
    wikilinks: list[str]

    @property
    def title(self) -> str:
        return str(self.metadata.get("title") or self.path.stem.replace("-", " ").title())

    @property
    def summary(self) -> str:
        return str(self.metadata.get("summary") or "No summary provided.")


def split_frontmatter(text: str) -> tuple[str, str]:
    match = FRONTMATTER_RE.match(text)
    if not match:
        return "", text
    return match.group("meta"), text[match.end() :]


def parse_value(raw: str) -> Any:
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
    parsed: dict[str, Any] = {}
    for line in meta.splitlines():
        if not line.strip() or line.lstrip().startswith("#") or ":" not in line:
            continue
        key, raw_value = line.split(":", 1)
        parsed[key.strip()] = parse_value(raw_value)
    return parsed


def read_page(path: Path) -> WikiPage:
    text = path.read_text(encoding="utf-8")
    meta_text, body = split_frontmatter(text)
    metadata = parse_frontmatter(meta_text)
    return WikiPage(
        path=path,
        wiki_path=to_wiki_path(path),
        metadata=metadata,
        body=body,
        wikilinks=sorted(set(WIKILINK_RE.findall(body))),
    )


def to_wiki_path(path: Path) -> str:
    return path.resolve().relative_to(WIKI_ROOT.resolve()).with_suffix("").as_posix()


def is_canonical_page(path: Path) -> bool:
    try:
        relative = path.resolve().relative_to(WIKI_ROOT.resolve())
    except ValueError:
        return False
    if path.suffix.lower() != ".md":
        return False
    if relative.name in INTERNAL_FILES:
        return False
    if relative.parts and relative.parts[0] in INTERNAL_DIRS:
        return False
    return True


def enumerate_canonical_pages() -> list[WikiPage]:
    pages = []
    for path in sorted(WIKI_ROOT.rglob("*.md")):
        if is_canonical_page(path):
            pages.append(read_page(path))
    return pages


def strip_wikilink_syntax(value: str) -> str:
    stripped = value.strip()
    if stripped.startswith("[[") and stripped.endswith("]]"):
        stripped = stripped[2:-2].split("|", 1)[0].split("#", 1)[0]
    return stripped


def resolve_page_arg(value: str) -> Path:
    normalized = strip_wikilink_syntax(value).replace("\\", "/").strip("/")
    candidates = []
    raw = Path(normalized)
    if raw.is_absolute():
        candidates.append(raw)
    else:
        if normalized.startswith("wiki/"):
            candidates.append(ROOT / normalized)
        candidates.append(WIKI_ROOT / normalized)
        if not normalized.endswith(".md"):
            if normalized.startswith("wiki/"):
                candidates.append(ROOT / f"{normalized}.md")
            candidates.append(WIKI_ROOT / f"{normalized}.md")
    for candidate in candidates:
        if candidate.exists() and candidate.is_file() and is_canonical_page(candidate):
            return candidate.resolve()
    raise SystemExit(f"Canonical wiki page not found or not allowed: {value}")


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "combination-draft"


def unique_path(directory: Path, stem: str, suffix: str = ".md") -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    candidate = directory / f"{stem}{suffix}"
    counter = 2
    while candidate.exists():
        candidate = directory / f"{stem}-{counter}{suffix}"
        counter += 1
    return candidate


def yaml_list(values: list[str]) -> str:
    return "[" + ", ".join(json.dumps(value) for value in values) + "]"


def combined_tags(parent_a: WikiPage, parent_b: WikiPage) -> list[str]:
    tags: list[str] = []
    for parent in (parent_a, parent_b):
        for tag in parent.metadata.get("tags", []):
            if tag in STANDARD_TAGS and tag not in tags:
                tags.append(tag)
    if "cross-niche" not in tags:
        tags.append("cross-niche")
    return tags


def related_links(parent_a: WikiPage, parent_b: WikiPage) -> list[str]:
    seen = {parent_a.wiki_path, parent_b.wiki_path}
    links: list[str] = []
    for link in parent_a.wikilinks + parent_b.wikilinks:
        normalized = link.strip()
        candidate = WIKI_ROOT / f"{normalized}.md"
        if (
            normalized
            and normalized not in seen
            and normalized not in links
            and candidate.exists()
            and is_canonical_page(candidate)
        ):
            links.append(normalized)
    return links[:12]


def generate_draft(parent_a: WikiPage, parent_b: WikiPage, title: str | None = None) -> str:
    today = date.today().isoformat()
    draft_title = title or f"{parent_a.title} x {parent_b.title}"
    tags = combined_tags(parent_a, parent_b)
    parents = [f"[[{parent_a.wiki_path}]]", f"[[{parent_b.wiki_path}]]"]
    related = related_links(parent_a, parent_b)
    related_lines = "\n".join(f"- [[{link}]]" for link in related) or "- No shared related links detected yet."
    tag_lines = "\n".join(f"- {tag}" for tag in tags)
    summary = (
        f"Speculative combination draft pairing {parent_a.title} with {parent_b.title}; "
        "not canonical until explicitly promoted."
    )

    return f"""---
title: {json.dumps(draft_title)}
date_created: {today}
date_modified: {today}
last_verified: {today}
summary: {json.dumps(summary)}
tags: {yaml_list(tags)}
type: synthesis
status: draft
origin: combination
parents: {yaml_list(parents)}
promotion_state: not-submitted
combination_mode: canonical-canonical
---

# {draft_title}

## Lineage
- Parent A: [[{parent_a.wiki_path}|{parent_a.title}]]
- Parent B: [[{parent_b.wiki_path}|{parent_b.title}]]
- Status: speculative draft; do not treat as canonical until promoted.
- Promotion state: not-submitted.

## Parent Summaries
- **{parent_a.title}:** {parent_a.summary}
- **{parent_b.title}:** {parent_b.summary}

## Fusion Summary
- This combination asks what becomes possible when the logic of [[{parent_a.wiki_path}|{parent_a.title}]] is applied to [[{parent_b.wiki_path}|{parent_b.title}]].
- The synthesis should be evaluated as a hypothesis generator, not as a factual claim about either parent page.
- The strongest use case is identifying founder-relevant leverage points, product wedges, research questions, or cross-niche strategy.

## Product Opportunity
- Build around the overlap where the first parent supplies a mechanism and the second parent supplies a market, workflow, constraint, or user behavior.
- Look for a narrow wedge that can be tested without rewriting the canonical wiki or assuming the fusion is already true.
- Prefer opportunities that create a measurable behavior change, capital efficiency gain, narrative advantage, or decision-support loop.

## System Design
- Ingredient layer: canonical pages remain fixed inputs and preserve source lineage.
- Synthesis layer: this draft explores speculative connections, abstractions, and use cases.
- Review layer: promotion requires an explicit request in [[promotion-queue/index|Promotion Queue]] before any canonical page is modified.

## Research Question
- What non-obvious advantage appears if the core mechanism of [[{parent_a.wiki_path}|{parent_a.title}]] becomes a design constraint for [[{parent_b.wiki_path}|{parent_b.title}]]?
- Which claims would need source support before this draft could graduate into canonical knowledge?
- What would falsify the fusion quickly?

## Cross-Niche Implications
{tag_lines}

## Failure Modes
- False analogy: the two pages may share vocabulary without sharing mechanism.
- Overextension: speculative combinations can create impressive-sounding but weakly grounded claims.
- Canonical contamination: this draft must not backlink from parent pages unless it is reviewed and promoted.
- Staleness: if either parent page is time-sensitive, verify it before using the draft operationally.

## Related Canonical Pages
{related_lines}
"""


def create_draft(parent_a_arg: str, parent_b_arg: str, title: str | None) -> Path:
    parent_a = read_page(resolve_page_arg(parent_a_arg))
    parent_b = read_page(resolve_page_arg(parent_b_arg))
    draft_title = title or f"{parent_a.title} x {parent_b.title}"
    path = unique_path(DRAFT_DIR, slugify(draft_title))
    path.write_text(generate_draft(parent_a, parent_b, title), encoding="utf-8")
    return path


def set_frontmatter_value(path: Path, key: str, value: str) -> None:
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


def create_promotion_request(draft_arg: str, note: str | None) -> Path:
    draft_path = Path(draft_arg)
    if not draft_path.is_absolute():
        draft_path = ROOT / draft_arg
    if not draft_path.exists():
        raise SystemExit(f"Draft not found: {draft_arg}")
    draft = read_page(draft_path.resolve())
    if draft.metadata.get("origin") != "combination":
        raise SystemExit("Only combination drafts can be submitted to the promotion queue.")

    today = date.today().isoformat()
    draft_link = f"[[{draft.wiki_path}]]"
    parents = draft.metadata.get("parents", [])
    parent_lines = "\n".join(f"- {parent}" for parent in parents) or "- Parent lineage missing."
    note_block = note or "No submitter note provided."
    title = f"Promote {draft.title}"
    request_path = unique_path(PENDING_DIR, f"{draft.path.stem}-promotion")
    request_text = f"""---
title: {json.dumps(title)}
date_created: {today}
date_modified: {today}
last_verified: {today}
summary: {json.dumps(f"Promotion review request for {draft.title}.")}
tags: {yaml_list([tag for tag in draft.metadata.get("tags", []) if tag in STANDARD_TAGS])}
type: output
status: review
---

# {title}

## Draft
- Draft page: {draft_link}
- Current state: pending review.

## Parent Lineage
{parent_lines}

## Submitter Note
- {note_block}

## Review Checklist
- Confirm the draft has useful cross-niche insight, not just word association.
- Verify factual claims against canonical pages and raw sources where needed.
- Decide whether the canonical destination should be an existing page update or a new page.
- If approved, move this request to [[promotion-queue/index|Promotion Queue]] approved tracking and update canonical pages explicitly.
"""
    request_path.write_text(request_text, encoding="utf-8")
    set_frontmatter_value(draft_path.resolve(), "promotion_state", "pending")
    return request_path


def command_list(args: argparse.Namespace) -> None:
    pages = CombinationService(ROOT).discover_canonical_pages()
    rows = [
        {
            "path": page.relative_path,
            "wikilink": page.wikilink_path,
            "title": page.title,
            "type": page.page_type,
            "status": page.status,
            "summary": page.summary,
            "tags": page.tags,
            "outgoing_wikilinks": page.outgoing_wikilinks,
            "has_cross_niche_implications": page.has_cross_niche_implications,
        }
        for page in pages
    ]
    if args.json:
        print(json.dumps(rows, indent=2))
        return
    for row in rows:
        print(f"{row['wikilink']} | {row['title']} | {row['type']} | {row['status']} | {row['summary']}")


def command_links(args: argparse.Namespace) -> None:
    page = CombinationService(ROOT).resolve_canonical_page(args.page)
    if args.json:
        print(json.dumps({"page": page.wikilink_path, "wikilinks": page.outgoing_wikilinks}, indent=2))
        return
    for link in page.outgoing_wikilinks:
        print(link)


def command_combine(args: argparse.Namespace) -> None:
    result = CombinationService(ROOT).combine_pages(args.parent_a, args.parent_b, args.title)
    if args.json:
        print(
            json.dumps(
                {
                    "title": result.title,
                    "summary": result.summary,
                    "tags": result.tags,
                    "parents": [page.relative_path for page in result.parents],
                    "related_pages": [page.relative_path for page in result.related_pages],
                    "sections": result.sections,
                    "provider": result.provider_name,
                    "pair_score": result.pair_score,
                    "pair_score_threshold": result.pair_score_threshold,
                    "pair_score_block_low": result.pair_score_blocked,
                    "pair_score_warning": result.pair_score_warning,
                    "semantic_gate": result.semantic_gate,
                    "generation_metadata": result.generation_metadata,
                    "output": result.output,
                    "prompt": result.prompt,
                },
                indent=2,
            )
        )
        return
    for name, body in result.sections.items():
        print(f"# {name}\n{body}\n")


def command_draft(args: argparse.Namespace) -> None:
    path = CombinationService(ROOT).create_draft(args.parent_a, args.parent_b, args.title)
    print(path.relative_to(ROOT).as_posix())


def command_submit(args: argparse.Namespace) -> None:
    path = CombinationService(ROOT).create_promotion_request(
        args.draft,
        args.note,
        suggested_destination=args.destination,
        suggested_merge_strategy=args.strategy,
    )
    print(path.relative_to(ROOT).as_posix())


def command_approve(args: argparse.Namespace) -> None:
    path = CombinationService(ROOT).approve_promotion_request(
        args.request,
        strategy=args.strategy,
        destination=args.destination,
        note=args.note,
    )
    print(path.relative_to(ROOT).as_posix())


def command_reject(args: argparse.Namespace) -> None:
    path = CombinationService(ROOT).reject_promotion_request(args.request, strategy=args.strategy, note=args.note)
    print(path.relative_to(ROOT).as_posix())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Combination draft utilities for Damon's LLM Wiki.")
    subcommands = parser.add_subparsers(dest="command", required=True)

    list_parser = subcommands.add_parser("list", help="Enumerate canonical wiki pages.")
    list_parser.add_argument("--json", action="store_true", help="Emit JSON instead of pipe-delimited text.")
    list_parser.set_defaults(func=command_list)

    links_parser = subcommands.add_parser("links", help="Read wikilinks from one canonical page.")
    links_parser.add_argument("page", help="Canonical page path, e.g. ai/agentic-ai or [[ai/agentic-ai]].")
    links_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    links_parser.set_defaults(func=command_links)

    combine_parser = subcommands.add_parser("combine", help="Generate a structured result without writing a file.")
    combine_parser.add_argument("parent_a", help="First canonical page.")
    combine_parser.add_argument("parent_b", help="Second canonical page.")
    combine_parser.add_argument("--title", help="Optional result title.")
    combine_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    combine_parser.set_defaults(func=command_combine)

    draft_parser = subcommands.add_parser("draft", help="Generate a speculative combination draft.")
    draft_parser.add_argument("parent_a", help="First canonical page.")
    draft_parser.add_argument("parent_b", help="Second canonical page.")
    draft_parser.add_argument("--title", help="Optional draft title.")
    draft_parser.set_defaults(func=command_draft)

    submit_parser = subcommands.add_parser("submit", help="Submit a draft to the pending promotion queue.")
    submit_parser.add_argument("draft", help="Draft path, e.g. wiki/combinations/drafts/example.md.")
    submit_parser.add_argument("--note", help="Short reviewer note.")
    submit_parser.add_argument("--destination", help="Suggested canonical destination, e.g. wiki/cross-niche/example.md.")
    submit_parser.add_argument(
        "--strategy",
        choices=["create_new_canonical", "append_to_existing", "keep_as_draft", "reject"],
        default="create_new_canonical",
        help="Suggested merge strategy.",
    )
    submit_parser.set_defaults(func=command_submit)

    approve_parser = subcommands.add_parser("approve", help="Approve a pending promotion request.")
    approve_parser.add_argument("request", help="Pending promotion request path or filename.")
    approve_parser.add_argument(
        "--strategy",
        choices=["create_new_canonical", "append_to_existing"],
        default=None,
        help="Canonical merge strategy. Defaults to the request suggestion.",
    )
    approve_parser.add_argument("--destination", help="Canonical target path.")
    approve_parser.add_argument("--note", help="Reviewer note.")
    approve_parser.set_defaults(func=command_approve)

    reject_parser = subcommands.add_parser("reject", help="Reject or keep a pending promotion request as draft.")
    reject_parser.add_argument("request", help="Pending promotion request path or filename.")
    reject_parser.add_argument(
        "--strategy",
        choices=["reject", "keep_as_draft"],
        default="reject",
        help="Close strategy.",
    )
    reject_parser.add_argument("--note", help="Reviewer note.")
    reject_parser.set_defaults(func=command_reject)

    return parser


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
