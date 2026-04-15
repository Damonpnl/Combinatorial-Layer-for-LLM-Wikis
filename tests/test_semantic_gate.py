import unittest

from semantic_gate import evaluate_semantic_quality


def parent(path: str, summary: str, links: list[str] | None = None) -> dict:
    return {
        "path": path,
        "summary": summary,
        "linked_concepts": links or [],
    }


def high_quality_output() -> dict:
    return {
        "draft_title": "Agentic AI x Business Model Design",
        "draft_summary": "Speculative synthesis.",
        "fusion_summary": "Agent loops can tighten business-model activity feedback.",
        "mechanistic_interaction": (
            "Agentic planning loops reduce the interval between customer signal capture and activity-system redesign."
        ),
        "product_opportunity": (
            "Sell a two-week workflow audit to seed-stage founders deciding whether to automate one onboarding step."
        ),
        "system_design": "Canonical inputs stay fixed while the draft remains reviewable.",
        "research_question": "Does a shorter signal-to-redesign loop improve one operating decision?",
        "falsification_test": (
            "If five onboarding audits produce no changed step within 14 days, the fusion is not operationally useful."
        ),
        "non_obviousness_reason": "It connects agent loop timing to business-model activity redesign, not just AI tooling.",
        "primary_bottleneck": "The founder must identify one onboarding step with repeated customer signal loss.",
        "specific_user_or_buyer": "Seed-stage SaaS founder redesigning onboarding after ten customer calls.",
        "novelty_score": 0.72,
        "plausibility_score": 0.68,
        "promotion_readiness": "medium",
        "interaction_type": "mechanistic",
        "grounded_points": ["Agentic AI is a parent page.", "Business Model Design is a parent page."],
        "speculative_extensions": ["Agent loop timing may change business-model redesign cadence."],
        "evidence_needed_before_promotion": ["Decision logs showing changed onboarding actions."],
        "cross_niche_implications": ["AI: planning loops become a testable operating cadence for onboarding redesign."],
        "failure_modes": ["The audit may confuse automation speed with real activity-system value."],
        "related_canonical_pages": ["wiki/startups/business-model-design.md"],
        "tags": ["ai", "startups", "cross-niche"],
    }


class SemanticGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.parent_a = parent("wiki/ai/agentic-ai.md", "Agents use tools and loops.", ["wiki/startups/business-model-design.md"])
        self.parent_b = parent("wiki/startups/business-model-design.md", "Activity systems create and capture value.")

    def test_high_quality_output_is_accepted(self) -> None:
        result = evaluate_semantic_quality(high_quality_output(), self.parent_a, self.parent_b)

        self.assertEqual(result["status"], "accept")
        self.assertEqual(result["flags"], [])

    def test_obviously_generic_output_is_rejected(self) -> None:
        output = high_quality_output()
        output.update(
            {
                "mechanistic_interaction": "Use the first parent as an operating mechanism and the second as a constraint space.",
                "product_opportunity": "Build a broad platform to unlock value for users.",
                "falsification_test": "The idea fails if it cannot produce observable behavior change.",
                "cross_niche_implications": ["AI: inspect whether this tag contributes mechanism, market context, risk, or distribution leverage."],
                "specific_user_or_buyer": "users",
                "primary_bottleneck": "unknown",
                "novelty_score": 0.92,
                "plausibility_score": 0.91,
            }
        )

        result = evaluate_semantic_quality(output, self.parent_a, self.parent_b)

        self.assertEqual(result["status"], "reject")
        self.assertIn("generic_mechanism", result["flags"])
        self.assertIn("generic_product", result["flags"])
        self.assertIn("score_inconsistency", result["flags"])

    def test_vague_falsification_is_flagged(self) -> None:
        output = high_quality_output()
        output["falsification_test"] = "The idea fails if it does not work."

        result = evaluate_semantic_quality(output, self.parent_a, self.parent_b)

        self.assertEqual(result["status"], "needs_revision")
        self.assertIn("vague_falsification", result["flags"])

    def test_irrelevant_related_page_suggestions_are_flagged(self) -> None:
        output = high_quality_output()
        output["related_canonical_pages"] = ["wiki/politics/unrelated-page.md"]

        result = evaluate_semantic_quality(output, self.parent_a, self.parent_b)

        self.assertEqual(result["status"], "needs_revision")
        self.assertIn("irrelevant_related_pages", result["flags"])

    def test_score_inconsistency_is_flagged(self) -> None:
        output = high_quality_output()
        output["novelty_score"] = 0.95
        output["cross_niche_implications"] = [
            "AI: inspect whether this tag contributes mechanism, market context, risk, or distribution leverage."
        ]

        result = evaluate_semantic_quality(output, self.parent_a, self.parent_b)

        self.assertEqual(result["status"], "needs_revision")
        self.assertIn("score_inconsistency", result["flags"])


if __name__ == "__main__":
    unittest.main()
