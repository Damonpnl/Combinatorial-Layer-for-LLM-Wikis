import unittest

from pair_scorer import score_pair


def page(
    path: str,
    title: str,
    tags: list[str],
    page_type: str = "concept",
    status: str = "final",
    mechanisms: list[str] | None = None,
    links: list[str] | None = None,
    summary: str | None = None,
) -> dict:
    return {
        "path": path,
        "title": title,
        "summary": summary or title,
        "tags": tags,
        "type": page_type,
        "status": status,
        "mechanisms": mechanisms or [],
        "incentives": [],
        "actors": [],
        "risks": [],
        "linked_concepts": links or [],
        "cross_niche_implications": [],
    }


class PairScorerTests(unittest.TestCase):
    def test_same_domain_low_tension_pair_scores_low(self) -> None:
        left = page(
            "wiki/ai/agentic-ai.md",
            "Agentic AI",
            ["ai"],
            mechanisms=["agents use tools loops planning"],
            links=["ai/rag"],
        )
        right = page(
            "wiki/ai/react-pattern.md",
            "ReAct Pattern",
            ["ai"],
            mechanisms=["agents use tools loops reasoning"],
            links=["ai/rag"],
        )

        score = score_pair(left, right)

        self.assertLess(score["overall_score"], 0.25)
        self.assertEqual(score["domain_distance"], 0.0)
        self.assertGreaterEqual(score["overlap_penalty"], 0.65)

    def test_cross_domain_high_tension_pair_scores_high(self) -> None:
        left = page(
            "wiki/ai/agentic-ai.md",
            "Agentic AI",
            ["ai"],
            mechanisms=["agents use tools loops planning"],
            links=["ai/rag"],
        )
        right = page(
            "wiki/biohacking/bpc-157.md",
            "BPC-157",
            ["biohacking"],
            page_type="protocol",
            mechanisms=["peptide tissue repair angiogenesis inflammation"],
            links=["biohacking/peptide-therapeutics-overview"],
        )

        score = score_pair(left, right)

        self.assertGreater(score["overall_score"], 0.7)
        self.assertEqual(score["domain_distance"], 1.0)
        self.assertEqual(score["mechanism_difference"], 1.0)

    def test_high_overlap_penalty_reduces_score(self) -> None:
        left = page(
            "wiki/ai/agentic-ai.md",
            "Agentic AI",
            ["ai"],
            mechanisms=["agents use tools loops planning"],
            links=["ai/rag", "ai/prompt-engineering"],
            summary="Agents use tools and planning loops.",
        )
        right = page(
            "wiki/ai/agentic-ai-copy.md",
            "Agentic AI Systems",
            ["ai"],
            mechanisms=["agents use tools loops planning"],
            links=["ai/rag", "ai/prompt-engineering"],
            summary="Agents use tools and planning loops.",
        )

        score = score_pair(left, right)

        self.assertEqual(score["overlap_penalty"], 1.0)
        self.assertLess(score["overall_score"], 0.1)

    def test_scoring_is_deterministic(self) -> None:
        left = page(
            "wiki/startups/business-model-design.md",
            "Business Model Design",
            ["startups", "markets"],
            mechanisms=["activity systems create and capture value"],
        )
        right = page(
            "wiki/politics/cognitive-warfare.md",
            "Cognitive Warfare",
            ["politics", "social-media"],
            mechanisms=["narratives shape perception coordination and legitimacy"],
        )

        self.assertEqual(score_pair(left, right), score_pair(left, right))


if __name__ == "__main__":
    unittest.main()
