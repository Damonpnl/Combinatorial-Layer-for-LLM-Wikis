"""Primary CLI for the local markdown LLM Wiki combination system."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from combination_doctor import doctor_check
from combination_providers import PROVIDER_TYPES, ProviderSetupError
from combination_service import CombinationService, PROJECT_ROOT


def default_root() -> Path:
    cwd = Path.cwd()
    if (cwd / "wiki").exists():
        return cwd
    return PROJECT_ROOT


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Combine two canonical markdown wiki pages into a speculative draft."
    )
    parser.add_argument("parent_a", nargs="?", help="First canonical wiki page, e.g. ai/agentic-ai or wiki/ai/agentic-ai.md.")
    parser.add_argument("parent_b", nargs="?", help="Second canonical wiki page, e.g. startups/business-model-design.")
    parser.add_argument("--title", help="Optional draft title override.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    parser.add_argument("--config", help="Path to combine.config.json.")
    parser.add_argument("--root", help="Wiki project root. Defaults to the current directory when it contains wiki/.")
    parser.add_argument(
        "--provider",
        choices=sorted(PROVIDER_TYPES),
        help="Override combine_provider.type from config or auto-detection.",
    )
    parser.add_argument(
        "--doctor",
        "--check",
        action="store_true",
        help="Check wiki folders, output paths, and provider setup without generating a draft.",
    )
    return parser


def result_payload(service: CombinationService, draft_path: Path, result: Any) -> dict[str, Any]:
    return {
        "status": "created",
        "draft_path": service.relative_to_root(draft_path),
        "draft_wikilink": service.wikilink_path(draft_path),
        "title": result.title,
        "summary": result.summary,
        "provider": result.provider_name,
        "pair_score": result.pair_score,
        "pair_score_threshold": result.pair_score_threshold,
        "pair_score_block_low": result.pair_score_blocked,
        "pair_score_warning": result.pair_score_warning,
        "semantic_gate": result.semantic_gate,
        "generation_metadata": result.generation_metadata,
        "parents": [page.relative_path for page in result.parents],
        "related_pages": [page.relative_path for page in result.related_pages],
    }


def blocked_payload(message: str) -> dict[str, Any]:
    reasons = [part.strip() for part in message.split(":", 1)[-1].split(";") if part.strip()]
    if not reasons:
        reasons = [message]
    lowered = message.lower()
    status = "blocked"
    if "semantic gate rejected" in lowered or "rejected" in lowered:
        status = "rejected"
    elif "revision" in lowered:
        status = "needs_revision"
    elif "canonical wiki page not found" in lowered or "not allowed" in lowered:
        status = "invalid_page"
    elif "provider output" in lowered or "invalid json" in lowered:
        status = "validation_failed"
    return {"status": status, "error": message, "reasons": reasons}


def setup_error_payload(message: str) -> dict[str, Any]:
    return {
        "status": "setup_failed",
        "error": message,
        "reasons": [message],
        "next_steps": [
            "Run wiki-combine --doctor to inspect setup.",
            "Copy combine.config.example.json to combine.config.json and set a provider.",
            "Use --provider local-model for a deterministic dry run.",
        ],
    }


def exception_payload(exc: Exception) -> dict[str, Any]:
    message = str(exc) or exc.__class__.__name__
    payload: dict[str, Any] = {"status": "failed", "error": message, "reasons": [message]}
    if isinstance(exc, PermissionError):
        payload["next_steps"] = ["Check write permissions for wiki/combinations/drafts, wiki/index.md, and wiki/log.md."]
    elif isinstance(exc, ValueError) and "Provider output" in message:
        payload["status"] = "validation_failed"
        payload["next_steps"] = ["Inspect the provider response and ensure it returns strict CombineOutput JSON."]
    else:
        payload["next_steps"] = ["Run wiki-combine --doctor for setup diagnostics."]
    return payload


def print_human(payload: dict[str, Any]) -> None:
    status = payload.get("status")
    if status == "created":
        print("status: created")
        print(f"draft_path: {payload['draft_path']}")
        print(f"title: {payload['title']}")
        print(f"provider: {payload['provider']}")
        print(f"semantic_gate: {payload['semantic_gate']['status']}")
        warning = payload.get("pair_score_warning")
        if warning:
            print(f"pair_score_warning: {warning}")
        print("next: review the draft before promotion; canonical pages were not modified.")
        return
    print(f"status: {status}")
    print(f"error: {payload.get('error', 'unknown error')}")
    for reason in payload.get("reasons", []):
        print(f"reason: {reason}")
    for next_step in payload.get("next_steps", []):
        print(f"next: {next_step}")


def print_doctor_human(payload: dict[str, Any]) -> None:
    print(f"doctor_status: {payload['status']}")
    print(f"root: {payload['root']}")
    for check in payload["checks"]:
        print(f"[{check['status']}] {check['name']}: {check['detail']}")
        if check.get("next_step"):
            print(f"  next: {check['next_step']}")


def emit(payload: dict[str, Any], as_json: bool, doctor: bool = False) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    elif doctor:
        print_doctor_human(payload)
    else:
        print_human(payload)


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    parser = build_parser()
    args = parser.parse_args(argv)
    root = Path(args.root) if args.root else default_root()
    config_path = Path(args.config) if args.config else None

    if args.doctor:
        payload = doctor_check(root, config_path, args.provider)
        emit(payload, args.json, doctor=True)
        return 1 if payload["status"] == "failed" else 0

    if not args.parent_a or not args.parent_b:
        parser.error("parent_a and parent_b are required unless --doctor is used.")

    try:
        service = CombinationService(root, config_path=config_path, provider_type=args.provider)
        draft_path, result = service.create_draft_with_result(args.parent_a, args.parent_b, args.title)
        payload = result_payload(service, draft_path, result)
    except ProviderSetupError as exc:
        payload = setup_error_payload(str(exc))
        emit(payload, args.json)
        return 2
    except SystemExit as exc:
        if isinstance(exc.code, int):
            raise
        payload = blocked_payload(str(exc.code))
        emit(payload, args.json)
        return 2
    except Exception as exc:
        payload = exception_payload(exc)
        emit(payload, args.json)
        return 1
    emit(payload, args.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
