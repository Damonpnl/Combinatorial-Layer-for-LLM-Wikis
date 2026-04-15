"""Setup checks for the local LLM Wiki combination command."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, TypedDict

from combination_providers import (
    ProviderSetupError,
    command_executable,
    command_is_available,
    load_config,
    select_provider_config,
)


class DoctorCheck(TypedDict):
    name: str
    status: str
    detail: str
    next_step: str


def make_check(name: str, status: str, detail: str, next_step: str = "") -> DoctorCheck:
    return {"name": name, "status": status, "detail": detail, "next_step": next_step}


def writable_path(path: Path) -> bool:
    if path.exists():
        target = path if path.is_dir() else path.parent
    else:
        target = path.parent
        while not target.exists() and target != target.parent:
            target = target.parent
    return target.exists() and os.access(target, os.W_OK)


def check_provider(root: Path, config_path: Path | None, provider_type: str | None) -> list[DoctorCheck]:
    checks: list[DoctorCheck] = []
    try:
        provider_config, source = select_provider_config(root, config_path, provider_type)
    except (ProviderSetupError, ValueError) as exc:
        return [
            make_check(
                "provider",
                "fail",
                str(exc),
                "Copy combine.config.example.json to combine.config.json, set an API key, install cursor-agent, or pass --provider local-model.",
            )
        ]

    selected_type = str(provider_config.get("type", ""))
    checks.append(make_check("provider selected", "pass", f"{selected_type} ({source})"))
    if selected_type == "external-command":
        command = provider_config.get("command")
        executable = command_executable(command) or str(command)
        if command_is_available(command, root):
            checks.append(make_check("external command", "pass", f"found {executable}"))
        else:
            checks.append(
                make_check(
                    "external command",
                    "fail",
                    f"could not find {executable}",
                    "Install the command, fix combine_provider.command, or use --provider openai/local-model.",
                )
            )
    elif selected_type == "openai":
        env_name = str(provider_config.get("api_key_env", "OPENAI_API_KEY"))
        if provider_config.get("api_key") or os.getenv(env_name):
            checks.append(make_check("openai api key", "pass", f"{env_name} is available"))
        else:
            checks.append(make_check("openai api key", "fail", f"{env_name} is not set", f"Set {env_name} or configure combine_provider.api_key."))
    elif selected_type == "anthropic":
        env_name = str(provider_config.get("api_key_env", "ANTHROPIC_API_KEY"))
        if provider_config.get("api_key") or os.getenv(env_name):
            checks.append(make_check("anthropic api key", "pass", f"{env_name} is available"))
        else:
            checks.append(make_check("anthropic api key", "fail", f"{env_name} is not set", f"Set {env_name} or configure combine_provider.api_key."))
    elif selected_type == "local-model":
        endpoint = provider_config.get("endpoint")
        if endpoint:
            checks.append(make_check("local model endpoint", "pass", str(endpoint)))
        else:
            checks.append(make_check("local model endpoint", "warn", "using deterministic dry-run provider", "Configure endpoint for real synthesis output."))
    else:
        checks.append(make_check("provider type", "fail", f"unsupported provider type: {selected_type}"))
    return checks


def doctor_check(root: str | Path, config_path: str | Path | None = None, provider_type: str | None = None) -> dict[str, Any]:
    root_path = Path(root).resolve()
    config = Path(config_path).resolve() if config_path else None
    wiki_root = root_path / "wiki"
    checks: list[DoctorCheck] = []

    code_root = Path(__file__).resolve().parent
    for filename in ["combination_service.py", "combination_providers.py", "wiki_combine.py"]:
        path = code_root / filename
        checks.append(
            make_check(
                f"code file {filename}",
                "pass" if path.exists() else "fail",
                str(path),
                "Run doctor from a complete clone or reinstall the package." if not path.exists() else "",
            )
        )

    checks.append(
        make_check(
            "project root",
            "pass" if root_path.exists() else "fail",
            str(root_path),
            "Pass --root PATH pointing at the wiki project root." if not root_path.exists() else "",
        )
    )
    checks.append(
        make_check(
            "wiki folder",
            "pass" if wiki_root.is_dir() else "fail",
            str(wiki_root),
            "Create wiki/ or pass --root to an existing LLM Wiki project." if not wiki_root.is_dir() else "",
        )
    )

    required_paths = [
        (wiki_root / "combinations", "folder"),
        (wiki_root / "combinations" / "drafts", "folder"),
        (wiki_root / "combinations" / "index.md", "file"),
        (wiki_root / "index.md", "file"),
        (wiki_root / "log.md", "file"),
    ]
    for path, kind in required_paths:
        exists = path.is_dir() if kind == "folder" else path.is_file()
        checks.append(
            make_check(
                f"{path.relative_to(root_path) if path.is_relative_to(root_path) else path.name}",
                "pass" if exists else "fail",
                str(path),
                f"Create {path.relative_to(root_path).as_posix()} before running a production combine." if not exists else "",
            )
        )

    output_paths = [
        wiki_root / "combinations" / "drafts",
        wiki_root / "combinations" / "index.md",
        wiki_root / "index.md",
        wiki_root / "log.md",
    ]
    for path in output_paths:
        checks.append(
            make_check(
                f"writable {path.name if path.is_file() else path.relative_to(root_path).as_posix()}",
                "pass" if writable_path(path) else "fail",
                str(path),
                "Check filesystem permissions for the wiki output paths." if not writable_path(path) else "",
            )
        )

    if config:
        try:
            load_config(root_path, config)
            checks.append(make_check("config file", "pass", str(config)))
        except ValueError as exc:
            checks.append(make_check("config file", "fail", str(exc), "Fix JSON syntax or pass a different --config path."))
    elif (root_path / "combine.config.json").exists():
        try:
            load_config(root_path)
            checks.append(make_check("config file", "pass", str(root_path / "combine.config.json")))
        except ValueError as exc:
            checks.append(make_check("config file", "fail", str(exc), "Fix combine.config.json syntax."))
    else:
        checks.append(make_check("config file", "warn", "combine.config.json not found", "Auto-detection will be used; copy combine.config.example.json for explicit setup."))

    checks.extend(check_provider(root_path, config, provider_type))
    failed = [check for check in checks if check["status"] == "fail"]
    warned = [check for check in checks if check["status"] == "warn"]
    status = "failed" if failed else "warning" if warned else "ok"
    return {
        "status": status,
        "root": str(root_path),
        "checks": checks,
        "failures": failed,
        "warnings": warned,
    }
