"""Thin local-agent wrappers around the shared combination service."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from combination_doctor import doctor_check as run_doctor_check
from combination_service import CombinationService, PROJECT_ROOT


def service_for(root: str | Path | None = None, provider_type: str | None = None) -> CombinationService:
    return CombinationService(Path(root) if root else PROJECT_ROOT, provider_type=provider_type)


def list_canonical_pages(root: str | Path | None = None) -> list[dict[str, Any]]:
    service = service_for(root)
    return [
        {
            "path": page.relative_path,
            "wikilink": page.wikilink_path,
            "title": page.title,
            "summary": page.summary,
            "tags": page.tags,
            "type": page.page_type,
            "status": page.status,
        }
        for page in service.discover_canonical_pages()
    ]


def combine_pages(
    parent_a: str,
    parent_b: str,
    root: str | Path | None = None,
    provider_type: str | None = None,
    title: str | None = None,
) -> dict[str, Any]:
    service = service_for(root, provider_type=provider_type)
    draft_path, result = service.create_draft_with_result(parent_a, parent_b, title)
    return {
        "status": "created",
        "draft_path": service.relative_to_root(draft_path),
        "draft_wikilink": service.wikilink_path(draft_path),
        "title": result.title,
        "summary": result.summary,
        "semantic_gate": result.semantic_gate,
        "generation_metadata": result.generation_metadata,
    }


def submit_promotion(
    draft_path: str,
    note: str | None = None,
    root: str | Path | None = None,
    destination: str | None = None,
    strategy: str | None = None,
) -> dict[str, str]:
    service = service_for(root)
    request_path = service.create_promotion_request(
        draft_path,
        note,
        suggested_destination=destination,
        suggested_merge_strategy=strategy,
    )
    return {
        "status": "pending",
        "request_path": service.relative_to_root(request_path),
        "request_wikilink": service.wikilink_path(request_path),
    }


def doctor_check(
    root: str | Path | None = None,
    provider_type: str | None = None,
    config_path: str | Path | None = None,
) -> dict[str, Any]:
    return run_doctor_check(
        Path(root) if root else PROJECT_ROOT,
        Path(config_path) if config_path else None,
        provider_type,
    )
