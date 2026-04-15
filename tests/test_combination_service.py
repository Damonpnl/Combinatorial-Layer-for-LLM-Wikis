import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from combination_service import CombinationService
from combination_providers import ExternalCommandProvider


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class CountingProvider:
    name = "counting-provider"

    def __init__(self) -> None:
        self.calls = 0

    def synthesize(self, input_data):
        self.calls += 1
        return {
            "draft_title": "Blocked Pair Should Not Synthesize",
            "draft_summary": "Provider output.",
            "fusion_summary": "Provider fusion.",
            "mechanistic_interaction": "Provider mechanism.",
            "product_opportunity": "Provider product.",
            "system_design": "Provider system.",
            "research_question": "Provider research?",
            "falsification_test": "Provider falsification.",
            "cross_niche_implications": ["Provider implication."],
            "failure_modes": ["Provider failure mode."],
            "related_canonical_pages": [],
            "tags": ["ai", "cross-niche"],
            "non_obviousness_reason": "The pair tests a constraint across domains.",
            "primary_bottleneck": "Narrow workflow selection.",
            "specific_user_or_buyer": "Founder operator.",
            "novelty_score": 0.5,
            "plausibility_score": 0.5,
            "promotion_readiness": "low",
            "interaction_type": "strategic",
            "grounded_points": ["Parent pages are canonical inputs."],
            "speculative_extensions": ["The combination may reveal one useful operating constraint."],
            "evidence_needed_before_promotion": ["Reviewer must verify claims against canonical pages."],
        }


class GenericProvider:
    name = "generic-provider"

    def synthesize(self, input_data):
        return {
            "draft_title": "Generic Draft",
            "draft_summary": "Generic synthesis.",
            "fusion_summary": "This combines the parent summaries.",
            "mechanistic_interaction": "Use the first parent as an operating mechanism and the second as a constraint space.",
            "product_opportunity": "Build a broad platform to unlock value for users.",
            "system_design": "External system.",
            "research_question": "External research question?",
            "falsification_test": "The idea fails if it cannot produce observable behavior change.",
            "non_obviousness_reason": "It is non-obvious because it combines two areas.",
            "primary_bottleneck": "unknown",
            "specific_user_or_buyer": "users",
            "novelty_score": 0.95,
            "plausibility_score": 0.95,
            "promotion_readiness": "high",
            "interaction_type": "strategic",
            "grounded_points": ["Generic grounded point."],
            "speculative_extensions": ["Generic speculation."],
            "evidence_needed_before_promotion": ["Generic evidence request."],
            "cross_niche_implications": [
                "AI: inspect whether this tag contributes mechanism, market context, risk, or distribution leverage."
            ],
            "failure_modes": ["Generic failure."],
            "related_canonical_pages": [],
            "tags": ["ai", "cross-niche"],
        }


class CacheProvider:
    name = "cache-provider"

    def __init__(self, model: str = "cache-model-v1") -> None:
        self.model = model
        self.calls = 0

    def synthesize(self, input_data):
        self.calls += 1
        return {
            "draft_title": "Cacheable Synthesis",
            "draft_summary": "Provider output.",
            "fusion_summary": "Agent loops can tighten business-model activity feedback.",
            "mechanistic_interaction": "Agentic planning loops reduce the interval between customer signal capture and activity-system redesign.",
            "product_opportunity": "Sell a two-week workflow audit to seed-stage founders deciding whether to automate one onboarding step.",
            "system_design": "Canonical pages stay fixed while draft synthesis remains reviewable.",
            "research_question": "Does a shorter signal-to-redesign loop improve one operating decision?",
            "falsification_test": "If five onboarding audits produce no changed step within 14 days, the fusion is not operationally useful.",
            "non_obviousness_reason": "It connects agent loop timing to business-model activity redesign, not just AI tooling.",
            "primary_bottleneck": "The founder must identify one onboarding step with repeated customer signal loss.",
            "specific_user_or_buyer": "Seed-stage SaaS founder redesigning onboarding after ten customer calls.",
            "novelty_score": 0.6,
            "plausibility_score": 0.7,
            "promotion_readiness": "medium",
            "interaction_type": "mechanistic",
            "grounded_points": ["Agentic AI is a canonical parent.", "Business Model Design is a canonical parent."],
            "speculative_extensions": ["Agent loops may alter one founder onboarding decision."],
            "evidence_needed_before_promotion": ["Decision logs showing a changed onboarding action."],
            "cross_niche_implications": ["AI: planning loops become a testable operating cadence for onboarding redesign."],
            "failure_modes": ["The audit may confuse automation speed with real activity-system value."],
            "related_canonical_pages": input_data["parent_a"]["linked_concepts"],
            "tags": ["ai", "startups", "cross-niche"],
        }


class EpistemicProvider(CacheProvider):
    name = "epistemic-provider"

    def __init__(self, interaction_type: str = "mechanistic", tags: list[str] | None = None) -> None:
        super().__init__()
        self.interaction_type = interaction_type
        self.tags = tags or ["ai", "startups", "cross-niche"]

    def synthesize(self, input_data):
        payload = super().synthesize(input_data)
        payload["interaction_type"] = self.interaction_type
        payload["tags"] = self.tags
        if self.interaction_type == "analogical":
            payload["mechanistic_interaction"] = (
                "Agentic planning loops and tissue-repair protocols are compared by analogy around feedback timing."
            )
            payload["non_obviousness_reason"] = "The analogy compares feedback timing, not causal equivalence."
            payload["speculative_extensions"] = ["The feedback-timing analogy may suggest a research question for founder recovery routines."]
        return payload


class WikilinkProvider(CacheProvider):
    name = "wikilink-provider"

    def synthesize(self, input_data):
        payload = super().synthesize(input_data)
        payload["fusion_summary"] = (
            "Compare [[missing/not-real|missing concept]] with [[ai/agentic-ai|Agentic AI]]."
        )
        payload["grounded_points"] = [
            "Grounded in [[startups/business-model-design|Business Model Design]]."
        ]
        return payload


class CombinationServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.service = CombinationService(self.root, provider_type="local-model")

        write(
            self.root / "wiki" / "index.md",
            """---
title: "Index"
summary: "Master catalog and navigation hub. 31 sources, 2 pages across test niches."
type: hub
status: final
---

# Index

**Status:** Active - 31 sources ingested, 2 wiki pages created

---

## Source Summaries
""",
        )
        write(
            self.root / "wiki" / "log.md",
            """---
title: "Log"
type: output
status: final
---

# Log
""",
        )
        write(
            self.root / "wiki" / "combinations" / "index.md",
            """---
title: "Combination Lab"
type: hub
status: final
---

# Combination Lab

## Current Draft Index

| Draft | Parents | Promotion State |
|---|---|---|
""",
        )
        write(
            self.root / "wiki" / "ai" / "agentic-ai.md",
            """---
title: "Agentic AI"
summary: "Agents use tools and loops."
tags: [ai, startups]
type: concept
status: final
---

# Agentic AI

Links to [[startups/business-model-design]] and [[missing/not-real]].

## Cross-Niche Implications

- Useful across domains.
""",
        )
        write(
            self.root / "wiki" / "startups" / "business-model-design.md",
            """---
title: "Business Model Design"
summary: "Activity systems create and capture value."
tags: [startups, markets]
type: concept
status: final
---

# Business Model Design

Links to [[ai/agentic-ai]].
""",
        )
        write(
            self.root / "wiki" / "sources" / "source-summary.md",
            """---
title: "Source"
summary: "Excluded source."
tags: [ai]
type: source-summary
status: final
---

# Source
""",
        )
        write(
            self.root / "wiki" / "ai.md",
            """---
title: "AI Hub"
summary: "Excluded hub."
tags: [ai]
type: hub
status: final
---

# AI
""",
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_discovers_only_canonical_pages_with_metadata(self) -> None:
        pages = self.service.discover_canonical_pages()
        paths = {page.wikilink_path for page in pages}

        self.assertEqual(paths, {"ai/agentic-ai", "startups/business-model-design"})
        agentic = next(page for page in pages if page.wikilink_path == "ai/agentic-ai")
        self.assertEqual(agentic.title, "Agentic AI")
        self.assertEqual(agentic.summary, "Agents use tools and loops.")
        self.assertEqual(agentic.tags, ["ai", "startups"])
        self.assertEqual(agentic.page_type, "concept")
        self.assertEqual(agentic.status, "final")
        self.assertIn("startups/business-model-design", agentic.outgoing_wikilinks)
        self.assertTrue(agentic.has_cross_niche_implications)
        self.assertIn("Links to", agentic.body)

    def test_extended_parent_extraction_uses_section_markers(self) -> None:
        write(
            self.root / "wiki" / "ai" / "marked-system.md",
            """---
title: "Marked System"
summary: "A page with explicit extraction markers."
tags: [ai]
type: tool
status: final
---

# Marked System

## Core Mechanism

- Tool calls close the loop between intent and action.

## Control Variable

- Latency between observation and intervention.

## Primary Bottleneck

- Reliable context selection.

## Dominant Failure Mode

- False autonomy from stale context.

## Highest Leverage Use Case

- Founder operating copilots.

## Evidence Base

- protocol_defined
""",
        )

        page = self.service.resolve_canonical_page("ai/marked-system")
        payload = self.service.page_to_combine_input(page)

        self.assertEqual(payload["core_mechanism"], "Tool calls close the loop between intent and action.")
        self.assertEqual(payload["control_variable"], "Latency between observation and intervention.")
        self.assertEqual(payload["primary_bottleneck"], "Reliable context selection.")
        self.assertEqual(payload["dominant_failure_mode"], "False autonomy from stale context.")
        self.assertEqual(payload["highest_leverage_use_case"], "Founder operating copilots.")
        self.assertEqual(payload["certainty_level"], "protocol_defined")

    def test_extended_parent_extraction_falls_back_to_unknown(self) -> None:
        page = self.service.resolve_canonical_page("startups/business-model-design")
        payload = self.service.page_to_combine_input(page)

        self.assertEqual(payload["core_mechanism"], "unknown")
        self.assertEqual(payload["control_variable"], "unknown")
        self.assertEqual(payload["primary_bottleneck"], "unknown")
        self.assertEqual(payload["dominant_failure_mode"], "unknown")
        self.assertEqual(payload["highest_leverage_use_case"], "unknown")
        self.assertEqual(payload["certainty_level"], "unknown")

    def test_extended_parent_extraction_handles_sparse_pages(self) -> None:
        write(
            self.root / "wiki" / "markets" / "sparse.md",
            """---
title: "Sparse"
summary: "Minimal page."
tags: [markets]
type: concept
status: draft
---
""",
        )

        page = self.service.resolve_canonical_page("markets/sparse")
        payload = self.service.page_to_combine_input(page)

        self.assertEqual(payload["core_mechanism"], "unknown")
        self.assertEqual(payload["control_variable"], "unknown")
        self.assertEqual(payload["primary_bottleneck"], "unknown")
        self.assertEqual(payload["dominant_failure_mode"], "unknown")
        self.assertEqual(payload["highest_leverage_use_case"], "unknown")
        self.assertEqual(payload["certainty_level"], "unknown")
        self.assertEqual(payload["body_text"], "")

    def test_create_draft_writes_markdown_and_updates_indexes_without_parent_mutation(self) -> None:
        parent_path = self.root / "wiki" / "ai" / "agentic-ai.md"
        parent_before = parent_path.read_text(encoding="utf-8")

        draft = self.service.create_draft("ai/agentic-ai", "startups/business-model-design")
        text = draft.read_text(encoding="utf-8")

        self.assertEqual(draft.name, "agentic-ai-x-business-model-design.md")
        self.assertIn("origin: combination", text)
        self.assertIn("parents:\n  - wiki/ai/agentic-ai.md\n  - wiki/startups/business-model-design.md", text)
        self.assertIn("promotion_state: not-submitted", text)
        self.assertIn("pair_score:", text)
        self.assertIn("pair_score_threshold:", text)
        self.assertIn("pair_score_block_low: false", text)
        self.assertIn("generation_metadata:", text)
        self.assertIn("# Fusion Summary", text)
        self.assertIn("# Mechanistic Interaction", text)
        self.assertIn("# Product Opportunity", text)
        self.assertIn("# System Design", text)
        self.assertIn("# Research Question", text)
        self.assertIn("# Falsification Test", text)
        self.assertIn("# Cross-Niche Implications", text)
        self.assertIn("# Failure Modes", text)
        self.assertIn("# Related Canonical Pages", text)
        self.assertNotIn("[[missing/not-real]]", text)
        self.assertEqual(parent_path.read_text(encoding="utf-8"), parent_before)

        combo_index = (self.root / "wiki" / "combinations" / "index.md").read_text(encoding="utf-8")
        main_index = (self.root / "wiki" / "index.md").read_text(encoding="utf-8")
        log = (self.root / "wiki" / "log.md").read_text(encoding="utf-8")

        self.assertIn("[[combinations/drafts/agentic-ai-x-business-model-design", combo_index)
        self.assertIn("## Combination Drafts", main_index)
        self.assertIn("3 wiki pages created", main_index)
        self.assertIn("COMBINE - Agentic AI x Business Model Design", log)
        self.assertIn("[[ai/agentic-ai]] + [[startups/business-model-design]]", log)

    def test_provider_text_does_not_render_unresolved_wikilinks(self) -> None:
        service = CombinationService(self.root, provider=WikilinkProvider())

        draft = service.create_draft("ai/agentic-ai", "startups/business-model-design")
        text = draft.read_text(encoding="utf-8")

        self.assertNotIn("[[missing/not-real", text)
        self.assertIn("missing concept", text)
        self.assertIn("[[ai/agentic-ai|Agentic AI]]", text)
        self.assertIn("[[startups/business-model-design|Business Model Design]]", text)

    def test_pending_submission_updates_draft_and_creates_review_without_canonical_mutation(self) -> None:
        canonical_path = self.root / "wiki" / "startups" / "business-model-design.md"
        canonical_before = canonical_path.read_text(encoding="utf-8")
        draft = self.service.create_draft("ai/agentic-ai", "startups/business-model-design")

        request = self.service.create_promotion_request(
            str(draft),
            "Worth reviewing.",
            suggested_destination="wiki/cross-niche/agentic-business-model-design.md",
            suggested_merge_strategy="create_new_canonical",
        )

        draft_text = draft.read_text(encoding="utf-8")
        request_text = request.read_text(encoding="utf-8")
        log = (self.root / "wiki" / "log.md").read_text(encoding="utf-8")

        self.assertIn("promotion_state: pending", draft_text)
        self.assertTrue(request.relative_to(self.root).as_posix().endswith("wiki/promotion-queue/pending/agentic-ai-x-business-model-design-promotion.md"))
        self.assertIn("review_state: pending", request_text)
        self.assertIn("draft_path: wiki/combinations/drafts/agentic-ai-x-business-model-design.md", request_text)
        self.assertIn("suggested_destination: wiki/cross-niche/agentic-business-model-design.md", request_text)
        self.assertIn("suggested_merge_strategy: create_new_canonical", request_text)
        self.assertIn("PROMOTION SUBMITTED - Agentic AI x Business Model Design", log)
        self.assertEqual(canonical_path.read_text(encoding="utf-8"), canonical_before)

    def test_approval_create_new_canonical_moves_request_and_updates_index(self) -> None:
        draft = self.service.create_draft("ai/agentic-ai", "startups/business-model-design")
        request = self.service.create_promotion_request(
            str(draft),
            "Promote this.",
            suggested_destination="wiki/cross-niche/agentic-business-model-design.md",
            suggested_merge_strategy="create_new_canonical",
        )

        target = self.service.approve_promotion_request(str(request), note="Approved.")

        target_text = target.read_text(encoding="utf-8")
        draft_text = draft.read_text(encoding="utf-8")
        index_text = (self.root / "wiki" / "index.md").read_text(encoding="utf-8")
        log = (self.root / "wiki" / "log.md").read_text(encoding="utf-8")

        self.assertEqual(target.relative_to(self.root).as_posix(), "wiki/cross-niche/agentic-business-model-design.md")
        self.assertIn("type: synthesis", target_text)
        self.assertIn("status: final", target_text)
        self.assertIn("## Promotion Lineage", target_text)
        self.assertIn("promotion_state: approved", draft_text)
        self.assertFalse(request.exists())
        self.assertTrue((self.root / "wiki" / "promotion-queue" / "approved" / request.name).exists())
        self.assertIn("## Promoted Canonical Updates", index_text)
        self.assertIn("4 wiki pages created", index_text)
        self.assertIn("PROMOTION APPROVED - Agentic AI x Business Model Design", log)

    def test_rejection_moves_request_without_canonical_creation(self) -> None:
        draft = self.service.create_draft("ai/agentic-ai", "startups/business-model-design")
        request = self.service.create_promotion_request(
            str(draft),
            "Not ready.",
            suggested_destination="wiki/cross-niche/agentic-business-model-design.md",
        )

        rejected = self.service.reject_promotion_request(str(request), note="Too speculative.")

        self.assertFalse(request.exists())
        self.assertTrue(rejected.exists())
        self.assertIn("promotion_state: rejected", draft.read_text(encoding="utf-8"))
        self.assertFalse((self.root / "wiki" / "cross-niche" / "agentic-business-model-design.md").exists())
        self.assertIn("PROMOTION CLOSED", (self.root / "wiki" / "log.md").read_text(encoding="utf-8"))

    def test_external_command_provider_generates_validated_draft(self) -> None:
        provider_script = self.root / "provider.py"
        write(
            provider_script,
            """import json
import sys

payload = json.load(sys.stdin)
parent_a = payload["parent_a"]
parent_b = payload["parent_b"]
json.dump({
    "draft_title": parent_a["title"] + " x " + parent_b["title"],
    "draft_summary": "External provider synthesis.",
    "fusion_summary": "Agent loops can tighten business-model activity feedback.",
    "mechanistic_interaction": "Agentic planning loops reduce the interval between customer signal capture and activity-system redesign.",
    "product_opportunity": "Sell a two-week workflow audit to seed-stage founders deciding whether to automate one onboarding step.",
    "system_design": "External system.",
    "research_question": "External research question?",
    "falsification_test": "If five onboarding audits produce no changed step within 14 days, the fusion is not operationally useful.",
    "non_obviousness_reason": "It connects agent loop timing to business-model activity redesign, not just AI tooling.",
    "primary_bottleneck": "The founder must identify one onboarding step with repeated customer signal loss.",
    "specific_user_or_buyer": "Seed-stage SaaS founder redesigning onboarding after ten customer calls.",
    "novelty_score": 0.6,
    "plausibility_score": 0.7,
    "promotion_readiness": "medium",
    "interaction_type": "mechanistic",
    "grounded_points": ["Agentic AI is a canonical parent.", "Business Model Design is a canonical parent."],
    "speculative_extensions": ["Agent loops may alter one founder onboarding decision."],
    "evidence_needed_before_promotion": ["Decision logs showing a changed onboarding action."],
    "cross_niche_implications": ["External implication."],
    "failure_modes": ["External failure mode."],
    "related_canonical_pages": parent_a["linked_concepts"],
    "tags": ["ai", "startups", "cross-niche"]
}, sys.stdout)
""",
        )
        provider = ExternalCommandProvider([sys.executable, str(provider_script)], cwd=self.root)
        service = CombinationService(self.root, provider=provider)

        draft = service.create_draft("ai/agentic-ai", "startups/business-model-design")
        text = draft.read_text(encoding="utf-8")

        self.assertIn("summary: \"External provider synthesis.\"", text)
        self.assertIn("# Mechanistic Interaction\n\nAgentic planning loops reduce", text)
        self.assertIn("# Falsification Test\n\nIf five onboarding audits", text)
        self.assertIn("[[startups/business-model-design|Business Model Design]]", text)

    def test_semantic_reject_blocks_draft_save(self) -> None:
        service = CombinationService(self.root, provider=GenericProvider())

        with self.assertRaises(SystemExit):
            service.create_draft("ai/agentic-ai", "startups/business-model-design")

        self.assertFalse(
            (self.root / "wiki" / "combinations" / "drafts" / "agentic-ai-x-business-model-design.md").exists()
        )

    def test_synthesis_cache_hit_reuses_provider_output(self) -> None:
        provider = CacheProvider()
        service = CombinationService(self.root, provider=provider)

        first = service.combine_pages("ai/agentic-ai", "startups/business-model-design")
        second = service.combine_pages("ai/agentic-ai", "startups/business-model-design")

        self.assertEqual(provider.calls, 1)
        self.assertFalse(first.generation_metadata["synthesis_cache_hit"])
        self.assertTrue(second.generation_metadata["synthesis_cache_hit"])
        self.assertTrue(any((self.root / "wiki" / "combinations" / "cache" / "extractions").glob("*.json")))
        self.assertTrue(any((self.root / "wiki" / "combinations" / "cache" / "pair_scores").glob("*.json")))
        self.assertTrue(any((self.root / "wiki" / "combinations" / "cache" / "synthesis").glob("*.json")))

    def test_synthesis_cache_misses_after_parent_content_change(self) -> None:
        provider = CacheProvider()
        service = CombinationService(self.root, provider=provider)

        service.combine_pages("ai/agentic-ai", "startups/business-model-design")
        agentic_path = self.root / "wiki" / "ai" / "agentic-ai.md"
        agentic_path.write_text(agentic_path.read_text(encoding="utf-8") + "\n\n## Mechanism\n\n- New loop detail.\n", encoding="utf-8")
        service.combine_pages("ai/agentic-ai", "startups/business-model-design")

        self.assertEqual(provider.calls, 2)

    def test_synthesis_cache_misses_after_prompt_version_change(self) -> None:
        provider = CacheProvider()
        service = CombinationService(self.root, provider=provider)

        service.combine_pages("ai/agentic-ai", "startups/business-model-design")
        service.prompt_version = "combine-prompt-test-v2"
        result = service.combine_pages("ai/agentic-ai", "startups/business-model-design")

        self.assertEqual(provider.calls, 2)
        self.assertEqual(result.generation_metadata["prompt_version"], "combine-prompt-test-v2")

    def test_synthesis_cache_misses_after_config_change(self) -> None:
        provider = CacheProvider()
        service = CombinationService(self.root, provider=provider)

        service.combine_pages("ai/agentic-ai", "startups/business-model-design")
        write(
            self.root / "combine.config.json",
            """{
  "cache": {
    "enabled": true
  },
  "semantic_gate": {
    "needs_revision_behavior": "allow",
    "save_diagnostics": false
  }
}
""",
        )
        service.combine_pages("ai/agentic-ai", "startups/business-model-design")

        self.assertEqual(provider.calls, 2)

    def test_analogical_combination_renders_boundary(self) -> None:
        provider = EpistemicProvider(interaction_type="analogical", tags=["ai", "biohacking", "cross-niche"])
        service = CombinationService(self.root, provider=provider)

        draft = service.create_draft("ai/agentic-ai", "startups/business-model-design")
        text = draft.read_text(encoding="utf-8")

        self.assertIn("# Interaction Boundary", text)
        self.assertIn("Interaction type: `analogical`", text)
        self.assertIn("does not establish causal equivalence", text)
        self.assertIn("High-risk domain caution", text)

    def test_mechanistic_combination_renders_boundary(self) -> None:
        provider = EpistemicProvider(interaction_type="mechanistic")
        service = CombinationService(self.root, provider=provider)

        draft = service.create_draft("ai/agentic-ai", "startups/business-model-design")
        text = draft.read_text(encoding="utf-8")

        self.assertIn("Interaction type: `mechanistic`", text)
        self.assertIn("mechanism remains provisional", text)

    def test_evidence_needed_is_rendered(self) -> None:
        provider = EpistemicProvider(interaction_type="mechanistic")
        service = CombinationService(self.root, provider=provider)

        draft = service.create_draft("ai/agentic-ai", "startups/business-model-design")
        text = draft.read_text(encoding="utf-8")

        self.assertIn("# Grounded Points", text)
        self.assertIn("# Speculative Extensions", text)
        self.assertIn("# Evidence Needed Before Promotion", text)
        self.assertIn("Decision logs showing a changed onboarding action.", text)

    def test_epistemic_rendering_does_not_mutate_canonical_pages(self) -> None:
        parent_path = self.root / "wiki" / "ai" / "agentic-ai.md"
        parent_before = parent_path.read_text(encoding="utf-8")
        provider = EpistemicProvider(interaction_type="analogical")
        service = CombinationService(self.root, provider=provider)

        service.create_draft("ai/agentic-ai", "startups/business-model-design")

        self.assertEqual(parent_path.read_text(encoding="utf-8"), parent_before)

    def test_low_score_block_happens_before_provider_call(self) -> None:
        write(
            self.root / "combine.config.json",
            """{
  "pair_scoring": {
    "score_threshold": 0.95,
    "block_low_score": true
  }
}
""",
        )
        provider = CountingProvider()
        service = CombinationService(self.root, provider=provider)

        with self.assertRaises(SystemExit):
            service.create_draft("ai/agentic-ai", "startups/business-model-design")

        self.assertEqual(provider.calls, 0)


if __name__ == "__main__":
    unittest.main()
