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
| [au-gov-report](skills/au-gov-report/SKILL.md) | Draft or review internal reports in Australian Government style. |
| [gtm-adoption-assumptions](skills/gtm-adoption-assumptions/SKILL.md) | Develop go-to-market and adoption assumptions for a product or service. |
| [maturity-model-architect](skills/maturity-model-architect/SKILL.md) | Collaboratively build a capability maturity model from one or more datasets. |
| [oss-solution-architect](skills/oss-solution-architect/SKILL.md) | Turn requirements into an annotated OSS-based architecture with open decisions and a backlog. |

## `mcp-servers/`

[Model Context Protocol](https://modelcontextprotocol.io) servers.

| Server | Purpose |
| --- | --- |
| [australian-writing-mcp](mcp-servers/australian-writing-mcp/) | Deterministic Australian English writing checks: spelling, grammar, and reading level. |

## Repository layout

```
civic-lab/
├── skills/                         # One directory per skill, each with a SKILL.md
│   ├── au-gov-email-letter/
│   │   └── SKILL.md
│   ├── au-gov-report/
│   │   └── SKILL.md
│   ├── gtm-adoption-assumptions/
│   │   └── SKILL.md
│   ├── maturity-model-architect/
│   │   └── SKILL.md
│   └── oss-solution-architect/
│       └── SKILL.md
└── mcp-servers/
    └── australian-writing-mcp/     # MCP server: AU English writing checks
```

## Licence

This repository is licensed under the [Apache License 2.0](LICENSE).

Individual subprojects may bundle third-party data or ported code under their
own terms; these are attributed in-place (for example,
[mcp-servers/australian-writing-mcp/NOTICE](mcp-servers/australian-writing-mcp/NOTICE) and the
bundled dictionary's licence). See each subproject's `README` for details.
