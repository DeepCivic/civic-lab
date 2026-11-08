# Changelog

## 0.1.0 (unreleased)

First release.

- **Review.** `review_project` scans a repository (code, infrastructure-as-code, CI and documents) against 29 rules and 12
  common-assessment-gap heuristics drawn from the ISM, and returns findings at four levels (blocker, gap, plan, info),
  authorisation readiness, inferred Essentials domains, open questions and next steps in lifecycle order. Responses are
  compact by default and page by level; `since` returns only what changed between runs.
- **Applicability and scope.** `assess_applicability` (does the PSPF bind, is Essential Eight Maturity Level Two mandatory, is
  IRAP required, sector overlays) and `scope_system` (applicable controls by guideline and section for the classification).
- **Authorisation preconditions.** `authorisation_readiness` checks for the system security plan and annex, incident response
  plan, continuous monitoring plan, risk management plan, authorisation to operate, register entry and IRAP report.
- **Lookup.** `get_control`, `search_controls`, `get_obligation`, `get_essentials_action`, `diff_release`, `interrogate`.
- **Control tracking.** `track_plan`, `track_entry`, `track_gaps`, `track_impact`, `track_ci` return content for the agent to
  write; `ism-requirements-au verify` checks `.ism/controls.yaml` offline in CI.
- **SSP annex.** `ssp_annex_schema`, `draft_ssp_annex` (the five user-owned columns only) and `ssp_annex_xlsx_instructions`.
- Knowledge base compiled from ISM OSCAL v2026.09.4 (1,143 controls and 49 principles), 58 Essentials actions and the
  Essential Eight crosswalk. Strictly read-only; no network.
- Docker image and MCP Registry entry; the image mounts the project at `/work`.
