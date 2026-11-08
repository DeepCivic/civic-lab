"""privacy-review-au MCP server: a privacy review of an Australian project (code, documents and
recorded observations) under the Australian Privacy Principles, ahead of or as part of a privacy threshold
assessment.

Run with:  privacy-review-au                                  (stdio)
           privacy-review-au serve --http --root /srv/repos   (streamable-HTTP /mcp)
           privacy-review-au serve --allow-live               (enable probe_deployment)
"""

from __future__ import annotations

import datetime as dt
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

from . import kb as _kb
from . import observations as _obs
from . import review as _rv
from . import threshold as _th
from .scan import live as _live
from .scan.scanner import scan_path

ROOTS_ENV = "PRIVACY_REVIEW_AU_ROOTS"

INSTRUCTIONS = """\
Reviews an Australian project for privacy issues under the Australian Privacy Principles (Privacy Act 1988
(Cth), Schedule 1), like a static analyser for privacy: it reads what is available, ranks what it shows,
and says what is still unknown. Every legal statement links to verified citations (legislation, OAIC
determinations, tribunal and court decisions).

Findings come at four levels:
- critical: the facts resemble a decided case that went against the entity (final decisions only);
- high: reads as an APP contravention if the facts are as they appear;
- caution: not enough information, but this may be a privacy issue (says what to confirm);
- info.

How to use it well:
- Start with review_project. Pass the repository path and any design, requirements or architecture
  documents (Markdown, text, HTML) as documents. It needs no answers from anyone.
- Then read what the scanner cannot: PDFs and Word files it lists as unread, Confluence pages, tickets,
  what the user has told you. Record each relevant fact as an observation {kind, fact, source}
  (list_observation_kinds gives the vocabulary and what to look for) and run review_project again.
  Use present: false for facts confirmed absent. Cite the source (file:line, page, or "team").
- Caution findings of type document-mention point at passages that need reading. Read them and record
  what they actually say; do not treat a mention as a fact.
- Work through gaps in priority order. Answer what you can from the material; ask the user only the
  gaps you cannot answer, and say what evidence would settle each. Do not quiz the user through every
  threshold question.
- Use interrogate on a finding id, threshold question, observation kind or KB entry to see the evidence
  for and against, what was looked at, and what would settle it.
- Before calling anything a contravention, check the finding's to_confirm questions and
  exceptions_to_check (get_entry has the full text). A critical finding names the decisions it resembles;
  pay attention to each authority's status.
- threshold_assessment produces the draft threshold assessment record from the same evidence when the team
  is ready to fill one in. assess_applicability says whether the APPs are likely to bind the entity.
- If the project uses the Australian Government Digital ID System, pass digital_id_role.
- Entries marked not_yet_in_force (for example APP 1.7 automated decisions, from 10 December 2026) are
  enacted but not yet commenced. probe_deployment makes network requests and is off unless enabled.
- This is decision support for the team and its privacy officer, not legal advice.
"""

mcp = _Server("privacy-review-au", instructions=INSTRUCTIONS)
F = TypeVar("F", bound=Callable[..., Any])


def anticipated(fn: F) -> F:
    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return fn(*args, **kwargs)
        except (ValueError, KeyError, _live.LiveDisabled, OSError, PermissionError) as exc:
            raise ToolError(str(exc)) from exc

    return wrapper  # type: ignore[return-value]


def allowed_roots() -> list[Path]:
    return [Path(p).expanduser().resolve() for p in os.environ.get(ROOTS_ENV, "").split(os.pathsep) if p.strip()]


def check_path(path: str) -> Path:
    """Resolve a path to scan, refusing anything outside the configured roots (when roots are set)."""
    p = Path(path).expanduser().resolve()
    roots = allowed_roots()
    if roots and not any(p == r or r in p.parents for r in roots):
        raise PermissionError(f"{p} is outside the directories this server may read ({ROOTS_ENV})")
    return p


def _entry_brief(e: dict) -> dict:
    return {"id": e["id"], "kind": e["kind"], "title": e["title"], "provisions": e["provisions"], "severity": e["severity"],
            **({"commences": e["commences"]} if e.get("commences") else {}),
            **({"confidence": e["confidence"]} if e.get("confidence") else {}), "citations": len(e["citations"])}


def _source_view(kb: _kb.KB, sid: str) -> dict:
    s = kb.source(sid)
    if not s:
        raise ValueError(f"unknown source {sid!r}; use kb_status for the source list")
    out = {k: v for k, v in s.items() if k != "anchor_base"}
    if "anchor_base" in s:
        out["provenance"] = s["anchor_base"]
    out["cited_by"] = kb.cited_by(sid)
    return out


SystemKind = Annotated[Literal["auto", "application", "library", "unknown"],
                       Field(description="What the code is. 'auto' detects it; a library skips the 'no privacy policy / no retention' checks")]
SensitiveContext = Annotated[bool | None, Field(description="Override the detected sensitive setting (health, religion, children at risk ...). "
                                                            "None: detect from the README and manifests")]
DigitalIdRole = Annotated[Literal["unknown", "none", "accredited_entity", "relying_party"],
                          Field(description="Role in the Australian Government Digital ID System. 'accredited_entity' (identity, "
                                            "attribute or exchange service provider) links the Digital ID Act 2024 rules to the findings; "
                                            "'relying_party' adds the voluntary-use rule (s 74)")]


def _role(r: str) -> str | None:
    return r if r in ("accredited_entity", "relying_party") else None


Observations = Annotated[list[dict[str, Any]] | None, Field(
    description="Facts recorded from material the scanner cannot read (PDFs, wikis, tickets, the team). Each: "
                "{\"kind\": see list_observation_kinds, \"fact\": what the material says, in a sentence, "
                "\"source\": where (file:line, document and page, or 'team'), \"present\": true (default) or false if confirmed absent}")]
Documents = Annotated[list[str] | None, Field(
    description="Absolute paths to design, requirements or architecture documents (files or folders). Markdown, text and HTML are "
                "read; PDFs, Word files and slides are listed as unread so you can read them and submit observations")]
Answers = Annotated[dict[str, bool] | None, Field(
    description="Team answers by threshold question id (see list_threshold_questions), e.g. {\"large_scale\": true}. "
                "Prefer observations, which carry their source")]
EntityType = Annotated[Literal["organisation", "agency", "unknown"],
                       Field(description="Australian Government agencies must do a PIA for high privacy risk projects")]


def _build(path, documents, observations, answers, entity_type, system_kind, sensitive_context, exclude, digital_id_role,
           project_name=None, project_description=None) -> dict:
    return _rv.build(_kb.load(), check_path(path) if path else None, documents=[check_path(d) for d in documents or []],
                     observations=observations, answers=answers, entity_type=None if entity_type == "unknown" else entity_type,
                     kind=system_kind, sensitive_context=sensitive_context, exclude=exclude, digital_id_role=digital_id_role,
                     project_name=project_name, project_description=project_description)


@mcp.tool()
@anticipated
def review_project(
    path: Annotated[str | None, Field(description="Absolute path to the repository. Omit to review documents and observations only")] = None,
    documents: Documents = None,
    observations: Observations = None,
    answers: Answers = None,
    entity_type: EntityType = "unknown",
    system_kind: SystemKind = "auto",
    sensitive_context: SensitiveContext = None,
    exclude: Annotated[list[str] | None, Field(description="Relative paths to skip")] = None,
    digital_id_role: DigitalIdRole = "unknown",
    min_level: Annotated[Literal["info", "caution", "high", "critical"], Field(description="Lowest level of finding to return")] = "caution",
    project_name: Annotated[str | None, Field(description="Name for the report. Default: the folder name")] = None,
    include_report: Annotated[bool, Field(description="Include report_markdown, a readable summary for a PR comment or the team")] = True,
) -> dict[str, Any]:
    """The main tool: review a project for privacy issues ahead of (or without) a threshold assessment. Reads code and
    documents, takes recorded observations, and returns findings ranked critical (resembles a decided case that went
    against the entity) / high (reads as an APP contravention at face value) / caution (not enough information, may be
    an issue), gaps (specific open questions with why they matter and what evidence would settle them), coverage
    (what was and was not examined), threshold readiness, and the personal-information inventory. Needs no answers."""
    rv = _build(path, documents, observations, answers, entity_type, system_kind, sensitive_context, exclude, digital_id_role,
                project_name)["review"]
    floor = _rv.LEVELS.index(min_level)
    rv["findings"] = [f for f in rv["findings"] if _rv.LEVELS.index(f["level"]) >= floor]
    if not include_report:
        rv.pop("report_markdown", None)
    return rv


@mcp.tool()
@anticipated
def interrogate(
    topic: Annotated[str, Field(description="A finding id from review_project (F003), a threshold question id (large_scale), an "
                                            "observation kind (data_matching) or a KB entry id (H-FRT-PROPORTIONALITY)")],
    path: Annotated[str | None, Field(description="Same as review_project")] = None,
    documents: Documents = None,
    observations: Observations = None,
    answers: Answers = None,
    entity_type: EntityType = "unknown",
    digital_id_role: DigitalIdRole = "unknown",
) -> dict[str, Any]:
    """Everything known about one topic, from the same evidence as review_project: evidence for and against, document
    passages, related findings, what was examined, the KB guidance, the decided cases it resembles, and what would
    settle it. Pass the same path, documents and observations as the review (finding ids depend on them)."""
    bundle = _build(path, documents, observations, answers, entity_type, "auto", None, None, digital_id_role)
    return _rv.interrogate(_kb.load(), bundle, topic)


@mcp.tool()
@anticipated
def list_observation_kinds() -> list[dict[str, Any]]:
    """The vocabulary for observations: each kind, what to look for in documents or ask about, the threshold question it
    answers, the KB entries it links, and the level it produces (critical where it matches a decided-case fact pattern)."""
    return _obs.kinds()


@mcp.tool()
@anticipated
def kb_status() -> dict[str, Any]:
    """What the knowledge base contains: sources (with version, as-at dates and status), rule
    and heuristic counts, the build date, and whether live probing is enabled."""
    kb = _kb.load()
    act = kb.source("privacy-act-1988") or {}
    return {
        "built": kb.built, "rules": len(kb.rules), "heuristics": len(kb.heuristics),
        "citations": sum(len(e["citations"]) for e in kb.rules + kb.heuristics),
        "threshold_questions": len(_th.QUESTIONS),
        "privacy_act_compilation": act.get("anchor_base", {}), "oaic_register_entries": len(kb.register()),
        "sources": [{"id": s["id"], "type": s["type"], "citation": s["citation"], **({"status": s["status"]} if s.get("status") else {})}
                    for s in kb.sources()],
        "live_probe_enabled": _live.live_enabled(),
        "path_roots": [str(r) for r in allowed_roots()] or "unrestricted (stdio)",
        "limitations": [
            "Case law: OALC v7.1.0 (to March 2025) plus OAIC publications and determinations to November 2026. Full texts of "
            "[2025] FCA 1224 and [2026] ARTA 130 were not retrievable; their quotes come from OAIC statements (marked secondary).",
            "Pending proceedings (Medibank, Optus 2022 breach) are represented only by allegations, labelled as such.",
            "Commonwealth law only. State and territory privacy laws (and their PIA expectations) are not assessed.",
            "Digital ID Act 2024 rules are statute-only (no decided authority yet) and depend on the stated role; the Digital ID "
            "Rules and Accreditation Rules are not in the knowledge base. The SOCI Act, TIA Act and Cyber Security Act are cited "
            "only for specific points (business critical data, retained data as personal information, incident and ransomware "
            "reporting periods), not assessed as regimes.",
        ],
    }


@mcp.tool()
@anticipated
def list_threshold_questions() -> list[dict[str, Any]]:
    """The threshold questions, each with its weight (gate, high or medium), guidance, whether the code scan can
    answer it, the evidence that would settle it, and the observation kinds that record it. Answer them from code,
    documents and observations first (review_project); ask the user only what that leaves open."""
    from .observations import KINDS

    return [{**q, "what_would_resolve": _th.RESOLVE.get(q["id"], ""), "record_as": [k.id for k in KINDS if k.question == q["id"]]}
            for q in _th.questions()]


@mcp.tool()
@anticipated
def threshold_assessment(
    path: Annotated[str | None, Field(description="Absolute path to the repository. Omit to assess from documents, observations and answers")] = None,
    documents: Documents = None,
    observations: Observations = None,
    answers: Answers = None,
    entity_type: EntityType = "unknown",
    project_name: str | None = None,
    project_description: Annotated[str | None, Field(description="One or two paragraphs for section 1 of the draft record")] = None,
    system_kind: SystemKind = "auto",
    sensitive_context: SensitiveContext = None,
    exclude: Annotated[list[str] | None, Field(description="Relative paths to skip")] = None,
    digital_id_role: DigitalIdRole = "unknown",
) -> dict[str, Any]:
    """Draft privacy threshold assessment record, for when the team is filling one in: is a PIA needed? Built from the
    same evidence as review_project. Returns the outcome (pia_required, pia_recommended, targeted_review, undetermined or
    pia_not_indicated) with reasons, every threshold question with its answer, basis and evidence, the inventory,
    issues for the PIA (critical and high findings), open questions with the evidence that would settle them,
    verified citations, and `report_markdown`."""
    b = _build(path, documents, observations, answers, entity_type, system_kind, sensitive_context, exclude, digital_id_role,
               project_name, project_description)
    res, rv = b["threshold"], b["review"]
    res["review_summary"] = {"headline": rv["headline"], "by_level": rv["summary"]["by_level"], "coverage": rv["coverage"]}
    return res


@mcp.tool()
@anticipated
def scan_repository(
    path: Annotated[str, Field(description="Absolute path to the repository or deployment directory")],
    entity_type: Annotated[Literal["organisation", "agency", "unknown"], Field(description="Agencies have a mandatory PIA duty")] = "unknown",
    include_heuristics: bool = True,
    min_severity: Annotated[Literal["info", "low", "medium", "high", "critical"], Field()] = "low",
    exclude: Annotated[list[str] | None, Field(description="Relative paths to skip")] = None,
    max_files: Annotated[int, Field(ge=1, le=100000)] = 20000,
    system_kind: SystemKind = "auto",
    sensitive_context: SensitiveContext = None,
    digital_id_role: DigitalIdRole = "unknown",
) -> dict[str, Any]:
    """Statically scan a directory (code, templates, IaC, config, docs, fixtures) for APP signals.
    Offline; honours .gitignore and skips build output. Returns a personal-information inventory and
    findings (grouped by cause) joined to rules/heuristics with key citations, plus a summary."""
    return scan_path(_kb.load(), check_path(path), max_files=max_files, exclude=exclude,
                     entity_type=None if entity_type == "unknown" else entity_type,
                     include_heuristics=include_heuristics, min_severity=min_severity, kind=system_kind,
                     sensitive_context=sensitive_context, digital_id_role=_role(digital_id_role))


@mcp.tool()
@anticipated
def list_entries(
    kind: Annotated[Literal["all", "rule", "heuristic"], Field(description="Filter by tier")] = "all",
    provision: Annotated[str | None, Field(description="Filter by provision text, e.g. 'APP 11' or 's 26WH'")] = None,
) -> list[dict[str, Any]]:
    """List rules (obvious contraventions) and heuristics (case-law-derived concerns)."""
    kb = _kb.load()
    items = (kb.rules if kind != "heuristic" else []) + (kb.heuristics if kind != "rule" else [])
    if provision:
        p = provision.lower().replace(" ", "")
        items = [e for e in items if any(p in x.lower().replace(" ", "") for x in e["provisions"])]
    return [_entry_brief(e) for e in items]


@mcp.tool()
@anticipated
def get_entry(entry_id: Annotated[str, Field(description="Rule or heuristic id, e.g. R-APP11-PUBLIC-STORAGE")]) -> dict[str, Any]:
    """Full rule or heuristic: requirement or concern, signals, exceptions, remediation, and
    verified citations with pinpoints, quotes, anchors and the status of each authority."""
    kb = _kb.load()
    e = kb.entry(entry_id.strip())
    if not e:
        raise ValueError(f"unknown entry {entry_id!r}; use list_entries")
    out = dict(e)
    out["citations"] = []
    for c in e["citations"]:
        s = kb.source(c["source"]) or {}
        out["citations"].append({**c, "citation": s.get("citation"), "authority_type": s.get("type"),
                                 **({"status": s["status"]} if s.get("status") else {})})
    if e.get("commences"):
        out["in_force"] = dt.date.fromisoformat(e["commences"]) <= dt.date.today()
    return out


@mcp.tool()
@anticipated
def get_app(number: Annotated[int, Field(ge=1, le=13, description="APP number 1-13")]) -> dict[str, Any]:
    """Verbatim text of an Australian Privacy Principle from the current compilation, including
    enacted amendments not yet in force (marked with their commencement date)."""
    kb = _kb.load()
    a = kb.app(number)
    if not a:
        raise ValueError("APP number must be 1-13")
    act = kb.source("privacy-act-1988") or {}
    return {**a, "compilation": act.get("anchor_base", {}), "licence": "CC BY 4.0. Sourced from the Federal Register of Legislation."}


@mcp.tool()
@anticipated
def get_authority(source_id: Annotated[str, Field(description="Source id, e.g. aicmr-2021-54 or fcafc-2017-4")]) -> dict[str, Any]:
    """An authority's citation, status (appeals, review, allegations), provenance and which entries rely on it."""
    return _source_view(_kb.load(), source_id.strip())


@mcp.tool()
@anticipated
def search_kb(query: Annotated[str, Field(description="Keywords, e.g. 'tracking pixel health' or 'APP 8'")],
              limit: Annotated[int, Field(ge=1, le=50)] = 15) -> list[dict[str, Any]]:
    """Keyword search over rules, heuristics, sources and the OAIC determinations register."""
    return _kb.load().search(query, limit)


@mcp.tool()
@anticipated
def assess_applicability(
    entity: Annotated[Literal["company", "individual_sole_trader", "partnership", "trust", "unincorporated_association",
                              "australian_government_agency", "state_or_territory_body"], Field()],
    annual_turnover_aud: Annotated[float | None, Field(description="Previous financial year turnover")] = None,
    provides_health_service: bool = False,
    discloses_personal_information_for_benefit: bool = False,
    collects_personal_information_from_others_for_benefit: bool = False,
    contracted_service_provider_to_commonwealth: bool = False,
    credit_reporting_body: bool = False,
    foreign_entity_with_australian_operations: bool = False,
    digital_id_role: DigitalIdRole = "unknown",
) -> dict[str, Any]:
    """Whether the APPs are likely to bind the entity (s 6C, s 6D small business exemption and its
    s 6D(4) exceptions), with verified citations, plus the Digital ID Act 2024 layer when the entity is
    an accredited digital ID entity or participating relying party. Facts in, reasoned outcome out; not legal advice."""
    out = _applicability(entity, annual_turnover_aud, provides_health_service, discloses_personal_information_for_benefit,
                         collects_personal_information_from_others_for_benefit, contracted_service_provider_to_commonwealth,
                         credit_reporting_body, foreign_entity_with_australian_operations)
    if digital_id_role in ("accredited_entity", "relying_party"):
        A = _kb.load().data["applicability"]
        if digital_id_role == "accredited_entity":
            out["digital_id"] = {
                "applies": True,
                "summary": "As an accredited entity, the Digital ID Act 2024 privacy safeguards apply on top of the APPs, whatever the "
                           "entity's turnover: attributes it holds are personal information (s 35); biometrics need authorisation and "
                           "express consent (s 48); prohibited attributes (s 44); no tracking of service use (s 53); limits on unique "
                           "identifiers (s 47). The Accreditation Rules can require PIAs (s 28(2)(b)).",
                "entries": ["R-DIGID-BIOMETRIC-EXPRESS-CONSENT", "R-DIGID-NO-PROFILING", "R-DIGID-PROHIBITED-ATTRIBUTES", "R-DIGID-UNIQUE-IDENTIFIER"],
                "citations": [A["digital_id_personal_information"], A["digital_id_pia_rules"]]}
        else:
            out["digital_id"] = {
                "applies": True,
                "summary": "As a participating relying party, the entity must keep digital ID voluntary: a reasonably accessible "
                           "alternative on comparable terms (s 74).",
                "entries": ["R-DIGID-VOLUNTARY"], "citations": [A["digital_id_relying_party"]]}
        out["digital_id"]["caveat"] = "The Digital ID Rules and Accreditation Rules are not in the knowledge base."
    return out


def _applicability(entity, annual_turnover_aud, provides_health_service, discloses_personal_information_for_benefit,
                   collects_personal_information_from_others_for_benefit, contracted_service_provider_to_commonwealth,
                   credit_reporting_body, foreign_entity_with_australian_operations) -> dict[str, Any]:
    kb = _kb.load()
    A = kb.data["applicability"]
    reasons, cites = [], []
    if entity == "state_or_territory_body":
        return {"likely_app_entity": False,
                "reasons": ["State and territory authorities are generally governed by state/territory privacy law, not the APPs.",
                            "State and territory privacy laws, and any PIA expectations under them, are not assessed by this server. "
                            "The threshold questions remain a useful structure, but the legal basis must come from the relevant state law."],
                "tort_exposure": True, "citations": [A["tort"]]}
    if entity == "australian_government_agency":
        return {"likely_app_entity": True, "reasons": ["Australian Government agencies are APP entities and are also bound by the Agencies APP Code (mandatory PIAs for high privacy risk projects)."],
                "citations": [A["apps_bind"], A["agency_pia"], A["high_privacy_risk_project"]], "tort_exposure": "limited: see Sch 2 Part 3 exemptions",
                "next": "Use threshold_assessment with entity_type='agency'."}
    triggers = {"provides_health_service": ("health_service", provides_health_service),
                "discloses_personal_information_for_benefit": ("trades_disclose", discloses_personal_information_for_benefit),
                "collects_personal_information_from_others_for_benefit": ("trades_collect", collects_personal_information_from_others_for_benefit),
                "contracted_service_provider_to_commonwealth": ("csp", contracted_service_provider_to_commonwealth),
                "credit_reporting_body": ("credit_reporting", credit_reporting_body)}
    hit = [(k, A[key]) for k, (key, v) in triggers.items() if v]
    over = annual_turnover_aud is not None and annual_turnover_aud > 3_000_000
    if over:
        reasons.append("Turnover above $3,000,000: not a small business operator.")
        cites.append(A["over_threshold"])
    for k, c in hit:
        reasons.append(f"{k.replace('_', ' ')}: excluded from the small business exemption.")
        cites.append(c)
    if over or hit:
        likely: bool | None = True
    elif annual_turnover_aud is None:
        likely = None
        reasons.append("Turnover unknown: if $3,000,000 or less, and no s 6D(4) exception applies, the small business exemption is likely to apply.")
        cites.append(A["small_business"])
    else:
        likely = False
        reasons.append("Turnover $3,000,000 or less and no s 6D(4) exception indicated: likely a small business operator, not bound by the APPs (unless it has opted in or is otherwise prescribed).")
        cites.append(A["small_business"])
    if foreign_entity_with_australian_operations:
        reasons.append("Foreign entities with an Australian link (carrying on business in Australia and collecting or holding personal information in Australia) are covered.")
        cites.append(A["australian_link"])
    cites.append(A["apps_bind"])
    return {"likely_app_entity": likely, "reasons": reasons, "citations": cites,
            "tort_exposure": True, "tort_note": "The Schedule 2 statutory tort for serious invasions of privacy is not limited to APP entities.",
            "threshold_note": "Even where the APPs do not bind, a threshold assessment is good practice and helps manage tort exposure.",
            "caveat": "Related bodies corporate, employee-records and other exemptions are not assessed here. Not legal advice."}


@mcp.tool()
@anticipated
def probe_deployment(url: Annotated[str, Field(description="Public URL of the deployed site")]) -> dict[str, Any]:
    """OPT-IN, NETWORK. Fetch a deployed page (no JavaScript) and its privacy policy, and check HTTPS/HSTS,
    tracking cookies on first response, third-party scripts and pixels, and (by keyword) APP 1.4 policy contents.
    Disabled unless the server was started with PRIVACY_REVIEW_AU_LIVE=1 or --allow-live."""
    kb = _kb.load()
    res = _live.probe(url)
    for f in res["findings"]:
        f["kb"] = [{"id": e, "title": kb.entry(e)["title"]} for e in f.pop("entries") if kb.entry(e)]
    return res


@mcp.prompt()
def privacy_review(path: str = "", documents: str = "", entity_description: str = "") -> str:
    """Review a project for privacy issues from its code and documents, and list what is still unknown."""
    return f"""Review this project for privacy issues under the Australian Privacy Principles.
Repository: {path or '(none given)'}
Documents: {documents or '(none given; look for design, requirements or architecture documents and ask where they are kept)'}
Entity: {entity_description or '(unknown; infer from the material if you can, otherwise say so)'}

1. Call review_project with the path and documents. Do not ask the user anything yet.
2. Read what the scanner could not: files listed in coverage.unread_documents, passages behind each
   document-mention finding, and anything else you can reach. For every relevant fact, add an observation
   {{kind, fact, source}} (list_observation_kinds); use present: false where the material rules something out.
   Then call review_project again with the observations.
3. Report findings by level: critical first (name the decisions each resembles and their status), then high,
   then caution. For each critical or high finding, check its to_confirm questions and exceptions_to_check
   against the material; say which you could settle and how.
4. List the remaining gaps in priority order with what evidence would settle each. Ask the user only for
   those you could not settle from the material, a few at a time, highest priority first.
5. Close with threshold_readiness: where a threshold assessment would land now, and what would change it.
State that these are signals for the team and its privacy officer, not legal advice."""


@mcp.prompt()
def privacy_threshold_assessment(path: str, entity_description: str = "") -> str:
    """Draft a privacy threshold assessment record, answering from the evidence first and asking only what remains."""
    return f"""Draft a privacy threshold assessment for the system at {path}.
Entity: {entity_description or '(unknown; ask, or assume and say so)'}

1. Call assess_applicability with what you know. State whether the APPs likely apply and why.
   If the entity is a state or territory body, say that state law governs and this server does not assess it.
2. Call review_project with the path and any documents. Read the unread documents and the passages behind
   document-mention findings, and record what they establish as observations with their sources.
3. Look at the gaps of type threshold_question that remain. Ask the user only those, grouped, with the
   evidence that would settle each. If the user does not know, leave them unanswered; do not guess.
   Ask about the Australian Government Digital ID System only if the material suggests it.
4. Call threshold_assessment with the path, documents, observations, any answers, entity_type ('agency' for
   Australian Government agencies) and digital_id_role if it applies.
5. Show the personal-information inventory and ask the user to correct it; re-run with corrections.
6. Present the outcome and reasons, then report_markdown as the draft record. Point out conflicts (⚠),
   critical findings and the decisions they resemble, and the open questions.
State clearly that this is a draft for the team and its privacy officer to review, not legal advice."""


def main(http: bool = False, host: str = "127.0.0.1", port: int = 8000) -> None:
    if http:
        if not allowed_roots():
            raise SystemExit(f"HTTP mode reads files on behalf of remote clients. Set {ROOTS_ENV} or pass --root DIR "
                             "to limit which directories may be scanned.")
        mcp.settings.host, mcp.settings.port = host, port
        mcp.run(transport="streamable-http")
    else:
        mcp.run()
