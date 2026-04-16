#!/usr/bin/env python3
"""Cursor Agent CLI adapter for the LLM Wiki combine provider.

The combination service expects providers to read CombineInput JSON from stdin
and write CombineOutput JSON to stdout. The headless ``cursor-agent`` CLI's
print mode returns its own result envelope, so this adapter translates between
the two contracts.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from combination_providers import extract_json_object, provider_prompt, validate_output


def windows_path_to_wsl(path: Path) -> str:
    resolved = path.resolve()
    drive = resolved.drive.rstrip(":").lower()
    if drive:
        parts = resolved.parts[1:]
        return "/mnt/" + drive + "/" + "/".join(parts)
    return resolved.as_posix()


def build_cursor_command() -> list[str]:
    requested_binary = os.getenv("CURSOR_AGENT_BIN", "cursor-agent")
    binary = shutil.which(requested_binary)
    workspace = os.getenv("CURSOR_AGENT_WORKSPACE", str(Path.cwd()))
    wsl_distro = os.getenv("CURSOR_AGENT_WSL_DISTRO", "Ubuntu")
    if not binary and shutil.which("wsl"):
        binary = os.getenv("CURSOR_AGENT_WSL_BIN", "cursor-agent")
        workspace = windows_path_to_wsl(Path(workspace))
        command = ["wsl", "-d", wsl_distro, "--", binary]
    elif binary:
        command = [binary]
    else:
        raise SystemExit(
            "Cursor Agent CLI was not found. Install the headless Cursor CLI so "
            "`cursor-agent --version` works, or set CURSOR_AGENT_BIN to its full path. "
            "The `cursor` editor command is not enough for non-interactive JSON synthesis."
        )
    subcommand = os.getenv("CURSOR_AGENT_SUBCOMMAND", "")
    model = os.getenv("CURSOR_AGENT_MODEL")
    if subcommand:
        command.append(subcommand)
    command.extend(["-p", "--output-format", "json", "--mode", "ask", "--trust", "--workspace", workspace])
    if model:
        command.extend(["--model", model])
    return command


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

    combine_input = json.load(sys.stdin)
    prompt = (
        provider_prompt(combine_input)
        + "\n\nImportant: Do not edit files, run shell commands, or mutate the repository. "
        "Only return the strict CombineOutput JSON object."
    )
    completed = subprocess.run(
        build_cursor_command(),
        input=prompt,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=int(os.getenv("CURSOR_AGENT_TIMEOUT_SECONDS", "240")),
    )
    if completed.returncode != 0:
        sys.stderr.write(completed.stderr.strip() or "Cursor Agent failed without stderr.")
        raise SystemExit(completed.returncode)

    cursor_payload = extract_json_object(completed.stdout)
    if isinstance(cursor_payload, dict) and "result" in cursor_payload:
        model_text = str(cursor_payload["result"])
    else:
        model_text = completed.stdout
    output = validate_output(extract_json_object(model_text))
    print(json.dumps(output, ensure_ascii=False))


if __name__ == "__main__":
    main()
