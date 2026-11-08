# Australian Writing MCP

An [MCP](https://modelcontextprotocol.io) server that gives any LLM client
(Claude, ChatGPT, Copilot, local models) three **deterministic** content-quality
checks for Australian English writing:

| Tool | Purpose |
| --- | --- |
| `check_spelling` | Enforce Australian English spelling (color → colour, organize → organise) and flag genuine misspellings. |
| `check_grammar` | Rule-based grammar, punctuation and usage checks. |
| `get_reading_level` | Reading age / grade level mapped to the Australian school year. |

All checks are deterministic and run fully offline — the same input always
produces the same output, with no network calls or LLM inference.

## How it works

- **Spelling** — the bundled [en_AU Hunspell dictionary](src/australian_writing/dictionaries/en_AU)
  (~50k entries) is the source of truth, read with the pure-Python
  [`spylls`](https://github.com/zverok/spylls) engine. American spellings are
  labelled `americanism` (via a curated map + `-ize`/`-yze` suffix rules, each
  verified against the dictionary); other unknown words are labelled
  `misspelling`. Both come with suggestions.
- **Grammar** — three layers: (1) 400+ curated phrase corrections (idioms,
  eggcorns, usage errors) and (2) dialect-aware `a`/`an` detection, both ported
  from [Harper](https://github.com/Automattic/harper) (Apache-2.0; see
  [NOTICE](NOTICE)), plus (3) high-precision mechanical rules for repeated words,
  spacing, punctuation, capitalisation and `could of` → `could have`. It is
  rule/data-driven, not a statistical parser (see [ASSESSMENT.md](ASSESSMENT.md)).
- **Reading level** — [`textstat`](https://github.com/textstat/textstat)
  computes the Flesch-Kincaid grade, which is mapped to an Australian year level
  (Foundation → Year 12 → Tertiary) and an approximate reading age.

## Install

```bash
cd mcp-servers/australian-writing-mcp
uv venv && source .venv/bin/activate
uv pip install -e .
```

(Or `pip install -e .`.)

## Run

```bash
python -m australian_writing.server          # stdio (local client spawns it)
python -m australian_writing.server --http   # streamable-HTTP on 0.0.0.0:8000/mcp
```

The `--http` mode (also enabled by `MCP_TRANSPORT=http`) serves stateless
streamable-HTTP and honours `HOST`/`PORT`. It's the form managed MCP hosts
require — see [deploy/aws](deploy/aws/README.md) for AWS Bedrock AgentCore
Runtime (Docker image included).

### Register with Claude Code / Claude Desktop

```json
{
  "mcpServers": {
    "australian-writing": {
      "command": "python",
      "args": ["-m", "australian_writing.server"],
      "cwd": "/path/to/civic-lab/mcp-servers/australian-writing-mcp",
      "env": { "PYTHONPATH": "src" }
    }
  }
}
```

## Example output

`check_spelling("The color of our neighbourhood.")`

```json
{
  "ok": false,
  "issue_count": 1,
  "issues": [
    {
      "word": "color",
      "offset": 4,
      "category": "americanism",
      "suggestions": ["colour"],
      "message": "American spelling; use Australian 'colour'."
    }
  ]
}
```

`get_reading_level("The cat sat on the mat. We had fun.")`

```json
{
  "australian_year_level": "Foundation (Prep/Kindergarten)",
  "reading_age_years": 5,
  "flesch_kincaid_grade": -1.4,
  "flesch_reading_ease": 116.1,
  "metrics": { "sentences": 2, "words": 9, "syllables": 9 }
}
```

## Tests

```bash
pip install -e ".[dev]"
pytest
```

## Licensing

This MCP server is part of [civic-lab](../../) and is licensed under the
Apache License 2.0. It bundles and ports third-party work under permissive
terms — see [NOTICE](NOTICE) for the Harper attribution. The bundled en_AU
dictionary is distributed under its original SCOWL-derived permissive terms;
see [LICENSE](src/australian_writing/dictionaries/en_AU/LICENSE).
