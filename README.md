# LLM Wiki Combine

Local-first tooling for generating speculative combination drafts from two canonical pages in a markdown LLM Wiki.

The combine engine reads two canonical parent pages, extracts structured fields, scores the pair, asks a pluggable synthesis provider for strict JSON, validates the output, runs a deterministic semantic gate, then renders a draft under `wiki/combinations/drafts/`. Canonical pages are not edited during draft generation.

## Quickstart

1. Install the command from the cloned repo:

   ```bash
   python -m pip install -e .
   ```

2. From a wiki project root that contains `wiki/`, check setup:

   ```bash
   wiki-combine --doctor
   ```

3. Combine two canonical pages:

   ```bash
   wiki-combine ai/agentic-ai startups/business-model-design
   ```

The draft appears in `wiki/combinations/drafts/`. The command also updates `wiki/combinations/index.md`, `wiki/index.md`, and `wiki/log.md` when those files exist.

For a deterministic dry run without an LLM provider:

```bash
wiki-combine --provider local-model ai/agentic-ai startups/business-model-design
```

## What This Adds

This repo adds a disciplined combination layer on top of an existing markdown LLM Wiki:

- deterministic parent extraction
- pre-synthesis pair scoring
- provider-pluggable structured synthesis
- strict JSON validation
- semantic rejection before save
- deterministic markdown rendering and index/log updates

## Canonical vs Draft Safety

Draft generation only writes to combination draft and tracking files:

- `wiki/combinations/drafts/`
- `wiki/combinations/index.md`
- `wiki/index.md`
- `wiki/log.md`

Canonical pages are read as inputs and remain unchanged. A draft becomes canonical only through the separate promotion workflow.

## Providers

Provider selection order:

1. `combine.config.json` or `--provider`
2. Cursor Agent compatible local wrapper, when detected
3. `OPENAI_API_KEY`
4. `ANTHROPIC_API_KEY`
5. helpful setup failure

Copy the template and edit one provider block:

```bash
cp combine.config.example.json combine.config.json
```

Common choices:

```json
{
  "combine_provider": {
    "type": "openai",
    "model": "gpt-4.1-mini",
    "api_key_env": "OPENAI_API_KEY"
  }
}
```

```json
{
  "combine_provider": {
    "type": "external-command",
    "command": "my-agent-wrapper combine",
    "timeout_seconds": 180
  }
}
```

```json
{
  "combine_provider": {
    "type": "local-model",
    "endpoint": "http://127.0.0.1:11434/v1/chat/completions",
    "model": "local-combine"
  }
}
```

## Examples

Run setup checks:

```bash
wiki-combine --doctor
```

Combine two pages from another wiki root:

```bash
wiki-combine --root /path/to/my-wiki ai/agentic-ai startups/business-model-design
```

Override provider for one run:

```bash
wiki-combine --provider openai ai/agentic-ai startups/business-model-design
```

Emit JSON for local agents:

```bash
wiki-combine --json ai/agentic-ai startups/business-model-design
```

Inspect the generated draft:

```bash
ls wiki/combinations/drafts/
```
