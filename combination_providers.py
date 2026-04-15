"""Pluggable synthesis providers for the LLM Wiki combination game.

Providers own only the speculative synthesis step. Filesystem writes,
wikilink safety, index updates, and promotion state remain in
``combination_service.py``.
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Protocol, TypedDict


PROMPT_VERSION = "combine-prompt-v4"


class CanonicalPageInput(TypedDict, total=False):
    path: str
    title: str
    summary: str
    tags: list[str]
    type: str
    status: str
    mechanisms: list[str]
    incentives: list[str]
    actors: list[str]
    risks: list[str]
    linked_concepts: list[str]
    cross_niche_implications: list[str]
    core_mechanism: str
    control_variable: str
    primary_bottleneck: str
    dominant_failure_mode: str
    highest_leverage_use_case: str
    certainty_level: str
    body_text: str


class CombineInput(TypedDict):
    parent_a: CanonicalPageInput
    parent_b: CanonicalPageInput


class CombineOutput(TypedDict):
    draft_title: str
    draft_summary: str
    fusion_summary: str
    mechanistic_interaction: str
    product_opportunity: str
    system_design: str
    research_question: str
    falsification_test: str
    cross_niche_implications: list[str]
    failure_modes: list[str]
    related_canonical_pages: list[str]
    tags: list[str]
    non_obviousness_reason: str
    primary_bottleneck: str
    specific_user_or_buyer: str
    novelty_score: float
    plausibility_score: float
    promotion_readiness: str
    interaction_type: str
    grounded_points: list[str]
    speculative_extensions: list[str]
    evidence_needed_before_promotion: list[str]


class CombineProvider(Protocol):
    name: str

    def synthesize(self, input_data: CombineInput) -> CombineOutput:
        """Return validated structured synthesis JSON."""


REQUIRED_STRING_FIELDS = {
    "draft_title",
    "draft_summary",
    "fusion_summary",
    "mechanistic_interaction",
    "product_opportunity",
    "system_design",
    "research_question",
    "falsification_test",
    "non_obviousness_reason",
    "primary_bottleneck",
    "specific_user_or_buyer",
}
REQUIRED_LIST_FIELDS = {
    "cross_niche_implications",
    "failure_modes",
    "related_canonical_pages",
    "tags",
    "grounded_points",
    "speculative_extensions",
    "evidence_needed_before_promotion",
}
REQUIRED_SCORE_FIELDS = {
    "novelty_score",
    "plausibility_score",
}
INTERACTION_TYPES = {"mechanistic", "analogical", "strategic", "market_structural", "epistemic"}
PROMOTION_READINESS_LEVELS = {"low", "medium", "high"}
PROVIDER_TYPES = {"external-command", "openai", "anthropic", "local-model"}


class ProviderSetupError(RuntimeError):
    """Raised when no safe synthesis provider can be selected."""


def command_executable(command: str | list[str] | None) -> str | None:
    if not command:
        return None
    if isinstance(command, list):
        return str(command[0]) if command else None
    try:
        parts = shlex.split(command, posix=os.name != "nt")
    except ValueError:
        parts = command.split()
    return parts[0] if parts else None


def command_is_available(command: str | list[str] | None, root: Path | None = None) -> bool:
    executable = command_executable(command)
    if not executable:
        return False
    candidate = Path(executable)
    if candidate.is_absolute() and candidate.exists():
        return True
    if root:
        rooted = root / executable
        if rooted.exists():
            return True
    return shutil.which(executable) is not None


def cursor_agent_is_available() -> bool:
    requested_binary = os.getenv("CURSOR_AGENT_BIN", "cursor-agent")
    return shutil.which(requested_binary) is not None or shutil.which("wsl") is not None


def autodetect_provider_config(root: Path) -> tuple[dict[str, Any], str]:
    adapter = Path(__file__).resolve().parent / "cursor_combine_provider.py"
    if adapter.exists() and cursor_agent_is_available():
        return (
            {
                "type": "external-command",
                "command": [sys.executable, str(adapter)],
                "timeout_seconds": 300,
            },
            "detected Cursor Agent compatible external-command provider",
        )
    if os.getenv("OPENAI_API_KEY"):
        return (
            {
                "type": "openai",
                "model": "gpt-4.1-mini",
                "api_key_env": "OPENAI_API_KEY",
                "timeout_seconds": 180,
            },
            "detected OPENAI_API_KEY",
        )
    if os.getenv("ANTHROPIC_API_KEY"):
        return (
            {
                "type": "anthropic",
                "model": "claude-3-5-sonnet-latest",
                "api_key_env": "ANTHROPIC_API_KEY",
                "timeout_seconds": 180,
            },
            "detected ANTHROPIC_API_KEY",
        )
    raise ProviderSetupError(
        "No synthesis provider configured or detected. Add combine.config.json, install a local Cursor Agent compatible CLI, "
        "set OPENAI_API_KEY or ANTHROPIC_API_KEY, or run with --provider local-model for a deterministic dry run."
    )


def select_provider_config(
    root: Path,
    config_path: Path | None = None,
    override_type: str | None = None,
) -> tuple[dict[str, Any], str]:
    config = load_config(root, config_path)
    provider_config = dict(config.get("combine_provider", {}))
    env_provider_type = os.getenv("WIKI_COMBINE_PROVIDER")
    provider_type = override_type or env_provider_type or provider_config.get("type")
    if provider_type and provider_type not in PROVIDER_TYPES:
        raise ProviderSetupError(
            f"Unsupported combine provider type: {provider_type}. Use one of: {', '.join(sorted(PROVIDER_TYPES))}."
        )
    if provider_type:
        provider_config["type"] = provider_type
        if override_type:
            return provider_config, "--provider override"
        if env_provider_type:
            return provider_config, "WIKI_COMBINE_PROVIDER"
        return provider_config, str(config_path or root / "combine.config.json")
    return autodetect_provider_config(root)


def normalize_string(value: Any, field: str) -> str:
    if value is None:
        raise ValueError(f"Provider output missing required field: {field}")
    if isinstance(value, list):
        value = "\n".join(f"- {item}" for item in value)
    text = str(value).strip()
    if not text:
        raise ValueError(f"Provider output field cannot be empty: {field}")
    return text


def normalize_string_list(value: Any, field: str) -> list[str]:
    if value is None:
        raise ValueError(f"Provider output missing required field: {field}")
    if isinstance(value, str):
        values = [line.strip().lstrip("- ").strip() for line in value.splitlines()]
    elif isinstance(value, list):
        values = [str(item).strip() for item in value]
    else:
        raise ValueError(f"Provider output field must be a list or string: {field}")
    return [item for item in values if item]


def normalize_score(value: Any, field: str) -> float:
    if value is None:
        raise ValueError(f"Provider output missing required field: {field}")
    if isinstance(value, bool):
        raise ValueError(f"Provider output score must be numeric: {field}")
    try:
        score = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Provider output score must be numeric: {field}") from exc
    if score < 0.0 or score > 1.0:
        raise ValueError(f"Provider output score must be between 0.0 and 1.0: {field}")
    return score


def normalize_enum(value: Any, field: str, allowed: set[str]) -> str:
    text = normalize_string(value, field).lower()
    if text not in allowed:
        allowed_values = ", ".join(sorted(allowed))
        raise ValueError(f"Provider output field {field} must be one of: {allowed_values}")
    return text


def validate_output(payload: Any) -> CombineOutput:
    if not isinstance(payload, dict):
        raise ValueError("Provider output must be a JSON object.")
    output: dict[str, Any] = {}
    for field in REQUIRED_STRING_FIELDS:
        output[field] = normalize_string(payload.get(field), field)
    for field in REQUIRED_LIST_FIELDS:
        output[field] = normalize_string_list(payload.get(field), field)
    for field in REQUIRED_SCORE_FIELDS:
        output[field] = normalize_score(payload.get(field), field)
    output["promotion_readiness"] = normalize_enum(
        payload.get("promotion_readiness"),
        "promotion_readiness",
        PROMOTION_READINESS_LEVELS,
    )
    output["interaction_type"] = normalize_enum(
        payload.get("interaction_type"),
        "interaction_type",
        INTERACTION_TYPES,
    )
    return output  # type: ignore[return-value]


def migrate_legacy_output(payload: dict[str, Any]) -> CombineOutput:
    """Upgrade old persisted/provider-like payloads when explicitly requested.

    New provider generations still call ``validate_output`` directly, so missing
    contract fields are not silently accepted.
    """

    upgraded = dict(payload)
    upgraded.setdefault("non_obviousness_reason", "Legacy output did not include a non-obviousness rationale.")
    upgraded.setdefault("primary_bottleneck", "unknown")
    upgraded.setdefault("specific_user_or_buyer", "unknown")
    upgraded.setdefault("novelty_score", 0.0)
    upgraded.setdefault("plausibility_score", 0.0)
    upgraded.setdefault("promotion_readiness", "low")
    upgraded.setdefault("interaction_type", "epistemic")
    upgraded.setdefault("grounded_points", ["Legacy output did not separate grounded points."])
    upgraded.setdefault("speculative_extensions", ["Legacy output did not separate speculative extensions."])
    upgraded.setdefault("evidence_needed_before_promotion", ["Legacy output needs human review before promotion."])
    return validate_output(upgraded)


def extract_json_object(text: str) -> Any:
    stripped = text.strip()
    if not stripped:
        raise ValueError("Provider returned empty output.")
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError("Provider stdout did not contain a JSON object.")
        return json.loads(stripped[start : end + 1])


def provider_prompt(input_data: CombineInput) -> str:
    prompt_template = """You are generating a speculative combination draft for a structured markdown-based LLM Wiki system.

Your job is to produce a **high-quality, non-obvious synthesis** of two canonical parent pages.

This is NOT canonical truth. This is a **disciplined hypothesis**.

---

## Core Directive

On high-tension / high domain-distance pairs, lean into **intellectual boldness and non-obvious bridges**.

Write like a sharp, curious researcher exploring a genuinely interesting idea.

Favor:

* depth over surface-level coverage
* precision over generic statements
* insight over completeness

Do NOT flatten strong ideas to be safe.
Instead, explore them deeply and **label their boundaries clearly**.

---

## Internal Thinking Step (CRITICAL)

Before producing the final output:

1. Think through the combination deeply in freeform reasoning.
2. Identify:

   * the strongest possible bridge between the two domains
   * where the analogy or interaction holds vs breaks
   * the most non-obvious but defensible insight
   * one concrete, narrow product or system that emerges
3. Do NOT format yet.

Then:

Convert that reasoning into the required structured JSON.

---

## Interaction Discipline

You MUST explicitly classify the interaction:

* mechanistic -> real causal interaction
* analogical -> structural similarity only
* strategic -> decision/system-level similarity
* market_structural -> incentives / market behavior
* epistemic -> knowledge / reasoning structure

If the interaction is NOT mechanistic:

* clearly treat it as analogy
* do NOT imply biological, physical, or causal equivalence

---

## Required Output Rules

You must produce:

* one clear mechanistic or structural interaction
* one narrow, concrete product opportunity
* one explicit primary bottleneck
* one falsifiable test
* one strong non-obviousness explanation
* a clearly defined specific user or buyer

Avoid:

* generic business fluff
* repeating parent summaries
* vague "platform" ideas
* unsupported certainty

Minimize these, but do not over-constrain yourself.

---

## Output Format (STRICT)

Return ONLY valid JSON matching this schema.

No prose outside JSON.

```json
{
  "draft_title": "string",
  "draft_summary": "string",
  "fusion_summary": "string",
  "mechanistic_interaction": "string",
  "product_opportunity": "string",
  "system_design": "string",
  "research_question": "string",
  "falsification_test": "string",
  "non_obviousness_reason": "string",
  "primary_bottleneck": "string",
  "specific_user_or_buyer": "string",
  "interaction_type": "mechanistic | analogical | strategic | market_structural | epistemic",
  "novelty_score": 0.0,
  "plausibility_score": 0.0,
  "promotion_readiness": "low | medium | high",
  "grounded_points": ["string"],
  "speculative_extensions": ["string"],
  "evidence_needed_before_promotion": ["string"],
  "cross_niche_implications": ["string"],
  "failure_modes": ["string"],
  "related_canonical_pages": ["wiki/path/to/existing-page.md"],
  "tags": ["string"],
  "boldness_note": "string"
}
```

---

## Scoring Guidance

* novelty_score:
  how non-obvious and original the combination is (0-1)

* plausibility_score:
  how defensible the reasoning is given known constraints (0-1)

* promotion_readiness:

  * low -> interesting but speculative
  * medium -> plausible and structured
  * high -> strong candidate for canonical expansion

---

## Evidence Boundary

* grounded_points must include only claims directly grounded in the parent inputs.
* speculative_extensions must label hypotheses that go beyond the parent inputs.
* evidence_needed_before_promotion must state what evidence would be needed before canonical promotion.

---

## Safety Constraints

* Do NOT present speculative claims as established fact
* Do NOT create new canonical pages
* Only reference existing canonical pages
* Do NOT output unresolved wikilinks
* Clearly separate analogy vs mechanism
* Avoid anthropomorphic or misleading equivalence

---

## Combine Input

You are given structured representations of two canonical parent pages:

{COMBINE_INPUT_JSON}

Use these as your grounding.

---

## Final Instruction

Think deeply first.

Then produce a **sharp, structured, high-signal synthesis**.

Return only the JSON object.
"""
    return prompt_template.replace(
        "{COMBINE_INPUT_JSON}",
        json.dumps(input_data, ensure_ascii=False, indent=2),
    )


class ExternalCommandProvider:
    """Route synthesis through a local agent wrapper via stdin/stdout JSON."""

    name = "external-command"

    def __init__(self, command: str | list[str], cwd: Path, timeout_seconds: int = 180) -> None:
        self.command = command
        self.cwd = cwd
        self.timeout_seconds = timeout_seconds

    def synthesize(self, input_data: CombineInput) -> CombineOutput:
        payload = json.dumps(input_data, ensure_ascii=False)
        completed = subprocess.run(
            self.command,
            input=payload,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=self.cwd,
            timeout=self.timeout_seconds,
            shell=isinstance(self.command, str),
        )
        if completed.returncode != 0:
            stderr = completed.stderr.strip() or "no stderr"
            raise RuntimeError(f"External combine provider failed with exit code {completed.returncode}: {stderr}")
        try:
            return validate_output(extract_json_object(completed.stdout))
        except (json.JSONDecodeError, ValueError) as exc:
            raise ValueError(f"External combine provider returned invalid JSON: {exc}") from exc


class OpenAIProvider:
    """Minimal OpenAI-compatible chat completions provider using stdlib HTTP."""

    name = "openai"

    def __init__(
        self,
        model: str,
        api_key: str,
        base_url: str = "https://api.openai.com/v1/chat/completions",
        timeout_seconds: int = 180,
    ) -> None:
        self.model = model
        self.api_key = api_key
        self.base_url = base_url
        self.timeout_seconds = timeout_seconds

    def synthesize(self, input_data: CombineInput) -> CombineOutput:
        payload = {
            "model": self.model,
            "temperature": 0.4,
            "messages": [
                {"role": "system", "content": "Return strict JSON only."},
                {"role": "user", "content": provider_prompt(input_data)},
            ],
            "response_format": {"type": "json_object"},
        }
        response = post_json(
            self.base_url,
            payload,
            {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            self.timeout_seconds,
        )
        content = response["choices"][0]["message"]["content"]
        return validate_output(extract_json_object(content))


class AnthropicProvider:
    """Minimal Anthropic Messages provider using stdlib HTTP."""

    name = "anthropic"

    def __init__(
        self,
        model: str,
        api_key: str,
        base_url: str = "https://api.anthropic.com/v1/messages",
        timeout_seconds: int = 180,
    ) -> None:
        self.model = model
        self.api_key = api_key
        self.base_url = base_url
        self.timeout_seconds = timeout_seconds

    def synthesize(self, input_data: CombineInput) -> CombineOutput:
        payload = {
            "model": self.model,
            "max_tokens": 2400,
            "temperature": 0.4,
            "system": "Return strict JSON only.",
            "messages": [{"role": "user", "content": provider_prompt(input_data)}],
        }
        response = post_json(
            self.base_url,
            payload,
            {
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            self.timeout_seconds,
        )
        content_blocks = response.get("content", [])
        content = "\n".join(block.get("text", "") for block in content_blocks if block.get("type") == "text")
        return validate_output(extract_json_object(content))


class LocalModelProvider:
    """Local-model provider with optional OpenAI-compatible endpoint.

    Without an endpoint, it returns a deterministic offline synthesis so the
    repo remains testable and usable before a user configures a real model.
    """

    name = "local-model"

    def __init__(self, endpoint: str | None = None, model: str = "local-combine", timeout_seconds: int = 180) -> None:
        self.endpoint = endpoint
        self.model = model
        self.timeout_seconds = timeout_seconds

    def synthesize(self, input_data: CombineInput) -> CombineOutput:
        if self.endpoint:
            payload = {
                "model": self.model,
                "temperature": 0.4,
                "messages": [{"role": "user", "content": provider_prompt(input_data)}],
            }
            response = post_json(self.endpoint, payload, {"Content-Type": "application/json"}, self.timeout_seconds)
            content = response["choices"][0]["message"]["content"]
            return validate_output(extract_json_object(content))
        return validate_output(local_template_output(input_data))


def post_json(url: str, payload: dict[str, Any], headers: dict[str, str], timeout_seconds: int) -> Any:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Provider HTTP request failed: {exc.code} {detail}") from exc


def local_template_output(input_data: CombineInput) -> dict[str, Any]:
    parent_a = input_data["parent_a"]
    parent_b = input_data["parent_b"]
    title_a = parent_a.get("title", "Parent A")
    title_b = parent_b.get("title", "Parent B")
    bottleneck = parent_b.get("primary_bottleneck") or parent_a.get("primary_bottleneck")
    if not bottleneck or bottleneck == "unknown":
        bottleneck = "A testable workflow must be narrow enough to separate useful synthesis from word association."
    tags = []
    for tag in [*parent_a.get("tags", []), *parent_b.get("tags", []), "cross-niche"]:
        if tag not in tags:
            tags.append(tag)
    related = []
    for link in [*parent_a.get("linked_concepts", []), *parent_b.get("linked_concepts", [])]:
        if link not in related:
            related.append(link)
    return {
        "draft_title": f"{title_a} x {title_b}",
        "draft_summary": (
            f"Speculative combination draft pairing {title_a} with {title_b}; "
            "not canonical until explicitly promoted."
        ),
        "fusion_summary": (
            f"Combine {title_a} with {title_b} as a mechanism-to-context pairing. "
            f"Parent A grounding: {parent_a.get('summary', 'No summary provided.')}. "
            f"Parent B grounding: {parent_b.get('summary', 'No summary provided.')}."
        ),
        "mechanistic_interaction": (
            f"{title_a} supplies a repeatable decision loop, while {title_b} supplies the adoption constraint; "
            "the interaction is useful only where that loop changes one concrete operating choice."
        ),
        "product_opportunity": (
            "Run a two-page operating memo that asks one founder team to choose, defer, or discard a single initiative "
            "using the combined frame."
        ),
        "system_design": (
            "Canonical pages stay as immutable ingredients. The draft explores a synthesis layer. "
            "Promotion requires a review artifact before canonical content changes."
        ),
        "research_question": (
            f"What becomes possible if the core mechanism in {title_a} is applied to the constraints in {title_b}, "
            "and what evidence would be required before promotion?"
        ),
        "falsification_test": (
            "If three reviewed decisions produce the same action the team would have taken from either parent alone, "
            "the fusion is too weak to promote."
        ),
        "non_obviousness_reason": (
            "The pairing is non-obvious because it treats one parent as an operating constraint on the other, "
            "rather than summarizing their surface-level themes."
        ),
        "primary_bottleneck": bottleneck,
        "specific_user_or_buyer": "Seed-stage founder choosing between two operating initiatives this week.",
        "novelty_score": 0.45,
        "plausibility_score": 0.55,
        "promotion_readiness": "low",
        "interaction_type": "strategic",
        "grounded_points": [
            f"{title_a} is the first canonical parent and supplies one side of the draft lineage.",
            f"{title_b} is the second canonical parent and supplies the other side of the draft lineage.",
        ],
        "speculative_extensions": [
            "The draft hypothesizes that combining the parent frames can change one concrete operating decision.",
        ],
        "evidence_needed_before_promotion": [
            "Show that the combined frame changes a real decision beyond what either parent page already explains.",
            "Verify any domain-specific claims against canonical pages and source material before promotion.",
        ],
        "cross_niche_implications": [
            f"{tag}: test whether the combined frame changes one concrete decision in the parent workflow."
            for tag in tags
        ],
        "failure_modes": [
            "False analogy: shared vocabulary may hide different causal mechanisms.",
            "Overextension: a useful speculative frame can become an unsupported factual claim.",
            "Canonical contamination: parent pages must not backlink to this draft unless promoted.",
        ],
        "related_canonical_pages": related[:12],
        "tags": tags,
    }


def load_provider(root: Path, config_path: Path | None = None, override_type: str | None = None) -> CombineProvider:
    provider_config, _source = select_provider_config(root, config_path, override_type)
    provider_type = provider_config["type"]

    timeout = int(provider_config.get("timeout_seconds", 180))
    if provider_type == "external-command":
        command = provider_config.get("command")
        if not command:
            raise ProviderSetupError("external-command provider requires combine_provider.command.")
        if not command_is_available(command, root):
            executable = command_executable(command) or str(command)
            raise ProviderSetupError(
                f"External command provider executable was not found: {executable}. "
                "Install it, fix combine.config.json, or run wiki-combine --doctor for setup checks."
            )
        return ExternalCommandProvider(command=command, cwd=root, timeout_seconds=timeout)
    if provider_type == "openai":
        api_key = provider_config.get("api_key") or os.getenv(provider_config.get("api_key_env", "OPENAI_API_KEY"))
        if not api_key:
            raise ProviderSetupError("openai provider requires an API key. Set OPENAI_API_KEY or configure combine_provider.api_key_env.")
        return OpenAIProvider(
            model=provider_config.get("model", "gpt-4.1-mini"),
            api_key=api_key,
            base_url=provider_config.get("base_url", "https://api.openai.com/v1/chat/completions"),
            timeout_seconds=timeout,
        )
    if provider_type == "anthropic":
        api_key = provider_config.get("api_key") or os.getenv(provider_config.get("api_key_env", "ANTHROPIC_API_KEY"))
        if not api_key:
            raise ProviderSetupError("anthropic provider requires an API key. Set ANTHROPIC_API_KEY or configure combine_provider.api_key_env.")
        return AnthropicProvider(
            model=provider_config.get("model", "claude-3-5-sonnet-latest"),
            api_key=api_key,
            base_url=provider_config.get("base_url", "https://api.anthropic.com/v1/messages"),
            timeout_seconds=timeout,
        )
    if provider_type == "local-model":
        return LocalModelProvider(
            endpoint=provider_config.get("endpoint"),
            model=provider_config.get("model", "local-combine"),
            timeout_seconds=timeout,
        )
    raise ProviderSetupError(f"Unsupported combine provider type: {provider_type}")


def load_config(root: Path, config_path: Path | None = None) -> dict[str, Any]:
    path = config_path or root / "combine.config.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid combine config JSON at {path}: {exc}") from exc
