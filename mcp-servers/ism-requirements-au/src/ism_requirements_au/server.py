"""ism-requirements-au MCP server: derive the ISM, Essentials and PSPF requirements for a system, review a repository for what
would stop authorisation, and track control evidence as the system is built. Offline, read-only.

Run with:  ism-requirements-au                                 (stdio)
           ism-requirements-au serve --http --root /srv/repos  (streamable-HTTP /mcp)
"""

from __future__ import annotations

import functools
import os
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any, Literal, TypeVar

from pydantic import Field

try:  # mcp >= 2
    from mcp.server.mcpserver import MCPServer as _Server
    from mcp.server.mcpserver.exceptions import ToolError
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as _Server
    from mcp.server.fastmcp.exceptions import ToolError

from . import annex as _annex
from . import kb as _kb
from . import profile as _pr
from . import review as _rv
from . import track as _tr

ROOTS_ENV = "ISM_REQUIREMENTS_AU_ROOTS"

INSTRUCTIONS = """\
Helps a project team build a system that can be authorised under the Australian Government Information Security Manual (ISM):
it works out which obligations and controls apply, reviews the repository for what would stop authorisation, and tracks the
evidence as the system is built. It is read-only and offline; you (the agent) write any files from its output.

How to use it well:
- Start with review_project: pass the repository path, the system's classification, the entity type and the lifecycle phase
  the team is in. It returns counts first, then the top findings at four levels (blocker, gap, plan, info). Page with
  level/offset, or ask for detail=full. Pass since=<run_id> to see only what changed.
- Answer what you can from the material before asking the user: read the documents the review lists as unread, then ask only
  about what the repository cannot show. Findings with confidence 'low' are absence findings: 'not found here', not 'not done'.
- interrogate takes a finding id, control id (ISM-0041), rule or heuristic id, precondition, obligation or Essentials action
  id and returns the requirement, the evidence, guidance and what would settle it. get_control gives verbatim text.
- Only mappings with fidelity 'direct' are described as enforced by a mechanism; 'partial' and 'supporting' help evidence a
  control but do not settle it. Only an IRAP assessor sets an assessment outcome; this server never proposes anything but
  'Not Assessed'.
- To track controls, call track_plan, write its YAML to .ism/controls.yaml, then use track_entry as evidence is added and
  track_gaps / track_impact to check it. 'ism-requirements-au verify' checks the manifest in CI. draft_ssp_annex turns the
  manifest into the five user-owned columns of ASD's SSP annex template.
- Responses are compact by default. Control text comes through get_control, never in bulk.
- Decision support for the team, its system owner and its assessor. It is not an IRAP assessment and not legal advice.
"""

mcp = _Server("ism-requirements-au", instructions=INSTRUCTIONS)
F = TypeVar("F", bound=Callable[..., Any])


def anticipated(fn: F) -> F:
    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return fn(*args, **kwargs)
        except (ValueError, KeyError, OSError, PermissionError) as exc:
            raise ToolError(str(exc)) from exc

    return wrapper  # type: ignore[return-value]


def allowed_roots() -> list[Path]:
    return [Path(p).expanduser().resolve() for p in os.environ.get(ROOTS_ENV, "").split(os.pathsep) if p.strip()]


def check_path(path: str) -> Path:
    p = Path(path).expanduser().resolve()
    roots = allowed_roots()
    if roots and not any(p == r or r in p.parents for r in roots):
        raise PermissionError(f"{p} is outside the directories this server may read ({ROOTS_ENV})")
    return p


Classification = Annotated[str, Field(description="Highest classification of the information the system handles: NON-CLASSIFIED, OFFICIAL: Sensitive, PROTECTED, SECRET or TOP SECRET")]
EntityType = Annotated[Literal["non_corporate_commonwealth", "corporate_commonwealth", "state_territory", "private_sector", "other"],
                       Field(description="Who owns the system. Decides whether the PSPF binds and whether Essential Eight Maturity Level Two is mandatory")]
Hosting = Annotated[Literal["unknown", "cloud_csp", "on_premises", "hybrid", "gateway"], Field(description="Where the system runs")]
Phase = Annotated[Literal["define", "select", "implement", "assess", "authorise", "monitor"],
                  Field(description="The ISM risk management step the team is in. Controls that bite later are reported as 'plan'")]
Manifest = Annotated[str | None, Field(description="Path to the tracking manifest (default .ism/controls.yaml under the project)")]
ManifestYaml = Annotated[str | None, Field(description="The manifest content itself, if you have it and not a path")]


def _load() -> _kb.KB:
    return _kb.load()


def _manifest(manifest_path: str | None, manifest_yaml: str | None, project: str | None = None) -> dict:
    if manifest_yaml:
        return _tr.parse(manifest_yaml)
    p = check_path(manifest_path) if manifest_path else (check_path(project) / _tr.DEFAULT_MANIFEST if project else None)
    if p is None or not p.is_file():
        raise ValueError(f"manifest not found; pass manifest_path or manifest_yaml (default {_tr.DEFAULT_MANIFEST})")
    return _tr.parse(p.read_text(encoding="utf-8"))


def _control_brief(c: dict, limit: int = 160) -> dict:
    s = c["statement"].replace("\n", " ")
    return {"id": c["id"], "statement": s if len(s) <= limit else s[: limit - 1] + "…", "topic": c["topic"]}


# ---- applicability and scope ---------------------------------------------------------------------------------------------
@mcp.tool()
@anticipated
def assess_applicability(entity_type: EntityType, classification: Classification = "PROTECTED", hosting: Hosting = "unknown",
                         provides_cloud_service: bool = False, provides_gateway: bool = False, supplies_government: bool = True,
                         apra_regulated: bool = False, critical_infrastructure: bool = False) -> dict:
    """Does this system need to be authorised, and under what? PSPF binding or not, the classification baseline, the Essential Eight
    Maturity Level Two mandate, IRAP obligations for cloud and gateway providers, and sector overlays (APRA CPS 234, SOCI)."""
    return _pr.assess_applicability(_load(), entity_type, classification, hosting, provides_cloud_service, provides_gateway, supplies_government,
                                    apra_regulated, critical_infrastructure)


@mcp.tool()
@anticipated
def scope_system(classification: Classification = "PROTECTED", e8_target: Annotated[Literal["none", "ML1", "ML2", "ML3"], Field(description="Essential Eight target; ML2 for non-corporate Commonwealth entities")] = "none",
                 features: Annotated[list[Literal["email", "gateway", "transfer"]] | None, Field(description="Extra areas in scope: email, gateway, data transfer")] = None,
                 section: Annotated[str | None, Field(description="List control ids for one section or guideline (substring match)")] = None) -> dict:
    """Which ISM controls apply: counts per guideline and section for the classification baseline plus any Essential Eight mandate, with how many
    carry Essentials actions, Essential Eight levels and rules. Ids only on request; text via get_control."""
    return _pr.scope_system(_load(), classification, None if e8_target == "none" else e8_target, features, section)


# ---- review ----------------------------------------------------------------------------------------------------------------
def _run(path: str, classification: str, entity_type: str, hosting: str, phase: str, provides_cloud_service: bool, provides_gateway: bool,
         supplies_government: bool, apra_regulated: bool, critical_infrastructure: bool, exclude: list[str] | None) -> dict:
    return _rv.build(_load(), check_path(path), classification=classification, entity_type=entity_type, hosting=hosting, phase=phase,
                     provides_cloud_service=provides_cloud_service, provides_gateway=provides_gateway, supplies_government=supplies_government,
                     apra_regulated=apra_regulated, critical_infrastructure=critical_infrastructure, exclude=exclude)


@mcp.tool()
@anticipated
def review_project(path: Annotated[str, Field(description="Absolute path of the repository (and documents) to review; /work in the container")],
                   entity_type: EntityType, classification: Classification = "PROTECTED", hosting: Hosting = "unknown", phase: Phase = "implement",
                   level: Annotated[Literal["all", "blocker", "gap", "plan", "info"], Field(description="Show one level only")] = "all",
                   limit: Annotated[int, Field(ge=1, le=100, description="Findings per level")] = 5, offset: Annotated[int, Field(ge=0)] = 0,
                   detail: Annotated[Literal["summary", "full"], Field(description="'full' returns every finding with evidence, coverage and open questions")] = "summary",
                   since: Annotated[str | None, Field(description="A run_id from an earlier review: return only findings that are new, and list the resolved ones")] = None,
                   provides_cloud_service: bool = False, provides_gateway: bool = False, supplies_government: bool = True,
                   apra_regulated: bool = False, critical_infrastructure: bool = False,
                   exclude: Annotated[list[str] | None, Field(description="Relative paths to skip")] = None) -> dict:
    """START HERE. Scan code, infrastructure-as-code, CI and documents against the ISM rules: findings by level (blocker, gap, plan, info), authorisation
    readiness, inferred Essentials domains, open questions, and what to build next in lifecycle order. Counts first; pages with level/offset."""
    full = _run(path, classification, entity_type, hosting, phase, provides_cloud_service, provides_gateway, supplies_government,
                apra_regulated, critical_infrastructure, exclude)
    return _rv.compact(full, level=level, limit=limit, offset=offset, detail=detail, since=since)


@mcp.tool()
@anticipated
def authorisation_readiness(path: str, entity_type: EntityType, classification: Classification = "PROTECTED", hosting: Hosting = "unknown",
                            phase: Phase = "assess", provides_cloud_service: bool = False, provides_gateway: bool = False) -> dict:
    """The authorisation preconditions checklist (system security plan and annex, incident response plan, continuous monitoring plan, risk
    management plan, authorisation to operate, register entry, IRAP report) with what each is missing, and the obligations that route to them."""
    full = _run(path, classification, entity_type, hosting, phase, provides_cloud_service, provides_gateway, True, False, False, None)
    k = _load()
    return {"phase": phase, "ready_to_proceed_to_authorisation": full["readiness"]["ready_to_proceed_to_authorisation"], "preconditions": [
        {**p, "obligation": k.precondition(p["id"])["obligation"], "if_missing": k.precondition(p["id"])["missing"] if p["status"] == "not_found" else None}
        for p in full["readiness"]["preconditions"]], "obligations": full["applicability_full"]["obligations"],
        "note": "Found by file name or heading only; confirm the content meets the control. Documents held outside the repository are not visible."}


@mcp.tool()
@anticipated
def interrogate(id: Annotated[str, Field(description="A finding id (F-xxxxxxxx) from a review in this session, a control (ISM-0041), rule or heuristic (R-.., H-..), precondition (PRE-..), obligation (PSPF-.., DIR-..) or Essentials action (IT.IDE-01.2)")]) -> dict:
    """One finding, control, rule, heuristic, precondition, obligation or Essentials action: the requirement verbatim, evidence for and against,
    guidance (anchored, attributed quotations), mapping fidelity and what would settle it."""
    k = _load()
    key = id.strip()
    if key.upper().startswith("F-"):
        key = "F-" + key[2:].lower()
        f = _rv.find_finding(key)
        if f is None:
            raise ValueError("unknown finding id; finding ids last for the life of this server process. Run review_project first.")
        e = k.entry(f["rule"])
        pre = k.precondition(f["rule"])
        out: dict = {"finding": f}
        if e:
            out["requirement"] = e.get("requirement") or [{"control": c, "statement": k.control(c)["statement"]} for c in e["controls"]]
            out["what_non_conformance_looks_like"] = e.get("noncompliance")
            out["remediation"] = e.get("remediation")
            out["guidance"] = e.get("guidance", [])
            out["references"] = [r for r in k.data.get("references", []) if r["id"] in e.get("refs", [])]
            out["e8"] = e.get("e8", [])
            out["essentials"] = e.get("essentials", [])
            out["evidence_against"] = ("none visible" if f["kind"] == "presence" else
                                       "This is an absence finding: the repository may simply not be where the evidence lives. A CI setting, platform policy or document elsewhere would settle it.")
        elif pre:
            out["requirement"] = [{"control": c, "statement": k.control(c)["statement"]} for c in pre["controls"]]
            out["obligation"] = k.obligation(pre["obligation"])
        return out
    up = key.upper()
    if k.has_control(up):
        c = k.control(up)
        rules = k.rules_for_control(up)
        return {**c, "rules": rules, "baseline_names": [_kb.CLASSIFICATION_NAMES[a] for a in c["applicability"]],
                "essentials_actions": [{"id": a, "action": k.essentials[a]["action"]} for a in c["essentials"] if a in k.essentials],
                "guidance": [g for r in rules for g in (k.entry(r) or {}).get("guidance", [])][:4],
                "text_sha256": _tr.text_sha256(c["statement"])}
    e = k.entry(key)
    if e:
        return e
    p = k.precondition(key)
    if p:
        return {**p, "requirement": [{"control": c, "statement": k.control(c)["statement"]} for c in p["controls"]], "obligation": k.obligation(p["obligation"])}
    o = k.obligation(key)
    if o:
        return o
    if up in k.essentials:
        a = k.essentials[up]
        return {"id": up, **a, "controls": [_control_brief(k.control(i)) for i in a["ism"] if k.has_control(i)]}
    raise ValueError(f"nothing found for {id!r}; try search_controls")


# ---- lookup --------------------------------------------------------------------------------------------------------------------
@mcp.tool()
@anticipated
def get_control(ids: Annotated[list[str], Field(description="ISM control ids, e.g. ['ISM-0041', 'ISM-1504'] (up to 25)")]) -> list[dict]:
    """Verbatim control text with revision, last-updated month, classification baselines, Essential Eight levels, Essentials actions, section and rules."""
    k = _load()
    out = []
    for i in ids[:25]:
        c = k.control(i)
        if not c:
            out.append({"id": i.upper(), "error": f"not a control in ISM {k.release}"})
            continue
        out.append({**c, "baselines": c.pop("applicability"), "rules": k.rules_for_control(c["id"])})
    return out


@mcp.tool()
@anticipated
def search_controls(query: Annotated[str, Field(description="Words that must all appear in the control id, statement or topic")], limit: Annotated[int, Field(ge=1, le=50)] = 10) -> list[dict]:
    """Find controls by words in their text or topic. Returns ids with truncated statements."""
    return [{**h, "statement": h["statement"].replace("\n", " ")[:160]} for h in _load().search(query, limit)]


@mcp.tool()
@anticipated
def get_obligation(id: Annotated[str | None, Field(description="e.g. PSPF-14-E8-ML2; omit to list all")] = None) -> Any:
    """PSPF Release 2026 obligations that route to the ISM (sections 13 to 15 and Direction 002-2026), as paraphrase with short verified quotations and what each means for a project."""
    k = _load()
    if id is None:
        return [{"id": o["id"], "section": o["section"], "summary": o["summary"], "phase": o["phase"]} for o in k.obligations]
    o = k.obligation(id.strip())
    if not o:
        raise ValueError(f"unknown obligation {id!r}")
    return o


@mcp.tool()
@anticipated
def get_essentials_action(id: Annotated[str | None, Field(description="e.g. IT.IDE-01.2; omit to list the domains and counts")] = None,
                          domain: Annotated[str | None, Field(description="List actions in one domain")] = None) -> Any:
    """ASD Essentials (enterprise IT) actions: principle, action text, domains and the ISM controls each is cross-referenced to."""
    k = _load()
    if id:
        aid = id.strip().upper()
        a = k.essentials.get(aid)
        if not a:
            raise ValueError(f"unknown Essentials action {id!r}")
        return {"id": aid, **a, "controls": [_control_brief(k.control(i)) for i in a["ism"] if k.has_control(i)]}
    if domain:
        return [{"id": i, "action": a["action"][:140], "controls": len(a["ism"])} for i, a in k.essentials.items() if domain.lower() in " ".join(a["domains"]).lower()]
    counts: dict[str, int] = {}
    for a in k.essentials.values():
        for d in a["domains"]:
            counts[d] = counts.get(d, 0) + 1
    return {"domains": counts, "actions": len(k.essentials), "with_ism_controls": sum(1 for a in k.essentials.values() if a["ism"])}


@mcp.tool()
@anticipated
def diff_release(limit: Annotated[int, Field(ge=1, le=200)] = 50) -> dict:
    """Controls changed in the release this server carries (their 'updated' month equals the release month), by guideline. Older releases are not bundled;
    use track_impact to compare a manifest pinned to an earlier release."""
    k = _load()
    month = {"01": "Jan", "02": "Feb", "03": "Mar", "04": "Apr", "05": "May", "06": "Jun", "07": "Jul", "08": "Aug", "09": "Sep", "10": "Oct", "11": "Nov", "12": "Dec"}
    yr, mo = k.release.split(".")
    label = f"{month[mo]}-{yr[2:]}"
    ch = [c for c in k.controls("any") if c.get("updated") == label]
    by: dict[str, int] = {}
    for c in ch:
        by[c["guideline"]] = by.get(c["guideline"], 0) + 1
    return {"release": k.release, "updated_label": label, "changed": len(ch), "by_guideline": dict(sorted(by.items(), key=lambda kv: -kv[1])),
            "controls": [{"id": c["id"], "revision": c["revision"], "topic": c["topic"]} for c in ch[:limit]],
            "note": "Revision numbers show how many times a control has been reworded. Per-control change rationale is in ASD's published changes document."}


# ---- SSP annex ---------------------------------------------------------------------------------------------------------------
@mcp.tool()
@anticipated
def ssp_annex_schema() -> dict:
    """The schema of ASD's SSP annex template (columns, value lists, version, source URL). Static and small; call once."""
    return _annex.schema()


@mcp.tool()
@anticipated
def draft_ssp_annex(manifest_path: Manifest = None, manifest_yaml: ManifestYaml = None, project: Annotated[str | None, Field(description="Project directory holding .ism/controls.yaml")] = None,
                    sections: Annotated[list[str] | None, Field(description="Only controls whose guideline, section or topic contains one of these")] = None,
                    scope: Annotated[Literal["applicable", "all"], Field(description="'applicable' (default) limits to controls applicable at the manifest classification")] = "applicable",
                    format: Literal["csv", "json"] = "csv", include_comments: bool = True, sheet: Literal["controls", "principles"] = "controls") -> dict:
    """Only the five user-owned annex columns, keyed by control id, from the tracking manifest. The template already holds the identifying columns."""
    return _annex.draft(_load(), _manifest(manifest_path, manifest_yaml, project), applicable_only=scope == "applicable", sections=sections, fmt=format,
                        include_comments=include_comments, sheet=sheet)


@mcp.tool()
@anticipated
def ssp_annex_xlsx_instructions() -> list[str]:
    """Steps to merge the drafted CSV into ASD's xlsx template by Identifier, so the server never ships or writes the template."""
    return _annex.xlsx_instructions()


# ---- tracking ----------------------------------------------------------------------------------------------------------------
@mcp.tool()
@anticipated
def track_plan(classification: Classification = "PROTECTED", e8_target: Literal["none", "ML1", "ML2", "ML3"] = "none",
               essentials_domains: Annotated[list[str] | None, Field(description="Confirmed Essentials domains; omit to leave empty")] = None,
               sections: Annotated[list[str] | None, Field(description="Also include controls from these sections or guidelines")] = None) -> dict:
    """A starting .ism/controls.yaml: the controls the rule set can help evidence plus the preconditions' controls, with statement hashes. Returns content; the agent writes the file."""
    return _tr.plan(_load(), classification, None if e8_target == "none" else e8_target, essentials_domains, "user", sections)


@mcp.tool()
@anticipated
def track_entry(control_id: str, status: Literal["implemented", "partial", "planned", "not_applicable", "risk_accepted"],
                mechanism_kind: Literal["ci", "iac", "code", "config", "document", "process", "platform", "inherited"] = "process", mechanism_ref: str = "",
                evidence: Annotated[list[str] | None, Field(description="Repository paths or URLs that evidence the control")] = None,
                fidelity: Literal["direct", "partial", "supporting"] = "supporting",
                phase: Annotated[Literal["define", "select", "implement", "assess", "authorise", "monitor"] | None,
                                 Field(description="Lifecycle step; defaults to the phase of the control's first rule")] = None,
                responsibility: str | None = None, source: str | None = None, note: str | None = None) -> dict:
    """A validated manifest entry for one control to append under 'controls:'. Warns if 'direct' has no mechanism or 'implemented' has no evidence."""
    return _tr.entry(_load(), control_id, status, mechanism_kind, mechanism_ref, evidence, fidelity, phase, responsibility, source, note)


@mcp.tool()
@anticipated
def track_gaps(manifest_path: Manifest = None, manifest_yaml: ManifestYaml = None, project: str | None = None, limit: Annotated[int, Field(ge=1, le=200)] = 40) -> dict:
    """Rule-linked controls missing from the manifest, entries without evidence, and the count of applicable controls not declared."""
    return _tr.gaps(_load(), _manifest(manifest_path, manifest_yaml, project), limit=limit)


@mcp.tool()
@anticipated
def track_impact(manifest_path: Manifest = None, manifest_yaml: ManifestYaml = None, project: str | None = None) -> dict:
    """Manifest entries whose control text or revision changed since they were reviewed, and ids no longer in the ISM."""
    return _tr.impact(_load(), _manifest(manifest_path, manifest_yaml, project))


@mcp.tool()
@anticipated
def track_ci() -> dict:
    """A GitHub Actions workflow that runs 'ism-requirements-au verify' on the manifest (fetched from this repository with uvx; it is not on PyPI).
    Returns content; the agent writes the file."""
    return _tr.ci_workflow()


# ---- status ------------------------------------------------------------------------------------------------------------------
@mcp.tool()
@anticipated
def kb_status() -> dict:
    """Knowledge base release, counts, sources and licences, level meanings and known limits. Static material is returned here once, not in every response."""
    k = _load()
    return {"server_version": __import__("ism_requirements_au").__version__, "ism_release": k.release, "oscal_version": k.oscal, "built": k.built,
            "counts": {"controls": sum(1 for _ in k.controls()), "principles": sum(1 for _ in k.controls("principle")), "rules": len(k.rules),
                       "heuristics": len(k.heuristics), "preconditions": len(k.preconditions), "obligations": len(k.obligations), "essentials_actions": len(k.essentials),
                       "guidance_quotations": sum(len(e.get("guidance", [])) for e in k.rules + k.heuristics)},
            "baseline_check": k.data["baseline_check"], "levels": _rv.LEVEL_MEANING, "phases": k.phases, "sources": k.sources(),
            "limits": ["Static analysis of one directory; absence findings are not proof of absence.",
                       "PSPF requirement numbers are given only where the source states them unambiguously (0098); other obligations cite the section.",
                       "Guidance quotations are selected by relevance and checked for anchoring; they are not curated control by control.",
                       "Essential Eight strategy names are carried on rules where authored; the OSCAL data gives maturity level, not strategy.",
                       "Only the current ISM release is bundled; diff_release lists controls updated in it.",
                       "Not an IRAP assessment and not legal advice."]}


# ---- prompts -----------------------------------------------------------------------------------------------------------------
@mcp.prompt()
def ism_requirements(path: str, entity_type: str = "non_corporate_commonwealth", classification: str = "PROTECTED", phase: str = "implement") -> str:
    """Derive the ISM requirements for a system, review its repository, and propose what to build and evidence next."""
    return f"""Derive the ISM requirements for the system at {path} ({entity_type}, {classification}, phase: {phase}).

1. assess_applicability: say whether the PSPF binds, whether Essential Eight Maturity Level Two is mandatory, and whether authorisation and IRAP apply.
2. scope_system: report how many controls apply and where they concentrate. Do not list control text.
3. review_project (summary first). Read the documents it lists as unread. Say which findings you could settle from the material and which need the team.
4. Report blockers, then gaps, then what is coming (plan). For each blocker or gap say the control, the mapping fidelity, and what would settle it.
   Use interrogate for the few that matter. Ask the user only what the repository and documents cannot answer.
5. Offer track_plan if the team wants control tracking, and draft_ssp_annex when statuses are recorded.
This is decision support, not an IRAP assessment."""


@mcp.prompt()
def irap_readiness(path: str, entity_type: str = "non_corporate_commonwealth", classification: str = "PROTECTED") -> str:
    """Prepare for an IRAP assessment: preconditions, open findings, and the evidence an assessor will ask for."""
    return f"""Prepare the system at {path} ({entity_type}, {classification}) for IRAP assessment.

1. authorisation_readiness with phase 'assess': list each precondition as found, missing or found-but-unread, and read what is unread.
2. review_project with phase 'assess' and detail=full for blockers and gaps. Walk the open questions; each says what evidence settles it.
3. track_gaps (if a manifest exists) and track_impact; then draft_ssp_annex for the controls matrix.
4. Close with an ordered list: what to write, what to evidence, what to fix, before the assessor arrives.
Do not predict assessment outcomes; only an assessor sets those."""


def main(http: bool = False, host: str = "127.0.0.1", port: int = 8000) -> None:
    if http:
        if not allowed_roots():
            raise SystemExit(f"HTTP mode reads files on behalf of remote clients. Set {ROOTS_ENV} or pass --root DIR to limit which directories may be read.")
        mcp.settings.host, mcp.settings.port = host, port
        mcp.run(transport="streamable-http")
    else:
        mcp.run()
