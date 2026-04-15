import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from combination_providers import migrate_legacy_output, select_provider_config, validate_output


def valid_payload() -> dict:
    return {
        "draft_title": "Agentic AI x Business Model Design",
        "draft_summary": "Speculative synthesis.",
        "fusion_summary": "A concise fusion.",
        "mechanistic_interaction": "Agent loops change activity-system feedback latency.",
        "product_opportunity": "A narrow workflow audit for founder operating loops.",
        "system_design": "Canonical inputs remain fixed while drafts stay reviewable.",
        "research_question": "Does this improve a real operating decision?",
        "falsification_test": "The fusion fails if no user changes a decision after using it.",
        "non_obviousness_reason": "It links agent feedback loops to business-model activity constraints.",
        "primary_bottleneck": "The workflow must be narrow enough to validate.",
        "specific_user_or_buyer": "Seed-stage founder with a complex operating cadence.",
        "novelty_score": 0.7,
        "plausibility_score": 0.6,
        "promotion_readiness": "medium",
        "interaction_type": "mechanistic",
        "grounded_points": ["Agentic AI is one parent.", "Business Model Design is the other parent."],
        "speculative_extensions": ["Agent feedback loops may change business-model redesign cadence."],
        "evidence_needed_before_promotion": ["Decision logs showing a changed operating choice."],
        "cross_niche_implications": ["AI: agent loops become business-model components."],
        "failure_modes": ["Overbroad platform framing."],
        "related_canonical_pages": ["wiki/startups/business-model-design.md"],
        "tags": ["ai", "startups", "cross-niche"],
    }


class CombinationProviderValidationTests(unittest.TestCase):
    def test_valid_output_object_passes(self) -> None:
        output = validate_output(valid_payload())

        self.assertEqual(output["interaction_type"], "mechanistic")
        self.assertEqual(output["promotion_readiness"], "medium")
        self.assertEqual(output["novelty_score"], 0.7)
        self.assertEqual(output["plausibility_score"], 0.6)

    def test_invalid_interaction_type_fails(self) -> None:
        payload = valid_payload()
        payload["interaction_type"] = "vibes"

        with self.assertRaisesRegex(ValueError, "interaction_type"):
            validate_output(payload)

    def test_invalid_promotion_readiness_fails(self) -> None:
        payload = valid_payload()
        payload["promotion_readiness"] = "ready"

        with self.assertRaisesRegex(ValueError, "promotion_readiness"):
            validate_output(payload)

    def test_missing_new_field_fails(self) -> None:
        payload = valid_payload()
        del payload["non_obviousness_reason"]

        with self.assertRaisesRegex(ValueError, "non_obviousness_reason"):
            validate_output(payload)

    def test_malformed_score_values_fail(self) -> None:
        payload = valid_payload()
        payload["novelty_score"] = 1.4

        with self.assertRaisesRegex(ValueError, "between 0.0 and 1.0"):
            validate_output(payload)

        payload = valid_payload()
        payload["plausibility_score"] = "high"

        with self.assertRaisesRegex(ValueError, "numeric"):
            validate_output(payload)

    def test_legacy_migration_is_explicit(self) -> None:
        payload = valid_payload()
        for field in [
            "non_obviousness_reason",
            "primary_bottleneck",
            "specific_user_or_buyer",
            "novelty_score",
            "plausibility_score",
            "promotion_readiness",
            "interaction_type",
            "grounded_points",
            "speculative_extensions",
            "evidence_needed_before_promotion",
        ]:
            del payload[field]

        with self.assertRaises(ValueError):
            validate_output(payload)

        migrated = migrate_legacy_output(payload)
        self.assertEqual(migrated["promotion_readiness"], "low")
        self.assertEqual(migrated["interaction_type"], "epistemic")
        self.assertIn("human review", migrated["evidence_needed_before_promotion"][0])

    @patch("combination_providers.cursor_agent_is_available", return_value=False)
    def test_provider_auto_detects_openai_key(self, _cursor_available) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}, clear=True):
                config, source = select_provider_config(Path(tmp))

        self.assertEqual(config["type"], "openai")
        self.assertEqual(config["api_key_env"], "OPENAI_API_KEY")
        self.assertIn("OPENAI_API_KEY", source)


if __name__ == "__main__":
    unittest.main()
