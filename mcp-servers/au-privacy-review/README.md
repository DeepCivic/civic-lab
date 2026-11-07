# au-privacy-review

An [MCP](https://modelcontextprotocol.io) server that reviews an Australian project for privacy issues
under the Australian Privacy Principles (APPs). It works like a static analyser for privacy. It reads
the code, infrastructure configuration and design documents, and any facts your assistant records from
other material. Then it tells you three things:

- **what looks wrong, ranked by how sure it can be.** Each finding is ranked on whether a regulator or
  tribunal has already decided against similar facts;
- **what is still unknown**, and what evidence would settle each open question;
- **where a privacy threshold assessment would land**, and a draft of the record when you need one.

Use it to review a project before a privacy impact assessment (PIA), to gate pull requests, or to
draft the threshold assessment itself.

> **Read this first.** This is decision support, not legal advice, and not an official tool. It is not
> affiliated with or endorsed by the OAIC, any court or tribunal, or the Commonwealth.
> It covers **Commonwealth law only** (the Privacy Act 1988 and a few related Acts), not state or
> territory privacy law. It sees what the code *can* do and what documents *say*, not what happens in
> production. Every finding says what to confirm before you rely on it. See
> [What you can rely on](#what-you-can-rely-on).

## What a review looks like

Abridged output for the deliberately bad project in `tests/fixtures/bad`:

```text
3 critical, 6 high, 23 caution; 6 open question(s), 5 high priority.

## Critical
- F001 Third-party advertising or conversion pixel ... web/book.html:2 (APP 3.3)
  - Resembles: Advertising pixels in a health or other sensitive setting.
    Monash IVF [2026] AICmr 40; Medmate [2026] AICmr 41
  - Confirm: Is consent obtained before the pixel fires (not just a banner)?

## High
- F004 Infrastructure configuration makes storage or a database publicly accessible. infra/main.tf:2 (APP 11.1(b))

## Caution
- F011 Multi-factor authentication explicitly disabled. infra/main.tf:3 (APP 11.1)
  - Confirm: Is MFA enforced for every remote and privileged path to personal information?

## Open questions
- [high] Will it handle personal information about a large number of people ...?
  - Why: A yes on its own points to a full PIA.
  - Evidence that would settle it: Expected numbers of people and records ... Business case or capacity planning.
```

| Level | Meaning |
| --- | --- |
| **critical** | The facts resemble a decided case that went against the entity, and that decision is final. |
| **high** | Reads as an APP contravention if the facts are as they appear. |
| **caution** | Not enough information to say, but this may be a privacy issue. |

Every finding links to the law and the decisions behind it. Every quotation is checked word for word
against its source.

## Quick start

You need [uv](https://docs.astral.sh/uv/). `uvx` fetches and runs the server; there is no install step.

**Claude Desktop / Claude Code** (`mcpServers`):

```json
{
  "mcpServers": {
    "privacy": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/DeepCivic/civic-lab#subdirectory=mcp-servers/au-privacy-review",
               "au-privacy-review"]
    }
  }
}
```

**VS Code** (`.vscode/mcp.json`): the same `command` and `args` under `"servers"`.

Then ask your assistant something like:

> Review /path/to/my-project for privacy issues. The design documents are in /path/to/my-project/docs.

Or use the `privacy_review` prompt, which runs the whole workflow.

## How it works

1. **Review.** `review_project` scans the repository and any documents you point it at. It needs no
   answers from anyone.
2. **Read what the scanner cannot.** The scanner lists PDFs and Word files it could not read, and points
   at passages in documents that need a human (or your assistant) to read them. Your assistant records
   what it establishes as **observations**, each with its source:

   ```json
   {"kind": "large_scale", "fact": "About 2 million customers nationally", "source": "docs/business-case.pdf p 4"}
   ```

3. **Review again.** Observations answer the open questions they bear on. Some can raise a critical
   finding. For example, "faces matched against a watchlist" resembles 7-Eleven and Clearview.
4. **Ask only what is left.** Open questions are ranked. Your assistant asks you only the ones it could
   not settle from the material.
5. **Draft the threshold assessment** with `threshold_assessment` when the team is ready to complete one.

The details are in [docs/using-the-review.md](docs/using-the-review.md).

## Tools

| Tool | Use it to |
| --- | --- |
| `review_project` | **Start here.** Review code, documents and observations: findings by level, open questions, what was examined, threshold readiness. |
| `interrogate` | Dig into one finding, question, observation kind or rule: the evidence for and against, and what would settle it. |
| `list_observation_kinds` | See what facts can be recorded, and what to look for in documents. |
| `threshold_assessment` | Draft the privacy threshold assessment record from the same evidence. |
| `list_threshold_questions` | See the 17 threshold questions and the evidence that settles each. |
| `assess_applicability` | Check whether the APPs are likely to bind the entity (small business exemption, Digital ID Act). |
| `get_entry`, `get_app`, `get_authority`, `list_entries`, `search_kb` | Read the rules, the APP text, and the decisions behind them. |
| `scan_repository` | Raw detector output, if you want the signals without the levels. |
| `probe_deployment` | **Off by default; makes network requests.** Check a live site for trackers and its privacy policy. |
| `kb_status` | What the knowledge base contains, how current it is, and its known limits. |

Prompts: `privacy_review` (review a project) and `privacy_threshold_assessment` (draft the record).

## Docker

The image runs the same server. Mount the project to review at `/work` and ask for a review of `/work`.
The server can read nothing else.

```json
{
  "mcpServers": {
    "privacy": {
      "command": "docker",
      "args": ["run", "-i", "--rm", "-v", "/path/to/my-project:/work:ro", "ghcr.io/deepcivic/au-privacy-review"]
    }
  }
}
```

```bash
docker run --rm -v "$PWD":/work:ro ghcr.io/deepcivic/au-privacy-review review /work --fail-on high
```

The image is published when a release is tagged. Until then, build it locally with
`docker build -t au-privacy-review .`.

## Configuration

The server is isolated by default. It reads only the paths you give it and makes no network calls.

| Setting | Effect |
| --- | --- |
| `AU_PRIVACY_REVIEW_ROOTS` (path list) or `serve --root DIR` | Only these directories may be read. Required for HTTP mode. |
| `AU_PRIVACY_REVIEW_LIVE=1` or `serve --allow-live` | Enables `probe_deployment`, which fetches the page you name and its privacy policy. |
| `serve --http [--host H --port P]` | Streamable HTTP at `/mcp`. Refuses to start without roots, because it reads files for remote clients. |

## Command line and CI

```bash
au-privacy-review review path/to/repo --doc path/to/docs --out review.md
au-privacy-review review path/to/repo --fail-on high       # exit 1 on any high or critical finding
au-privacy-review threshold path/to/repo --observations obs.json --out threshold.md
au-privacy-review kinds | questions | status
```

To silence a finding you have checked, put `privacy-review: ignore` on the line, or
`privacy-review: ignore-file` anywhere in a file.

## What you can rely on

**What it is good at:** finding the things a privacy reviewer would want to know about early: tracking
pixels, biometrics, sensitive fields, overseas recipients, weak security settings, missing notices and
policies. It ties each one to the APP it bears on and to decisions with similar facts. It is careful
not to claim more than it saw. A question is "not detected" only if the scanner actually examined the
material where the answer would show up.

**What it cannot do:**

- **Decide whether the law was broken.** A critical finding means the facts *resemble* a case that was
  lost. The listed distinguishing facts decide whether they really match, and the scan usually cannot see
  them.
- **Assess state or territory law.** State and territory agencies, and private health providers in some
  states, have obligations it does not cover. `assess_applicability` says so.
- **See production, contracts or what people were told.** Code shows capability; documents show intent.
- **Understand documents.** It matches phrases to point at passages. Facts come from observations that a
  person or assistant records.
- **Read PDFs or Office files.** It lists them so they are not silently missed.
- **Know the latest law.** Legislation is as at 7 November 2026. Court and tribunal decisions come from
  the Open Australian Legal Corpus (to March 2025) plus OAIC publications to November 2026. Some
  authorities are on review, varied, or allegations only, and the output says so.

The knowledge base, its sources and its known gaps are described in
[docs/sources-and-limits.md](docs/sources-and-limits.md).

## Documentation

- [Using the review](docs/using-the-review.md): levels, open questions, documents and observations, `interrogate`, CI.
- [Findings reference](docs/findings-reference.md): the decided-case patterns, rules and heuristics, what the scanner detects and how it stays quiet.
- [Threshold assessment](docs/threshold-assessment.md): the 17 questions, outcomes, agencies, Digital ID and SOCI.
- [Sources and limits](docs/sources-and-limits.md): what the knowledge base contains, how current it is, and what it does not cover.
- [CHANGELOG](CHANGELOG.md).
- [RESEARCH.md](RESEARCH.md): what the knowledge base contains, where it came from, how it was built and checked, and the technologies used.

## Licence

Apache-2.0. Bundled legal text and quotations carry their own terms; see [NOTICE](NOTICE).
