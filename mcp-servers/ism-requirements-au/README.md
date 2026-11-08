# ism-requirements-au

An [MCP](https://modelcontextprotocol.io) server that helps a project team **build a system that can be authorised** under
the Australian Government [Information Security Manual](https://www.cyber.gov.au/resources-business-and-government/essential-cyber-security/ism)
(ISM). It works out which obligations and controls apply, reviews the repository for what would stop authorisation, and
tracks the evidence as the system is built, so the assessment pack is an export and not a reconstruction.

It is decision support for the team, its system owner and its assessor. It is **not an IRAP assessment** and not legal
advice: only an assessor sets an assessment outcome, and this server never proposes anything but "Not Assessed".

- **Offline and read-only.** The knowledge base ships in the package. No network, no model calls, no writes: the agent
  writes any file from the tool output.
- **Verbatim.** Control text is copied from ASD's OSCAL catalog (v2026.09.4). Every quotation is anchored to its source
  passage by hash and offsets, and the build fails if one does not match.
- **Honest about evidence.** Each finding carries a mapping *fidelity*. Only `direct` mappings are described as enforced
  by a mechanism. Absence findings say "not found here", not "not done".

## What you get

Given a repository and a short system profile, it answers four questions:

1. **Does this system need to be authorised, and under what?** PSPF binding or not, classification baseline, the Essential
   Eight Maturity Level Two mandate, IRAP obligations for cloud and gateway providers, sector overlays.
2. **Which controls apply, and which can this repository evidence?** The OSCAL baseline for the classification, grouped by
   guideline and section, with Essentials actions and Essential Eight levels.
3. **What would stop authorisation today?** Findings at four levels, plus missing authorisation documents.
4. **What should we build next, and what evidence should we keep?** Ordered by the ISM's six risk-management steps.

Findings come at four levels:

| Level | Meaning |
| --- | --- |
| `blocker` | Authorisation cannot proceed on current evidence: a precondition is missing, or a rule in a mandatory obligation (an Essential Eight Maturity Level Two strategy under PSPF section 14) reads as not met with firm evidence. |
| `gap` | A control in scope reads as unmet or unevidenced; the questions say what would settle it. Secrets in files are flagged `urgent`. |
| `plan` | In scope but it belongs to a later step of the six (define, select, implement, assess, authorise, monitor). |
| `info` | Recorded for completeness, for example a document found by file name that this server cannot read. |

## What a review looks like

Abridged output for the deliberately bad project the tests build (`tests/conftest.py`), reviewed for a non-corporate
Commonwealth entity at PROTECTED in the implement step:

```text
ISM 2026.09 review of /work (PROTECTED, phase implement)
levels: blocker=4, gap=32, plan=7, info=1
[BLOCKER] PRE-IRP                (repository)
    Cyber security incident response plan not found: ... it may be held elsewhere.
[BLOCKER] R-MFA                  infra/main.tf:13
    Multi-factor authentication is used: Multi-factor authentication is switched off in configuration.
[GAP    ] R-CRED-SHORT-LIVED     app/settings.py:3
    Workloads use short-lived, dynamically issued credentials: A long-lived cloud access key is present in the repository.
[GAP    ] R-TLS-VERSION          app/settings.py:4
    Only the latest TLS version is used: A TLS or SSL version below TLS 1.2 is permitted or selected.
[GAP    ] R-AI-AGENT-LEAST-TOOLS agent.py:1
    Agents are limited to the minimum tools and permissions: An agent is given broad execution capability or run without an approval step.
[PLAN   ] PRE-ATO                (repository)
    Authorisation to operate not found: ... (expected only once the earlier steps are complete).
[PLAN   ] H-ALERTS-WATCHED       (repository)
    Alerts from security tooling are actually watched: Tooling that generates alerts no one reads is a recurring assessment finding.
[INFO   ] PRE-SSP                (repository)
    System security plan found by file name: docs/system-security-plan.pdf ... is a format this server does not read. Confirm its content.
```

`R-MFA` is a blocker, not a gap, because multi-factor authentication is an Essential Eight Maturity Level Two strategy and
the PSPF makes Maturity Level Two mandatory for this entity. Over MCP, `interrogate` on any finding id gives the verbatim
control, the evidence, guidance and what would settle it.

## Quick start

You need [uv](https://docs.astral.sh/uv/). `uvx` fetches and runs the server; there is no install step.

**Claude Desktop / Claude Code** (`mcpServers`):

```json
{
  "mcpServers": {
    "ism": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/DeepCivic/civic-lab#subdirectory=mcp-servers/ism-requirements-au",
               "ism-requirements-au"]
    }
  }
}
```

**VS Code** (`.vscode/mcp.json`): the same `command` and `args` under `"servers"`.

Then ask your assistant something like:

> We are a non-corporate Commonwealth entity building a PROTECTED system. Review /path/to/my-project for what would stop
> it being authorised under the ISM.

Or use the `ism_requirements` prompt, which runs the whole workflow.

## Docker

The image runs the same server. Mount the project at `/work` (read-only is enough) and ask for a review of `/work`. The
server can read nothing else.

```json
{
  "mcpServers": {
    "ism": {
      "command": "docker",
      "args": ["run", "-i", "--rm", "-v", "/path/to/my-project:/work:ro", "ghcr.io/deepcivic/ism-requirements-au"]
    }
  }
}
```

```sh
docker run --rm -v "$PWD":/work:ro ghcr.io/deepcivic/ism-requirements-au \
    review /work --entity-type non_corporate_commonwealth --fail-on blocker
docker run --rm -v "$PWD":/work:ro ghcr.io/deepcivic/ism-requirements-au verify /work
```

The image is published when a release is tagged. Until then, build it locally with
`docker build -t ism-requirements-au .`.

## Configuration

The server is isolated by default. It reads only the paths you give it, makes no network calls and writes nothing.

| Setting | Effect |
| --- | --- |
| `ISM_REQUIREMENTS_AU_ROOTS` (path list) or `serve --root DIR` | Only these directories may be read (`/work` in the image). Required for HTTP mode. |
| `serve --http [--host H --port P]` | Streamable HTTP at `/mcp`. `HOST` and `PORT` set the defaults. Refuses to start without roots, because it reads files for remote clients. |

## Command line and CI

```sh
ism-requirements-au review path/to/repo --entity-type non_corporate_commonwealth --classification PROTECTED
ism-requirements-au review path/to/repo --entity-type other --fail-on gap --json   # exit 1 on any gap or blocker
ism-requirements-au verify path/to/repo --strict                                    # check .ism/controls.yaml
ism-requirements-au status
```

`review` exits 1 when a finding at or above `--fail-on` (default `blocker`) is present, and `verify` exits 1 on any error.
Both exit 2 on bad input, such as an unknown classification. From source (Python 3.15): `uv pip install -e ".[dev]" && pytest`.

## Tools

Responses are compact by default: counts first, ids and one-line statements, details on request. The 1,192-control text
never travels whole.

| Tool | Purpose |
| --- | --- |
| `review_project` | **Start here.** Scan code, IaC, CI and documents: findings by level (top N per level, `offset` to page, `detail=full` for everything, `since=<run_id>` for what changed), readiness, inferred Essentials domains, next steps. |
| `assess_applicability` | Entity type, classification, hosting, sector: which obligations bind; PSPF section 13 to 15 and Essential Eight status. |
| `scope_system` | Applicable controls for the classification and any Essential Eight target, as counts per guideline and section; ids for one section on request. |
| `authorisation_readiness` | The preconditions checklist (system security plan and annex, incident response plan, continuous monitoring plan, risk management plan, authorisation to operate, register entry, IRAP report) and what each is missing. |
| `interrogate` | One finding, control, rule, heuristic, precondition, obligation or Essentials action: requirement, evidence, guidance, what settles it. |
| `get_control`, `search_controls`, `get_obligation`, `get_essentials_action`, `diff_release` | Lookup: verbatim text, baselines and crosswalks, PSPF obligations, Essentials actions, controls changed in this release. |
| `ssp_annex_schema` | The schema of ASD's SSP annex template (columns and value lists). Static and small. |
| `draft_ssp_annex` | Only the five user-owned annex columns, keyed by control id, from the tracking manifest (CSV or JSON). |
| `ssp_annex_xlsx_instructions` | Steps to merge the CSV into ASD's xlsx by Identifier. |
| `track_plan`, `track_entry`, `track_gaps`, `track_impact`, `track_ci` | Control tracking: return YAML or a workflow for the agent to write; the server never writes. |
| `kb_status` | Release, counts, sources and licences, level meanings and known limits. |

Prompts: `ism_requirements` (derive requirements for a system) and `irap_readiness` (prepare for assessment).

A typical session: `assess_applicability` → `review_project` → read the documents it lists as unread → `interrogate` the
findings that matter → ask the user only what the repository cannot show → `track_plan`.

## Control tracking

When a team wants deterministic evidence, the agent writes a manifest from `track_plan` and `track_entry` output:

```yaml
# .ism/controls.yaml
ism_release: "2026.09"
scope: {classification: PROTECTED, e8_target: ML2, essentials_domains: [Identity services], essentials_domains_source: user}
controls:
  - id: ISM-2154            # Software artefact dependencies are pinned to approved versions in source code.
    text_sha256: "..."      # of the OSCAL statement; a reworded control fails verify
    phase: implement
    status: implemented     # implemented | partial | planned | not_applicable | risk_accepted
    fidelity: direct        # direct | partial | supporting
    mechanism: {kind: ci, ref: .github/workflows/deps.yml}
    evidence: [requirements.lock, .github/workflows/deps.yml]
    reviewed_against: "2026.09"
```

`ism-requirements-au verify` checks it offline, with no model and the same exit code for the same inputs: ids exist in the
pinned release, text hashes match, evidence paths and mechanism references exist inside the project, nothing claims `direct`
without a mechanism, and optional `# ism: ISM-xxxx` markers in code agree with the manifest. `--strict` also fails when an
applicable rule-linked control has no entry. `track_ci` returns a workflow that runs it. `track_impact` reports entries whose
control text or revision has changed.

`draft_ssp_annex` maps the manifest to the annex: `implemented` is Implemented, `not_applicable` is Not Applicable, and
`partial`, `planned`, `risk_accepted` and untracked controls are Not Determined (with a comment), never a guess.
Responsibility and Implementation Source come only from the manifest.

## Markers

A finding on a line containing `ism-review: ignore` is suppressed, and a file containing `ism-review: ignore-file` is not
read. Use them with a reason, for example for a test fixture.

## What you can rely on

**What it is good at:** finding early what an assessor would find late: secrets and long-lived keys in the repository,
switched-off MFA, weak TLS, open ingress, unpinned or untrusted dependencies, over-privileged AI agents, and missing
authorisation documents. It ties each one to the verbatim ISM control, the Essential Eight level and the PSPF obligation
behind it, and says how firmly the repository evidences it (`fidelity` and `confidence`).

**What it cannot do:**

- **Assess.** Only an IRAP assessor sets an assessment outcome; a blocker means "will not get through on this evidence",
  not "failed".
- **See outside the repository.** Platform settings, tenant policies, tickets and documents held elsewhere are invisible,
  so absence findings mean "not found here".
- **Read PDFs or Office files.** It finds documents such as a system security plan by file name and lists them as unread
  so your assistant can read them.
- **Cover every control.** Of the controls that apply, it has rules for the ones a repository can evidence. Physical,
  personnel and organisation-level controls are counted by `scope_system`, not reviewed.
- **Know a later ISM release.** It carries ISM v2026.09.4 only; `track_impact` flags manifest entries whose control has
  since changed.

The knowledge base, its sources and its known gaps are described in [RESEARCH.md](RESEARCH.md).

## What it covers

29 rules and 12 assessment-gap heuristics over software development, web and AI application development, credentials,
identity, TLS, network exposure, logging and patching, plus 8 authorisation preconditions. See [docs/rules.md](docs/rules.md)
for each rule, its controls, fidelity and detectors, and [RESEARCH.md](RESEARCH.md) for how the knowledge base was made and
its limits. Hardening and security-monitoring controls are in the control scope and carry Essential Eight levels and
Essentials actions; rules for them grow with later releases.

## Documentation

- [Rules](docs/rules.md): each rule and heuristic, its controls, fidelity, phase and detectors.
- [RESEARCH.md](RESEARCH.md): how the knowledge base was made, its sources and its known limits.
- [CHANGELOG](CHANGELOG.md).

## Licence

Apache-2.0. The knowledge base includes material from ASD (CC BY 4.0), the PSPF (CC BY 3.0 AU) and NIST (public domain), and
refers to OWASP and AESCSF by identifier only; see [NOTICE](NOTICE).
