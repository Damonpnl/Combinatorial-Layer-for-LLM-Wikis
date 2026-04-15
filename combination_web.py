#!/usr/bin/env python3
"""Local web UI/API for the LLM Wiki combination game."""

from __future__ import annotations

import argparse
import json
import mimetypes
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from combination_service import CombinationResult, CombinationService, PROJECT_ROOT


UI_ROOT = PROJECT_ROOT / "ui" / "combinations"


def page_to_dict(page) -> dict:
    niche = page.wikilink_path.split("/", 1)[0] if "/" in page.wikilink_path else "root"
    return {
        "title": page.title,
        "summary": page.summary,
        "path": page.relative_path,
        "wikilink": page.wikilink_path,
        "niche": niche,
        "tags": page.tags,
        "type": page.page_type,
        "status": page.status,
        "outgoingWikilinks": page.outgoing_wikilinks,
        "hasCrossNicheImplications": page.has_cross_niche_implications,
        "truthLevel": "canonical",
    }


def result_to_dict(result: CombinationResult, draft_path: Path | None = None, service: CombinationService | None = None) -> dict:
    draft_payload = {}
    if draft_path and service:
        draft_payload = {
            "draftPath": service.relative_to_root(draft_path),
            "draftWikilink": service.wikilink_path(draft_path),
        }
    return {
        "title": result.title,
        "summary": result.summary,
        "tags": result.tags,
        "parents": [page_to_dict(page) for page in result.parents],
        "relatedPages": [page_to_dict(page) for page in result.related_pages],
        "sections": result.sections,
        "createdOn": result.created_on,
        "provider": result.provider_name,
        "pairScore": result.pair_score,
        "pairScoreThreshold": result.pair_score_threshold,
        "pairScoreBlockLow": result.pair_score_blocked,
        "pairScoreWarning": result.pair_score_warning,
        "semanticGate": result.semantic_gate,
        "generationMetadata": result.generation_metadata,
        "truthLevel": "draft-preview",
        **draft_payload,
    }


class CombinationRequestHandler(BaseHTTPRequestHandler):
    service = CombinationService(PROJECT_ROOT)

    def log_message(self, format: str, *args) -> None:
        # Keep the local app quiet unless an exception reaches the console.
        return

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path in {"/", "/combinations", "/combinations/"}:
            self.serve_static("index.html")
            return
        if parsed.path in {"/craft", "/craft/"}:
            self.serve_static("canvas.html")
            return
        if parsed.path == "/api/concepts":
            self.send_json({"concepts": [page_to_dict(page) for page in self.service.discover_canonical_pages()]})
            return
        if parsed.path == "/api/health":
            self.send_json({"ok": True, "service": "combination-game"})
            return
        if parsed.path == "/file":
            self.serve_wiki_file(parse_qs(parsed.query).get("path", [""])[0])
            return
        if parsed.path.startswith("/static/"):
            self.serve_static(parsed.path.removeprefix("/static/"))
            return
        self.send_error(HTTPStatus.NOT_FOUND, "Route not found")

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        try:
            payload = self.read_json()
            if parsed.path == "/api/combine":
                draft, result = self.service.create_draft_with_result(payload.get("left", ""), payload.get("right", ""))
                self.send_json(
                    {
                        "result": result_to_dict(result, draft, self.service),
                        "path": self.service.relative_to_root(draft),
                        "wikilink": self.service.wikilink_path(draft),
                    }
                )
                return
            if parsed.path == "/api/drafts":
                draft = self.service.create_draft(payload.get("left", ""), payload.get("right", ""))
                self.send_json({"path": self.service.relative_to_root(draft), "wikilink": self.service.wikilink_path(draft)})
                return
            if parsed.path == "/api/promotions":
                request_path = self.service.create_promotion_request(
                    payload.get("draftPath", ""),
                    payload.get("note"),
                    suggested_destination=payload.get("destination"),
                    suggested_merge_strategy=payload.get("strategy"),
                )
                self.send_json({"path": self.service.relative_to_root(request_path), "wikilink": self.service.wikilink_path(request_path)})
                return
            if parsed.path == "/api/promotions/approve":
                target_path = self.service.approve_promotion_request(
                    payload.get("requestPath", ""),
                    strategy=payload.get("strategy"),
                    destination=payload.get("destination"),
                    note=payload.get("note"),
                )
                self.send_json({"path": self.service.relative_to_root(target_path), "wikilink": self.service.wikilink_path(target_path)})
                return
            if parsed.path == "/api/promotions/reject":
                request_path = self.service.reject_promotion_request(
                    payload.get("requestPath", ""),
                    strategy=payload.get("strategy", "reject"),
                    note=payload.get("note"),
                )
                self.send_json({"path": self.service.relative_to_root(request_path), "wikilink": self.service.wikilink_path(request_path)})
                return
            self.send_error(HTTPStatus.NOT_FOUND, "Route not found")
        except Exception as exc:
            self.send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)

    def read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length == 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        return json.loads(raw)

    def send_json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def serve_static(self, relative: str) -> None:
        path = (UI_ROOT / relative).resolve()
        try:
            path.relative_to(UI_ROOT.resolve())
        except ValueError:
            self.send_error(HTTPStatus.NOT_FOUND, "Static asset not found")
            return
        if not path.exists() or not path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND, "Static asset not found")
            return
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        body = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def serve_wiki_file(self, requested_path: str) -> None:
        path = (PROJECT_ROOT / requested_path).resolve()
        wiki_root = (PROJECT_ROOT / "wiki").resolve()
        try:
            path.relative_to(wiki_root)
        except ValueError:
            self.send_error(HTTPStatus.NOT_FOUND, "Wiki file not found")
            return
        if not path.exists() or not path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND, "Wiki file not found")
            return
        body = path.read_text(encoding="utf-8").encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/markdown; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Run the local Combination Lab web UI.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), CombinationRequestHandler)
    print(f"Combination Lab running at http://{args.host}:{args.port}/combinations")
    print(f"Atom Canvas running at http://{args.host}:{args.port}/craft")
    server.serve_forever()


if __name__ == "__main__":
    main()
