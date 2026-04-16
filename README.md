# Combinatorial Layer for LLM Wikis

Turn a source-grounded markdown LLM wiki into a disciplined speculative idea engine.

This project sits on top of a local, markdown-first LLM Wiki and adds a safe, structured combine workflow:

- pick two canonical wiki pages
- extract mechanisms, incentives, actors, risks, links, and synthesis-ready fields
- score whether the pair is worth combining
- ask a pluggable synthesis provider for strict JSON
- validate the output and run a deterministic semantic gate
- save the result as a draft without contaminating canonical knowledge
- optionally submit strong drafts for promotion later

It is designed for local-first workflows with tools such as Cursor, Claude Code, API providers, or local model wrappers. It is not a hosted SaaS system.

---

## What This Adds

A standard LLM wiki is good at:

- ingesting source material
- building canonical concept pages
- cross-linking concepts
- answering questions from grounded notes

This layer adds:

- combinations of canonical pages into speculative syntheses
- draft/canonical separation so exploration does not pollute grounded knowledge
- pair scoring to prioritize high-tension, high-potential combinations
- strict structured outputs from the synthesis provider
- semantic gating to reject weak, generic, or contradictory drafts
- explicit interaction boundaries, evidence gaps, and promotion readiness
- a promotion workflow for moving strong drafts into canonical content later

The result is a system for generating product opportunities, cross-domain hypotheses, research questions, strategic frameworks, and non-obvious concept bridges.

---

## Core Idea

Canonical wiki pages remain the grounded layer.

Combination drafts are speculative and separate.

Promotion is explicit.

The system creates a disciplined path from:

```text
source-backed knowledge -> structured recombination -> draft hypothesis -> optional promotion
```

It is not trying to turn every generated idea into truth. It is trying to make speculation useful without letting it contaminate the canonical layer.

---

## Repository Model

This project assumes a markdown-first wiki project with a `wiki/` folder and canonical pages that use YAML frontmatter. Canonical pages can live in any domain folders you maintain, for example `wiki/ai/`, `wiki/markets/`, `wiki/philosophies/`, or your own categories.

The reusable layer expects or creates drafts around this structure:

```text
wiki/
  index.md
  log.md
  combinations/
    index.md
    drafts/
    cache/
    diagnostics/
  promotion-queue/
    pending/
    approved/
    rejected/
```

Your actual wiki content is not part of this package. This repo contains only the combination engine and supporting interfaces.

---

## Quickstart

### 1. Clone and install

```bash
git clone https://github.com/Damonpnl/Combinatorial-Layer-for-LLM-Wikis.git
cd Combinatorial-Layer-for-LLM-Wikis
python -m pip install -e .
```

### 2. Check setup from your wiki root

From a project that contains `wiki/`:

```bash
wiki-combine --doctor
```

Or point at a wiki explicitly:

```bash
wiki-combine --root /path/to/my-wiki --doctor
```

### 3. Combine two pages

```bash
wiki-combine ai/prompt-engineering ai/rag
```

You can also pass full markdown paths:

```bash
wiki-combine wiki/ai/prompt-engineering.md wiki/ai/rag.md
```

The draft appears under:

```text
wiki/combinations/drafts/
```

When the tracking files exist, the deterministic writer also updates:

```text
wiki/combinations/index.md
wiki/index.md
wiki/log.md
```

For a deterministic dry run without an LLM provider:

```bash
wiki-combine --provider local-model ai/prompt-engineering ai/rag
```

---

## CLI

Primary command:

```bash
wiki-combine <left-page> <right-page>
```

Useful options:

```bash
wiki-combine --doctor
wiki-combine --json <left-page> <right-page>
wiki-combine --root /path/to/wiki-root <left-page> <right-page>
wiki-combine --config /path/to/combine.config.json <left-page> <right-page>
wiki-combine --provider external-command|openai|anthropic|local-model <left-page> <right-page>
```

Examples:

```bash
wiki-combine markets/price-mechanism biohacking/peptide-therapeutics-overview
wiki-combine --provider openai philosophies/game-theory psychology/analogical-reasoning
wiki-combine --json ai/rag biohacking/default-mode-network
```

---

## Provider Model

The project is provider-pluggable.

The deterministic layer owns reading, extraction, scoring, validation, rendering, and writes. The provider only returns structured synthesis JSON.

Supported provider types:

- `external-command`
- `openai`
- `anthropic`
- `local-model`

Provider selection order:

1. explicit `--provider`, `WIKI_COMBINE_PROVIDER`, or `combine.config.json`
2. detected Cursor Agent compatible local wrapper
3. `OPENAI_API_KEY`
4. `ANTHROPIC_API_KEY`
5. clear actionable setup failure

Copy the template and edit one provider block:

```bash
cp combine.config.example.json combine.config.json
```

External command example:

```json
{
  "combine_provider": {
    "type": "external-command",
    "command": "python ./cursor_combine_provider.py",
    "timeout_seconds": 300
  }
}
```

OpenAI example:

```json
{
  "combine_provider": {
    "type": "openai",
    "model": "gpt-4.1-mini",
    "api_key_env": "OPENAI_API_KEY",
    "timeout_seconds": 180
  }
}
```

OpenAI-compatible local endpoint example:

```json
{
  "combine_provider": {
    "type": "local-model",
    "endpoint": "http://127.0.0.1:11434/v1/chat/completions",
    "model": "local-combine",
    "timeout_seconds": 180
  }
}
```

---

## How It Works

1. You select two canonical pages.
2. The service resolves both pages and extracts deterministic fields such as title, summary, tags, type, status, mechanisms, incentives, actors, risks, linked concepts, cross-niche implications, certainty, bottlenecks, and body text.
3. The pair scorer estimates whether the pair has useful tension.
4. The configured synthesis provider receives structured input and returns strict JSON.
5. The output is validated against the required schema.
6. The semantic gate can reject or mark weak outputs for revision.
7. Markdown is rendered deterministically.
8. The draft is saved under `wiki/combinations/drafts/`.
9. Index and log files are updated by the deterministic writer when present.

The provider does not free-roam the repo and does not write files.

---

## Output Schema

The synthesis provider must return strict JSON only. Required fields include:

- `draft_title`
- `draft_summary`
- `fusion_summary`
- `mechanistic_interaction`
- `product_opportunity`
- `system_design`
- `research_question`
- `falsification_test`
- `non_obviousness_reason`
- `primary_bottleneck`
- `specific_user_or_buyer`
- `interaction_type`
- `novelty_score`
- `plausibility_score`
- `promotion_readiness`
- `grounded_points`
- `speculative_extensions`
- `evidence_needed_before_promotion`
- `cross_niche_implications`
- `failure_modes`
- `related_canonical_pages`
- `tags`

`interaction_type` must be one of:

```text
mechanistic, analogical, strategic, market_structural, epistemic
```

`promotion_readiness` must be one of:

```text
low, medium, high
```

---

## Draft Format

Combination drafts are written as markdown under `wiki/combinations/drafts/`.

They include draft-only lineage fields such as:

```yaml
origin: combination
parents:
  - wiki/path/to/parent-a.md
  - wiki/path/to/parent-b.md
promotion_state: not-submitted
combination_mode: canonical-canonical
```

Typical sections include:

- Fusion Summary
- Interaction Boundary
- Mechanistic Interaction
- Product Opportunity
- Non-Obviousness Reason
- Primary Bottleneck
- Specific User Or Buyer
- Grounded Points
- Speculative Extensions
- Evidence Needed Before Promotion
- System Design
- Research Question
- Falsification Test
- Cross-Niche Implications
- Failure Modes
- Related Canonical Pages

---

## Safety Rules

The system should never:

- edit canonical parent pages during draft generation
- create unresolved related-page wikilinks intentionally
- present speculative combinations as established fact
- allow the provider to write directly into the repo
- auto-promote a draft into canonical content

The system should always:

- preserve lineage
- keep canonical vs draft separation
- validate structured output
- reject weak or generic drafts when appropriate
- label analogical or epistemic interactions clearly
- surface evidence gaps before promotion

This is especially important in high-risk domains such as biotech, finance, medicine, law, and geopolitics.

---

## Promotion Workflow

Drafts are not canonical.

Promotion is explicit:

1. generate a draft in `wiki/combinations/drafts/`
2. review and edit if needed
3. submit to `wiki/promotion-queue/pending/`
4. approve or reject
5. only then promote into canonical wiki content

This preserves provenance and prevents speculative output from contaminating grounded knowledge.

---

## Local-Agent Usage

Local agents should invoke the tool layer rather than bypassing it.

Python wrappers are available in `combination_tools.py`:

- `combine_pages`
- `list_canonical_pages`
- `doctor_check`
- `submit_promotion`

The CLI can also emit JSON for agents:

```bash
wiki-combine --json ai/rag biohacking/default-mode-network
```

---

## Troubleshooting

### Provider not found

Run:

```bash
wiki-combine --doctor
```

Then configure `external-command`, install the local provider wrapper, set an API key, or use `--provider local-model` for a dry run.

### Invalid page path

Make sure the page exists under `wiki/` and is not inside excluded folders such as `wiki/sources/`, `wiki/combinations/`, or `wiki/promotion-queue/`.

### Output rejected by semantic gate

That usually means the output was too generic, too broad, contradictory, or failed specificity checks.

Try a higher-tension pair, cleaner canonical pages, or a different provider.

### Draft created but weak

That usually points to a low-tension pair, weak parent extraction, provider prompt drift, or semantic gate thresholds that are too soft.

---

## Why This Is Different From Plain RAG

This is not just "ask an LLM to combine two notes."

The difference is the discipline layer:

- source-backed canonical pages
- deterministic extraction
- pair scoring
- structured synthesis
- strict validation
- semantic rejection
- deterministic rendering
- explicit epistemic boundaries
- promotion workflow

That is what lets the system generate bold ideas without pretending speculation is truth.

---

## Roadmap

Possible next improvements:

- curated example set that contains no private wiki content
- optional live provider doctor check
- richer pair recommendation UI
- MCP server wrapper around the existing tool layer
- optional post-generation critique pass

---

## Contributing

If you extend this system, preserve the core invariants:

- deterministic write path
- canonical/draft separation
- no direct provider file writes
- strict output validation
- semantic gate before save
- explicit interaction-type labeling
- evidence-gap surfacing
- promotion before canonical inclusion

Do not trade rigor for novelty.

---

## License

MIT License
