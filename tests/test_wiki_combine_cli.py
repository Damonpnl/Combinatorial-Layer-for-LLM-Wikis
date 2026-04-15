import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "wiki-combine.py"


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def seed_wiki(root: Path) -> None:
    write(
        root / "wiki" / "index.md",
        """---
title: "Index"
summary: "Test index. 31 sources, 2 pages."
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
        root / "wiki" / "log.md",
        """---
title: "Log"
type: output
status: final
---

# Log
""",
    )
    write(
        root / "wiki" / "combinations" / "index.md",
        """---
title: "Combination Lab"
type: hub
status: final
---

# Combination Lab

| Draft | Parents | Promotion State |
|---|---|---|
""",
    )
    write(
        root / "wiki" / "ai" / "agentic-ai.md",
        """---
title: "Agentic AI"
summary: "Agents use tools and planning loops."
tags: [ai]
type: concept
status: final
---

# Agentic AI

Links to [[startups/business-model-design]].
""",
    )
    write(
        root / "wiki" / "startups" / "business-model-design.md",
        """---
title: "Business Model Design"
summary: "Activity systems create and capture value."
tags: [startups]
type: concept
status: final
---

# Business Model Design

Links to [[ai/agentic-ai]].
""",
    )


class WikiCombineCliTests(unittest.TestCase):
    def test_cli_json_success_smoke(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            seed_wiki(root)

            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--root",
                    str(root),
                    "--provider",
                    "local-model",
                    "--json",
                    "ai/agentic-ai",
                    "startups/business-model-design",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["status"], "created")
            self.assertTrue(payload["draft_path"].startswith("wiki/combinations/drafts/"))
            self.assertEqual(payload["semantic_gate"]["status"], "accept")

    def test_cli_json_blocked_smoke(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            seed_wiki(root)
            write(
                root / "combine.config.json",
                """{
  "pair_scoring": {
    "score_threshold": 0.99,
    "block_low_score": true
  },
  "cache": {
    "enabled": true
  }
}
""",
            )

            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--root",
                    str(root),
                    "--provider",
                    "local-model",
                    "--json",
                    "ai/agentic-ai",
                    "startups/business-model-design",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )

            self.assertEqual(completed.returncode, 2)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["status"], "blocked")
            self.assertIn("Pair score", payload["error"])

    def test_cli_doctor_json_smoke(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            seed_wiki(root)
            (root / "wiki" / "combinations" / "drafts").mkdir(parents=True, exist_ok=True)

            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--root",
                    str(root),
                    "--provider",
                    "local-model",
                    "--doctor",
                    "--json",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertIn(payload["status"], {"ok", "warning"})
            self.assertTrue(any(check["name"] == "provider selected" for check in payload["checks"]))


if __name__ == "__main__":
    unittest.main()
