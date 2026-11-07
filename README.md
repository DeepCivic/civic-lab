# civic-lab

A collection of tools, skills, and utilities used in DeepCivic development.

This repository is a monorepo that grows over time. It currently holds two
kinds of artifact:

## `skills/`

Reusable [agent skills](https://modelcontextprotocol.io), one directory per
skill with a `SKILL.md` definition, for drafting and reviewing work in
Australian Government and go-to-market contexts:

| Skill | Purpose |
| --- | --- |
| [au-gov-email-letter](skills/au-gov-email-letter/SKILL.md) | Draft or review emails/letters in Australian Government style. |
| [au-gov-formal-writing](skills/au-gov-formal-writing/SKILL.md) | Draft or review formal Australian Government content using formal tone, per the Style Manual. |
| [au-gov-report](skills/au-gov-report/SKILL.md) | Draft or review internal reports in Australian Government style. |
| [gtm-adoption-assumptions](skills/gtm-adoption-assumptions/SKILL.md) | Develop go-to-market and adoption assumptions for a product or service. |
| [maturity-model-architect](skills/maturity-model-architect/SKILL.md) | Collaboratively build a capability maturity model from one or more datasets. |
| [oss-assessment](skills/oss-assessment/SKILL.md) | Evidence-first assessment of an OSS repository against the DPG Standard and OpenSSF guide, with emphasis on architecture and code. |
| [oss-solution-architect](skills/oss-solution-architect/SKILL.md) | Turn requirements into an annotated OSS-based architecture with open decisions and a backlog. |

## `mcp-servers/`

[Model Context Protocol](https://modelcontextprotocol.io) servers.

| Server | Purpose |
| --- | --- |
| [abr-mcp](mcp-servers/abr-mcp/) | Australian Business Register (ABN Lookup) data: offline ABN/ACN validation, a local bulk-extract index, and optional live ABR web services. |
| [australian-writing-mcp](mcp-servers/australian-writing-mcp/) | Deterministic Australian English writing checks: spelling, grammar, and reading level. |

Each server is an independent Python package (its own `pyproject.toml`),
released on its own, in the same way as
[modelcontextprotocol/servers](https://github.com/modelcontextprotocol/servers):

- **CI** ([mcp-servers.yml](.github/workflows/mcp-servers.yml)) discovers
  every `mcp-servers/*/pyproject.toml`. It tests each package on Linux, macOS
  and Windows, on the current stable Python, the only version supported. It
  also launches each server over stdio and lists its tools.
- **Releases** ([mcp-release.yml](.github/workflows/mcp-release.yml)) run
  when you push a `<package>-v<version>` tag. A package with a `Dockerfile`
  publishes its image to ghcr.io, and one with a `server.json` publishes to
  the MCP Registry. PyPI is opt-in: only a package whose `server.json` lists
  a PyPI package is published there, and none currently do.

## Repository layout

```
civic-lab/
├── .github/                        # CI + per-package release workflows
├── skills/                         # One directory per skill, each with a SKILL.md
│   ├── au-gov-email-letter/
│   │   └── SKILL.md
│   ├── au-gov-formal-writing/
│   │   └── SKILL.md
│   ├── au-gov-report/
│   │   └── SKILL.md
│   ├── gtm-adoption-assumptions/
│   │   └── SKILL.md
│   ├── maturity-model-architect/
│   │   └── SKILL.md
│   ├── oss-assessment/
│   │   └── SKILL.md
│   └── oss-solution-architect/
│       └── SKILL.md
└── mcp-servers/
    ├── abr-mcp/                    # MCP server: ABN Lookup / ABR data
    └── australian-writing-mcp/     # MCP server: AU English writing checks
```

## Licence

This repository is licensed under the [Apache License 2.0](LICENSE).

Individual subprojects may bundle third-party data or ported code under their
own terms; these are attributed in-place (for example,
[mcp-servers/australian-writing-mcp/NOTICE](mcp-servers/australian-writing-mcp/NOTICE) and the
bundled dictionary's licence). See each subproject's `README` for details.
`abr-mcp` bundles no register data; it reads the ABN Bulk Extract you download
(CC BY 3.0 AU), see [mcp-servers/abr-mcp/NOTICE](mcp-servers/abr-mcp/NOTICE).
