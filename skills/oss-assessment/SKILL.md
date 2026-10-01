---
name: oss-assessment
description: >
  Assesses an arbitrary open-source software repository through two lenses: the Digital Public Goods (DPG) Standard and the OpenSSF Concise Guide for Evaluating OSS, with additional emphasis on architecture and code evaluation. Evidence-first: makes no assumptions about forge, CI, security tooling or project structure, distinguishes "not found", "not evidenced", "observed absence" and "unknown", and produces OSS-ASSESSMENT.md without an overall score or recommendation. Does not modify the target repository.
---

# OSS Assessment Skill

## Purpose

Assess an open-source software repository through two complementary lenses:

1. **DPG Standard** — openness, licensing, governance, privacy, sustainability and other applicable Digital Public Goods requirements.
2. **OpenSSF Concise Guide for Evaluating OSS** — project health, security practices, maintenance and technical sustainability.

The assessment places **additional emphasis on architecture and code evaluation**.

The objective is to determine what can be established about the project **from evidence that is actually discoverable**, rather than assuming that particular tools, controls, workflows or external assessments exist.

The skill is designed to run against an arbitrary OSS repository. It must therefore make **no assumptions about the repository's forge, CI provider, security tooling, dependency tooling, project structure, or external service configuration**.

Do not modify the target repository.

---

# Core Principle: Evidence First

> **Assess what can be discovered, not what would normally be expected to exist.**

The agent must begin with repository reconnaissance and progressively build an evidence base.

Do not assume that a project:

* uses GitHub
* uses GitHub Actions
* has OpenSSF Scorecard enabled
* has Dependabot or Renovate
* uses CodeQL
* has branch protection
* has CI
* has automated releases
* has a vulnerability disclosure process
* has architecture documentation
* follows a particular language or framework convention
* has a particular deployment model
* has multiple maintainers
* has production users
* has an external security assessment

If evidence for something is not discoverable, record it as:

**Not evidenced**

rather than assuming:

**Absent**

Where the repository structure makes the absence itself meaningful, distinguish:

* **Not found** — expected artefact was searched for but not located.
* **Not evidenced** — the available evidence is insufficient to establish whether it exists.
* **Observed absence** — repository evidence establishes that the capability is not present.
* **Unknown** — the matter cannot reasonably be determined from available evidence.

This distinction is mandatory for material findings.

---

# Evidence Hierarchy

Use evidence in approximately this order:

### 1. Implementation evidence

Highest priority.

Examples:

* source code
* configuration
* dependency manifests
* lockfiles
* tests
* build scripts
* deployment manifests
* infrastructure code

### 2. Repository documentation

Examples:

* README
* architecture documentation
* ADRs
* SECURITY.md
* CONTRIBUTING.md
* release documentation
* governance documentation

Documentation describes intended behaviour and must not automatically be treated as proof of implementation.

### 3. Repository metadata

Where available:

* commit history
* releases/tags
* contributors
* issues
* pull requests
* repository settings visible through the accessible interface
* commit signatures
* CI history

Only use metadata that is actually accessible.

### 4. External project evidence

Examples:

* official project website
* official documentation
* package registries
* official security advisories
* OpenSSF services
* published project reports

External evidence must be explicitly attributable to the assessed repository.

### 5. General ecosystem assumptions

**Do not use these as evidence.**

The fact that a project is hosted on GitHub, uses Python, or belongs to an ecosystem with a particular security practice does not establish that the repository uses that practice.

---

# External Tool and Service Attribution

External services may be used where useful, but **never assume that their results belong to the target repository**.

For every external assessment or metric:

1. Confirm the repository identity.
2. Confirm the result corresponds to the exact repository being assessed.
3. Record the source.
4. Record the date accessed.
5. Record any limitations.

If this cannot be established, do not use the result as evidence.

## OpenSSF Scorecard

OpenSSF Scorecard is **optional supporting evidence**, not a required assessment input.

Before using Scorecard:

* determine whether a Scorecard result is discoverable;
* verify that the result identifies the exact repository;
* verify that the result is sufficiently current to be useful;
* record the source and date.

If no attributable Scorecard result is discoverable:

> **Scorecard: Not evidenced / not available for assessment**

Do **not** infer that Scorecard is absent from the project merely because it cannot be found.

Do **not** substitute a Scorecard result from:

* another repository
* a fork
* an upstream project
* a similarly named project
* an organisation-level configuration
* a package with the same name

Do not manufacture a Scorecard score by mapping repository observations onto Scorecard criteria unless explicitly requested.

Instead, inspect the repository directly for the underlying practices where they can be evidenced.

---

# Assessment Workflow

## Phase 1 — Repository Discovery

Establish the repository's observable shape.

Inspect, where present:

* root directory
* source directories
* documentation
* configuration
* manifests
* lockfiles
* tests
* scripts
* CI/CD configuration
* deployment configuration
* infrastructure configuration
* security configuration
* licence files
* governance files

Do not expect particular filenames.

Search semantically for relevant evidence rather than relying only on conventional paths.

Produce an initial inventory of:

* languages
* frameworks
* runtimes
* package managers
* build systems
* application components
* services
* databases
* external dependencies
* deployment mechanisms
* test frameworks
* automation
* security tooling

---

# Phase 2 — Reconstruct the Architecture

The agent must understand the architecture **from the repository**, whether or not architecture documentation exists.

Determine, where possible:

* entry points
* major components
* component boundaries
* data flows
* control flows
* persistence
* external services
* APIs
* background processing
* messaging/event mechanisms
* configuration
* extension mechanisms
* deployment topology

Trace at least one important end-to-end execution path through the implementation.

For example:

**entry point → application/service layer → core logic → persistence/external service → output**

Use actual files, modules, classes, functions or configuration to establish the path.

If the architecture cannot be reconstructed confidently, state what remains unclear.

---

# Phase 3 — Architecture & Code Evaluation

Architecture/code evaluation carries the greatest emphasis.

Assess:

## System structure

* How is the system divided?
* Are boundaries apparent from implementation?
* Are responsibilities reasonably cohesive?

## Coupling

* Which components depend directly on one another?
* Are infrastructure concerns embedded in core logic?
* Are external services tightly coupled to application logic?
* Would changing a major dependency require widespread changes?

## Core logic

Identify where the project's primary functionality actually resides.

Assess:

* concentration of important logic
* complexity
* duplication
* abstraction boundaries
* error handling
* state management

## Extensibility

Determine whether important components can be:

* replaced
* extended
* configured
* tested independently

without requiring broad changes.

Do not reward abstraction for its own sake.

## Data architecture

Where relevant, inspect:

* data models
* persistence layer
* migrations
* schemas
* serialisation
* data flow
* ownership of state

## API architecture

Where applicable:

* identify API boundaries
* inspect contracts
* identify versioning
* inspect validation
* inspect error handling
* determine whether API and internal implementation are coupled

## Testing architecture

Inspect how tests relate to architectural boundaries.

Consider:

* unit tests
* integration tests
* end-to-end tests
* fixtures
* mocks/stubs
* test environments

Do not infer quality from coverage percentages alone.

## Build and deployment architecture

Determine from actual configuration:

* how the project is built
* how it is packaged
* runtime requirements
* infrastructure dependencies
* deployment assumptions
* reproducibility

---

# Phase 4 — Technical Health

Assess the OpenSSF lens using whatever evidence is discoverable.

## Maintenance

Inspect:

* recent commits
* release activity
* issue activity
* pull requests
* contributor activity

Do not impose arbitrary universal thresholds.

Describe the observed activity and relevant timeframe.

## Maintainer diversity

Use discoverable evidence about contributors and organisational participation.

Do not assume:

* contributor count equals maintainer count;
* commit count equals meaningful maintenance;
* lack of visible contributors means a single maintainer.

If maintainer structure cannot be established:

**Maintainer structure: Not evidenced**

## Security practices

Look for actual evidence of:

* vulnerability reporting
* security policies
* security scanning
* static analysis
* dependency scanning
* secret scanning
* signed releases/commits
* security-related CI
* security tests

Do not assume any of these exist because they are common practice.

## Dependency management

Inspect actual:

* manifests
* lockfiles
* update configuration
* dependency versions
* vendored code
* package sources

Assess the dependency architecture rather than merely counting dependencies.

## CI/CD

First determine whether CI/CD exists.

Then determine what it actually does.

For example:

* Does it run tests?
* Build artefacts?
* Run security checks?
* Publish releases?
* Deploy?
* Validate dependencies?

Do not assume CI exists because a conventional CI directory is absent or present.

---

# Phase 5 — DPG Assessment

Assess the current DPG Standard against discoverable evidence.

For each applicable criterion:

| Criterion | Status                                | Evidence | Interpretation |
| --------- | ------------------------------------- | -------- | -------------- |
|           | Pass / Partial / Fail / Not evidenced |          |                |

Use **Not evidenced** where the repository does not provide enough information.

Do not convert missing documentation automatically into failure.

Where a criterion requires information that cannot reasonably be obtained from repository inspection, identify it as an **assessment limitation**.

---

# Phase 6 — Cross-Lens Analysis

Compare the evidence from both lenses.

Identify factual relationships such as:

* documented security practice versus implemented security controls
* documented architecture versus observed architecture
* project activity versus release activity
* dependency complexity versus maintainability
* governance documentation versus observable governance
* deployment claims versus deployment configuration

Highlight discrepancies between stated and observed behaviour.

Do not infer motives.

---

# Assessment Weighting

Use:

| Lens                | Weight |
| ------------------- | -----: |
| DPG Standard        |    40% |
| OpenSSF / Technical |    60% |

Within the technical lens:

| Area                               |  Weight |
| ---------------------------------- | ------: |
| Maintenance & sustainability       |     15% |
| Security posture                   |     15% |
| **Architecture & code evaluation** | **30%** |

The weighting indicates **where assessment effort should be concentrated**.

It does not require the agent to produce a numerical project score.

Do not produce an overall score unless explicitly requested.

---

# Confidence

Every material finding should have a confidence level:

* **High** — directly established by implementation or strong repository evidence.
* **Medium** — supported by multiple indirect or documentary sources.
* **Low** — plausible interpretation with limited evidence.

Confidence describes the evidence, not the quality of the project.

---

# Required Output

Create:

`OSS-ASSESSMENT.md`

## 1. Executive Summary

Include:

* project purpose
* observable architecture
* major technical characteristics
* material strengths evidenced
* material risks evidenced
* significant unknowns

Do not provide an overall rating or recommendation.

---

## 2. Repository Profile

| Attribute              | Observed |
| ---------------------- | -------- |
| Repository             |          |
| Licence                |          |
| Primary languages      |          |
| Frameworks/runtime     |          |
| Build system           |          |
| Package manager        |          |
| Deployment model       |          |
| Major dependencies     |          |
| Repository activity    |          |
| External evidence used |          |

---

## 3. Architecture

Describe the architecture reconstructed from implementation.

Include a Mermaid diagram only where the architecture can be represented reliably.

```mermaid
flowchart LR
    ...
```

The diagram must represent observed architecture, not an inferred ideal architecture.

---

## 4. Architecture & Code Evaluation

| Area                   | Observation | Evidence | Confidence |
| ---------------------- | ----------- | -------- | ---------- |
| System structure       |             |          |            |
| Component boundaries   |             |          |            |
| Core logic             |             |          |            |
| Coupling               |             |          |            |
| Extensibility          |             |          |            |
| Data architecture      |             |          |            |
| API architecture       |             |          |            |
| Testing architecture   |             |          |            |
| Build/deployment       |             |          |            |
| Operational complexity |             |          |            |

---

## 5. DPG Standard Assessment

| Criterion | Status | Evidence | Confidence |
| --------- | ------ | -------- | ---------- |
|           |        |          |            |

---

## 6. OpenSSF / Technical Health

| Area                   | Observation | Evidence | Confidence |
| ---------------------- | ----------- | -------- | ---------- |
| Maintenance            |             |          |            |
| Contributors           |             |          |            |
| Releases               |             |          |            |
| Security               |             |          |            |
| Vulnerability handling |             |          |            |
| Dependencies           |             |          |            |
| CI/CD                  |             |          |            |
| Testing                |             |          |            |
| Documentation          |             |          |            |

---

## 7. External Evidence

Record only external evidence that can be reliably attributed to the target repository.

| Source | Result | Repository identity verified? | Date | Limitation |
| ------ | ------ | ----------------------------- | ---- | ---------- |
|        |        | Yes / No                      |      |            |

If no attributable external evidence is found:

> No external assessment results were identified that could be reliably attributed to the target repository.

---

## 8. Material Risks

For each material risk:

**Risk:**
**Evidence:**
**Potential implication:**
**Confidence:**

Risks must be grounded in observed evidence.

---

## 9. Material Unknowns

Explicitly list information that cannot be established.

Examples:

* actual production usage
* undisclosed infrastructure
* private security processes
* maintainer intentions
* operational performance
* undocumented dependencies
* private governance arrangements

---

## 10. Adoption Considerations

Describe the practical implications of the observed architecture and project characteristics for someone considering:

* adoption
* integration
* extension
* operation
* forking

This section is descriptive.

Do not provide an overall recommendation or ranking.

---

## 11. Evidence Appendix

List:

* key files inspected
* important source locations
* configuration files
* external sources
* relevant repository metadata
* assessment date

For significant code findings, identify relevant files and symbols where practical.

---

# Mandatory Quality Checks

Before completing the assessment, verify:

### Repository identity

* Am I assessing the exact repository supplied?
* Are external results demonstrably attributable to it?

### Evidence

* Did I distinguish "not found" from "not evidenced"?
* Did I avoid assuming standard tooling exists?
* Did I inspect implementation rather than relying on documentation?

### Architecture

* Can I explain how the system actually works?
* Can I identify its major components?
* Can I trace an important execution path?
* Can I identify its principal dependencies and infrastructure assumptions?

### Technical health

* Are maintenance claims based on observed activity?
* Are security claims based on actual evidence?
* Are dependency claims based on the project's actual manifests/configuration?
* Did I inspect CI before making claims about CI?

### External services

* Is every external result attributable to the exact repository?
* Is its date recorded?
* Have limitations been recorded?

### Unknowns

* Have important gaps been explicitly identified?
* Have I avoided turning missing evidence into unsupported conclusions?

### Final report

* Does every material finding have identifiable evidence?
* Are facts separated from interpretation?
* Is confidence stated where appropriate?
* Does the report describe the project rather than manufacture an overall rating?
