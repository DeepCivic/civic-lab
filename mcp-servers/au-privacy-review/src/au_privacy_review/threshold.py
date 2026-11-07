"""Privacy threshold assessment: does this project need a privacy impact assessment (PIA)?

privacy-review: ignore-file

A threshold assessment is the short, documented check a team does before (or instead of) a full
PIA. It answers three things: does the project involve personal information; does it involve any
factor that points to significant privacy impact; and so is a full PIA needed. For Australian
Government agencies the answer has legal force: the Agencies APP Code s 12 requires a PIA for every
high privacy risk project.

This module combines evidence from a code scan with the team's own answers. The scan can establish
many factors (sensitive fields, biometrics, tracking, overseas recipients). Others only people can
answer (scale, data matching, whether handling is new or changed, community expectations). Those
stay `unknown` until answered, and the outcome says so.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from . import __version__
from .kb import KB

VULNERABLE_CONTEXT = {"ndis", "aged care", "child protection", "out-of-home care", "out of home care", "youth justice", "homeless",
                      "homelessness", "refugee", "asylum", "domestic violence", "family violence", "mental health", "disability",
                      "disabilities", "addiction", "rehab", "rehabilitation"}
DIGITAL_ID_ROLES = {"accredited_entity": "accredited entity (identity, attribute or exchange service provider)",
                    "relying_party": "participating relying party"}
APP11_DETECTORS = {"weak-password-hashing", "hardcoded-secret", "iac-public-storage", "tls-verification-disabled", "mfa-disabled",
                   "plaintext-http-endpoint"}


@dataclass
class Question:
    id: str
    question: str
    weight: str  # "gate", "high" or "medium"
    guidance: str
    entries: tuple[str, ...] = ()
    detect: Callable[[dict], list[str]] | None = None

    def brief(self) -> dict:
        return {"id": self.id, "question": self.question, "weight": self.weight, "guidance": self.guidance,
                "detectable_from_code": self.detect is not None, **({"related_entries": list(self.entries)} if self.entries else {})}


def _findings(scan: dict, *detectors: str, min_sev: str | None = None) -> list[str]:
    order = ["info", "low", "medium", "high", "critical"]
    out = []
    for f in scan.get("findings", []):
        if f["detector"] in detectors and (min_sev is None or order.index(f["severity"]) >= order.index(min_sev)):
            loc = f.get("file", "(repository)") + (f":{f['line']}" if f.get("line") else "")
            out.append(f"{f['id']} {f['detector']} at {loc}")
    return out


def _inv(scan: dict, *cats: str) -> list[str]:
    pi = scan.get("data_inventory", {}).get("personal_information", {})
    return [f"{pi[c]['label']}: {', '.join(pi[c]['fields'][:6])}" for c in cats if c in pi]


def _d_handles(s: dict) -> list[str]:
    inv = s.get("data_inventory", {})
    ev = _inv(s, *inv.get("personal_information", {}).keys())
    if inv.get("collection_points"):
        ev.append(f"{len(inv['collection_points'])} collection point(s), e.g. {inv['collection_points'][0]['file']}")
    ev += [f"recipient: {r['name']} ({r['kind']})" for r in inv.get("recipients", []) if r["kind"] not in ("service provider (SDK)", "hosting provider")][:3]
    return ev


def _d_sensitive(s: dict) -> list[str]:
    ev = _inv(s, "sensitive") + _findings(s, "sensitive-fields-no-consent")
    ctx = s.get("context", {}).get("sensitive_context_terms") or []
    if ctx:
        ev.append(f"repository describes a sensitive setting: {', '.join(ctx[:6])}")
    return ev


def _d_vulnerable(s: dict) -> list[str]:
    ev = _inv(s, "children")
    ctx = [t for t in (s.get("context", {}).get("sensitive_context_terms") or []) if t in VULNERABLE_CONTEXT]
    if ctx:
        ev.append(f"setting suggests people who may be vulnerable: {', '.join(ctx)}")
    return ev


def _d_overseas(s: dict) -> list[str]:
    ov = s.get("data_inventory", {}).get("overseas", {})
    ev = [f"non-Australian region: {r}" for r in ov.get("non_australian_regions", [])]
    ev += [f"likely overseas recipient: {r}" for r in ov.get("likely_overseas_recipients", [])]
    return ev


def _d_digital_id(s: dict) -> list[str]:
    ctx = s.get("context", {})
    ev = [f"Digital ID reference: {t}" for t in ctx.get("digital_id_terms") or []]
    if ctx.get("digital_id_role") in DIGITAL_ID_ROLES:
        ev.insert(0, f"stated role: {DIGITAL_ID_ROLES[ctx['digital_id_role']]}")
    return ev


def _d_third_party(s: dict) -> list[str]:
    return [f"{r['name']} ({r['kind']})" for r in s.get("data_inventory", {}).get("recipients", [])]


def _d_secondary(s: dict) -> list[str]:
    return [f"{r['name']}: personal information in prompts or context may be a new use or disclosure"
            for r in s.get("data_inventory", {}).get("recipients", []) if r["kind"] == "AI API"]


QUESTIONS: list[Question] = [
    Question("handles_personal_information", "Will the project collect, use, store or disclose personal information (information or an opinion "
             "about an identified or reasonably identifiable individual)?", "gate",
             "Include indirect identifiers: device IDs, IP addresses, hashed emails, location and photos can all be personal information.",
             ("H-IDENTIFIERS-ARE-PERSONAL",), _d_handles),
    Question("new_or_changed_handling", "Is this a new system, or a change to how personal information is already handled (new collection, "
             "new purpose, new recipients, new technology, or moving to a new platform)?", "gate",
             "For agencies, the Agencies APP Code s 12(2) test turns on 'new or changed ways of handling personal information'. "
             "If nothing changes, check that an existing PIA still covers the system as built."),
    Question("sensitive_information", "Will it handle sensitive information: health, genetic or biometric information, racial or ethnic "
             "origin, political opinions or membership, religious or philosophical beliefs, trade union membership, sexual orientation "
             "or practices, or criminal record?", "high", "Includes inferences: a fertility clinic's booking page reveals health information.",
             ("R-APP3.3-SENSITIVE-WITHOUT-CONSENT", "H-TRACKING-PIXEL-SENSITIVE"), _d_sensitive),
    Question("biometrics_or_surveillance", "Does it use facial recognition or other biometrics, or monitor people (CCTV analytics, session "
             "recording, keystroke, camera, microphone or screen capture)?", "high", "",
             ("H-FRT-PROPORTIONALITY", "H-SURVEILLANCE-TORT"),
             lambda s: _inv(s, "biometric") + _findings(s, "biometric-processing", "session-replay", "covert-capture", "hedged-notice-language")),
    Question("automated_decisions", "Will a computer program make, or substantially and directly assist, decisions that could significantly "
             "affect individuals' rights or interests (eligibility, pricing, risk scores, approvals)?", "high",
             "From 10 December 2026 APP 1.7-1.9 require privacy policies to describe these decisions.",
             ("R-APP1.7-AUTOMATED-DECISIONS",), lambda s: _findings(s, "automated-decision")),
    Question("vulnerable_individuals", "Does it involve children or young people, or people who may be vulnerable (patients, people with "
             "disability, people in crisis, people experiencing family violence, homelessness or the justice system)?", "high",
             "Vulnerability raises the impact of any misuse and lowers the weight that can be placed on consent.", (), _d_vulnerable),
    Question("large_scale", "Will it handle personal information about a large number of people, a whole customer base or a population "
             "group, or large volumes about each person?", "high",
             "Scale multiplies the harm of a breach and is a factor in whether a breach is an eligible data breach. Personal "
             "information about 20,000 or more people is 'business critical data' under the SOCI Act s 5; a service storing or "
             "processing it for a government body may be a critical infrastructure asset (s 12F).",
             ("H-BREACH-ASSESSMENT-READINESS",)),
    Question("data_matching_or_linkage", "Will it match, link or combine datasets about individuals (including with other organisations, ad "
             "platforms or public data), or create profiles?", "high", "Hashed-email audience matching counts.",
             ("H-IDENTIFIERS-ARE-PERSONAL",), lambda s: _findings(s, "hashed-identifier-sharing")),
    Question("indirect_collection", "Will it collect personal information from somewhere other than the individual (scraping, data brokers, "
             "other agencies or businesses, social media)?", "high", "", ("H-SCRAPING-PUBLIC-DATA",),
             lambda s: _findings(s, "scraping-personal-data")),
    Question("digital_id_system", "Is the project part of, or does it rely on, the Australian Government Digital ID System (as an "
             "accredited identity, attribute or exchange service provider, or as a participating relying party)?", "high",
             "The Digital ID Act 2024 adds rules on top of the APPs: express consent for biometrics, no tracking of service use, "
             "prohibited attributes, limits on unique identifiers, and voluntary use. Its Accreditation Rules can require PIAs (s 28(2)(b)).",
             ("R-DIGID-BIOMETRIC-EXPRESS-CONSENT", "R-DIGID-NO-PROFILING", "R-DIGID-PROHIBITED-ATTRIBUTES", "R-DIGID-UNIQUE-IDENTIFIER",
              "R-DIGID-VOLUNTARY"), _d_digital_id),
    Question("tracking_and_profiling", "Does it track people's online behaviour or location (advertising pixels, analytics SDKs collecting "
             "automatically, device location)?", "medium", "", ("H-TRACKING-PIXEL-SENSITIVE", "H-LOCATION-TRANSPARENCY", "H-VENDOR-DEFAULT-DRIFT"),
             lambda s: _findings(s, "tracking-pixel", "sdk-autocollect-defaults", "location-collection")),
    Question("government_identifiers", "Will it collect or use government related identifiers (TFN, Medicare number, passport, driver "
             "licence, Centrelink CRN)?", "medium", "APP 9 limits adopting, using and disclosing them; TFNs have their own rule.",
             ("R-APP9-GOVERNMENT-IDENTIFIER", "R-TFN-MISHANDLING"),
             lambda s: _inv(s, "government_identifier") + _findings(s, "government-identifier-as-key", "tfn-handling")),
    Question("overseas_disclosure", "Will personal information be stored or processed outside Australia, or disclosed to overseas "
             "recipients (including cloud and SaaS providers)?", "medium", "", ("H-OVERSEAS-PROCESSING",), _d_overseas),
    Question("third_party_disclosure", "Will personal information be disclosed to other organisations or service providers (processors, "
             "partners, vendors, other agencies)?", "medium", "", ("R-APP6-SECONDARY-USE",), _d_third_party),
    Question("secondary_use", "Will personal information be used for a purpose other than the one it was collected for (analytics, AI "
             "training or prompts, research, marketing)?", "medium", "", ("R-APP6-SECONDARY-USE",), _d_secondary),
    Question("security_weaknesses", "Are there known weaknesses in how the information will be protected (public storage, weak credentials, "
             "missing MFA, unverified TLS)?", "medium", "These are APP 11 issues to fix whatever the threshold outcome.",
             ("R-APP11-PUBLIC-STORAGE", "R-APP11-CREDENTIALS", "R-APP11-TRANSPORT", "H-MFA-AND-PRIVILEGED-ACCESS"),
             lambda s: _findings(s, *APP11_DETECTORS, min_sev="high")),
    Question("community_expectations", "Would the people affected be surprised by, or object to, how their information is handled? Is "
             "public, media or stakeholder concern likely?", "medium", "Consider asking representatives of the people affected."),
]
QUESTION_IDS = [q.id for q in QUESTIONS]
BY_QUESTION = {q.id: q for q in QUESTIONS}

# What would settle each question: the evidence to look for, and who usually holds it.
RESOLVE = {
    "handles_personal_information": "A data flow or the data model: any field, log, upload or analytics event about a person. Developers or the data model owner.",
    "new_or_changed_handling": "The project brief or business case: what is new, what it replaces, and whether an existing PIA covers it. Project owner.",
    "sensitive_information": "The data model and the setting: health, biometric or other sensitive fields, or a service that reveals them. Product owner.",
    "biometrics_or_surveillance": "The solution design: any use of faces, voice or fingerprints (and whether it identifies or verifies), or recording of people.",
    "automated_decisions": "The decision logic: which outcomes for people are made or substantially shaped by a program, and whether a person reviews them.",
    "vulnerable_individuals": "Who the service is for and who else it touches. Service owner or user research.",
    "large_scale": "Expected numbers of people and records, and whether it covers a whole customer base or population. Business case or capacity planning.",
    "data_matching_or_linkage": "Integrations and analytics: any joining of datasets about people, audience matching or profiling. Data or analytics lead.",
    "indirect_collection": "Data sources other than the person: brokers, partners, other agencies, public or social media data. Data or integration lead.",
    "digital_id_system": "Sign-in and identity verification design: whether myID or another accredited digital ID is used, and in what role.",
    "tracking_and_profiling": "Analytics and marketing tags, SDKs and location features. Marketing or web analytics owner.",
    "government_identifiers": "The data model and forms: TFN, Medicare, passport, licence or CRN fields, and whether any is used as a key.",
    "overseas_disclosure": "Hosting regions, vendors, support teams and AI services, and the countries they operate from. Contracts or the vendor register.",
    "third_party_disclosure": "Vendors, processors, partners and agencies that receive personal information. Contracts or the data flow diagram.",
    "secondary_use": "Every purpose the data is used for beyond the original one: analytics, AI training or prompts, research, marketing.",
    "security_weaknesses": "Security assessment or penetration test results, and the infrastructure configuration. Security team.",
    "community_expectations": "How the people affected would react: consultation, complaints, media or advocacy interest. Stakeholder or communications lead.",
}
WEIGHT_WHY = {"gate": "Decides whether a PIA is needed at all.", "high": "A yes on its own points to a full PIA.",
              "medium": "Two or more together point to a PIA; each is also an issue to handle directly."}


def questions() -> list[dict]:
    return [q.brief() for q in QUESTIONS]


def assess(kb: KB, scan: dict | None, answers: dict[str, bool] | None = None, *, entity_type: str | None = None,
           project_name: str | None = None, project_description: str | None = None, as_at: dt.date | None = None,
           digital_id_role: str | None = None, observations: list[dict] | None = None) -> dict:
    """Threshold assessment from a scan (or review) and what is known.

    Precedence for each question: the team's answer, then observations (facts recorded from documents or
    the team, with their source), then code evidence, then mentions in prose documents (``indicated``:
    read the passage and confirm). A question is ``not detected`` only when code was actually examined.
    """
    from .observations import BY_ID as KINDS

    answers = dict(answers or {})
    if digital_id_role not in (None, "unknown", "none", *DIGITAL_ID_ROLES):
        raise ValueError(f"digital_id_role must be one of: none, unknown, {', '.join(DIGITAL_ID_ROLES)}")
    if digital_id_role in DIGITAL_ID_ROLES:
        answers.setdefault("digital_id_system", True)
    elif digital_id_role == "none":
        answers.setdefault("digital_id_system", False)
    unknown_ids = sorted(set(answers) - set(QUESTION_IDS))
    if unknown_ids:
        raise ValueError(f"unknown question id(s): {', '.join(unknown_ids)}; use list_threshold_questions")
    scan = scan or {}
    if digital_id_role in DIGITAL_ID_ROLES and scan:
        scan = {**scan, "context": {**scan.get("context", {}), "digital_id_role": digital_id_role}}
    as_at = as_at or dt.date.today()
    cov = scan.get("coverage") or {}
    code_examined = cov.get("code_examined", bool(scan))
    mentions = scan.get("doc_mentions") or {}
    obs_by_q: dict[str, list[dict]] = {}
    for o in observations or []:
        k = KINDS.get(o["kind"])
        if k and k.question:
            obs_by_q.setdefault(k.question, []).append(o)
        if k and k.sensitive and o["present"] and k.question != "sensitive_information":  # biometrics for identification, health settings
            obs_by_q.setdefault("sensitive_information", []).append(o)
    rows = []
    for q in QUESTIONS:
        code_ev = q.detect(scan) if (q.detect and scan) else []
        obs = obs_by_q.get(q.id, [])
        obs_yes = [o for o in obs if o["present"]]
        obs_no = [o for o in obs if not o["present"]]
        doc_ev = [f"{m['file']}:{m['line']}: \u201c{m['excerpt']}\u201d" for k in KINDS.values() if k.question == q.id
                  for m in mentions.get(k.id, [])]
        evidence = [f"observed: {o['fact']} ({o['source']})" for o in obs_yes] + code_ev
        stated = answers.get(q.id)
        if stated is not None:
            answer, basis = ("yes" if stated else "no"), "stated by the team"
        elif obs_yes:
            answer, basis = "yes", "observed: " + "; ".join(sorted({o["source"] for o in obs_yes}))[:200]
        elif obs_no and not code_ev:
            answer, basis = "no", "confirmed absent: " + "; ".join(sorted({o["source"] for o in obs_no}))[:200]
        elif code_ev:
            answer, basis = "yes", "detected in code"
        elif doc_ev:
            answer, basis = "indicated", "mentioned in documents; read the passage and confirm"
        elif q.detect and scan and code_examined:
            answer, basis = "not detected", "nothing found in code; confirm with the team"
        elif q.detect and scan:
            answer, basis = "unknown", "no code was examined, so the scan could not look for this"
        else:
            answer, basis = "unknown", "not in the code or documents examined; needs evidence or an answer"
        if answer in ("indicated", "unknown", "not detected") or not evidence:
            evidence = evidence + [f"document: {d}" for d in doc_ev]
        row = {"id": q.id, "question": q.question, "weight": q.weight, "answer": answer, "basis": basis, "evidence": evidence[:8]}
        said_no = stated is False or (stated is None and obs_no and not obs_yes)
        if said_no and code_ev:
            row["conflict"] = ("The team answered no, but the scan found evidence. Record why the evidence does not apply." if stated is False
                               else "An observation says no, but the scan found evidence. Record why the evidence does not apply.")
        if q.entries:
            row["related_entries"] = list(q.entries)
        rows.append(row)
    by = {r["id"]: r for r in rows}

    high_yes = [r["id"] for r in rows if r["weight"] == "high" and r["answer"] == "yes"]
    med_yes = [r["id"] for r in rows if r["weight"] == "medium" and r["answer"] == "yes"]
    open_ids = [r["id"] for r in rows if r["answer"] in ("unknown", "indicated")]
    indicated = [r["id"] for r in rows if r["answer"] == "indicated"]
    not_detected = [r["id"] for r in rows if r["answer"] == "not detected"]
    high_open = [i for i in open_ids if by[i]["weight"] in ("high", "gate")]
    handles = by["handles_personal_information"]["answer"]
    # A high-impact factor (biometrics, automated decisions about people, large numbers of people ...) implies personal
    # information. Recipients and hosting regions alone do not: a payment SDK says nothing about what is sent to it.
    pi_confirmed = handles == "yes" or bool(high_yes)
    # The same SaaS SDKs make both 'third party' and 'overseas' true. Found only in code, they are one factor, not two.
    med_count = len(med_yes)
    recip = {"overseas_disclosure", "third_party_disclosure"}
    if recip <= set(med_yes) and all(by[i]["basis"] == "detected in code" for i in recip):
        med_count -= 1

    if handles == "no":
        outcome, label = "pia_not_indicated", "A PIA is not indicated: the project does not handle personal information."
        reasons = ["The team states the project does not handle personal information. Keep this record, and revisit it if that changes."]
    elif high_yes or (med_count >= 2 and pi_confirmed):
        outcome, label = "pia_recommended", "A full privacy impact assessment is recommended."
        reasons = ([f"High-impact factor(s): {', '.join(high_yes)}."] if high_yes else []) + \
                  ([f"Several other factors combine: {', '.join(med_yes)}."] if med_count >= 2 else
                   [f"Also present: {', '.join(med_yes)}."] if med_yes else [])
    elif med_yes and not pi_confirmed:
        outcome, label = "undetermined", "Undetermined: factors were found, but not that the project handles personal information."
        reasons = [f"Present: {', '.join(med_yes)}. These matter only if personal information reaches them, and none was confirmed. "
                   "Confirm what data the project handles and what it sends to these recipients."]
        if high_open:
            reasons.append(f"Also unanswered: {', '.join(high_open)}.")
    elif high_open:
        outcome, label = "undetermined", "Undetermined: open questions need answering before relying on this outcome."
        reasons = [f"No high-impact factor found so far. Still open: {', '.join(high_open)}."] + \
                  ([f"Present: {', '.join(med_yes)}."] if med_yes else [])
    elif med_yes:
        outcome, label = "targeted_review", "A full PIA is not indicated on these answers; address the factor identified and keep this record."
        reasons = [f"One factor present: {med_yes[0]}. Deal with it directly (for example a privacy policy update, contract terms or a security fix)."]
    elif handles == "not detected":
        outcome, label = "pia_not_indicated", "A PIA is not indicated on current evidence: no personal information was found in the code."
        reasons = ["No personal-information fields, collection points or recipients were found in the code, and the team's answers raise "
                   "no factor. Confirm the project handles no personal information (including logs, analytics and support channels)."]
    else:
        outcome, label = "pia_not_indicated", "A PIA is not indicated on these answers. Keep this record and revisit it if the project changes."
        reasons = ["No factor pointing to significant privacy impact was found or stated."]
    if handles in ("unknown", "not detected", "indicated") and not pi_confirmed and outcome not in ("pia_not_indicated",):
        reasons.append("Whether the project handles personal information is itself unconfirmed.")
    if indicated:
        reasons.append(f"Mentioned in documents but not yet confirmed: {', '.join(indicated)}. Read the passages and record what they say.")
    if not_detected and outcome in ("undetermined", "targeted_review", "pia_not_indicated"):
        reasons.append(f"Not found in code, so treated as absent until the team confirms: {', '.join(not_detected)}.")

    A = kb.data["applicability"]
    citations = [A["pia_definition"]]
    agency = None
    if entity_type == "agency":
        changed = by["new_or_changed_handling"]["answer"]
        agency = {"pia_mandatory_if_high_privacy_risk": True, "citations": [A["agency_pia"], A["high_privacy_risk_project"]]}
        if outcome == "pia_recommended" and changed not in ("no",):
            agency["assessment"] = ("Likely a high privacy risk project under the Agencies APP Code s 12(2), so a PIA is mandatory "
                                    "(s 12(1)) unless the agency reasonably considers otherwise and records why.")
            outcome, label = "pia_required", "A PIA is likely mandatory: this looks like a high privacy risk project (Agencies APP Code s 12)."
        elif outcome == "pia_recommended":
            agency["assessment"] = ("Handling is stated not to be new or changed. The s 12(2) test turns on new or changed handling; confirm "
                                    "an existing PIA covers the system as built and is current.")
        else:
            agency["assessment"] = "On these answers the project does not appear to be high privacy risk. Record this assessment."
    no_pia = kb.entry("H-NO-PIA-HIGH-RISK")
    if no_pia:
        citations += [c for c in no_pia["citations"] if c["source"] != "agencies-app-code-2017"]

    regime_questions = []
    if by["digital_id_system"]["answer"] == "yes":
        citations += [A["digital_id_pia_definition"], A["digital_id_pia_rules"]]
        reasons.append("Digital ID Act 2024: accredited entities may be required by the Accreditation Rules to conduct and report on "
                       "PIAs (s 28(2)(b)), and the Act's privacy rules apply on top of the APPs.")
        if digital_id_role == "accredited_entity":
            citations.append(A["digital_id_personal_information"])
            regime_questions.append({"id": "R-DIGID-UNIQUE-IDENTIFIER", "question": "Where does the digital ID unique identifier go? It "
                                     "may be disclosed only to the accredited entity or relying party it was given to (s 47)."})
            regime_questions.append({"id": "R-DIGID-PROHIBITED-ATTRIBUTES", "question": "Do any attribute sources supply racial or ethnic "
                                     "origin, political, religious or philosophical, or sexual orientation information? These may not be "
                                     "collected, and unsolicited ones must be destroyed (s 44)."})
        elif digital_id_role == "relying_party":
            citations.append(A["digital_id_relying_party"])
            regime_questions.append({"id": "R-DIGID-VOLUNTARY", "question": "Is there a reasonably accessible way to use the service "
                                     "without a digital ID, on terms that are not substantially less favourable (s 74)?"})
        else:
            regime_questions.append({"id": "digital_id_system", "question": "Is the entity an accredited entity or a participating "
                                     "relying party? Re-run with digital_id_role so the Digital ID Act rules are linked to the findings."})
    if by["large_scale"]["answer"] == "yes":
        citations += [A["soci_business_critical_data"], A["soci_data_asset"]]
        regime_questions.append({"id": "large_scale", "question": "Does the system store or process personal information about 20,000 "
                                 "or more people for a Commonwealth, State or Territory body? If so, it may be a critical data storage or "
                                 "processing asset under the SOCI Act (s 12F), with cyber incident reporting within 12 or 72 hours "
                                 "alongside the NDB scheme."})

    def named(cs: list[dict]) -> list[dict]:
        out = []
        for c in cs:
            src = kb.source(c["source"]) or {}
            out.append({**c, "citation": src.get("citation", c["source"]), **({"status": src["status"]} if src.get("status") else {})})
        return out

    citations = named(citations)
    if agency:
        agency["citations"] = named(agency["citations"])

    issues = _issues(scan)
    open_questions = [{"id": i, "question": by[i]["question"], "resolve": RESOLVE.get(i, "")} for i in open_ids] + regime_questions
    for f in scan.get("findings", [])[:40]:
        for e in f["kb"]:
            ent = kb.entry(e["id"]) or {}
            for qq in ent.get("questions_for_agent", [])[:1]:
                if all(qq != o["question"] for o in open_questions):
                    open_questions.append({"id": e["id"], "question": qq})
    name = project_name or (Path(scan["root"]).name if scan.get("root") else "") or "Unnamed project"
    result = {
        "project": name, "as_at": as_at.isoformat(), "outcome": outcome, "outcome_label": label, "reasons": reasons,
        "factors": {"high": high_yes, "medium": med_yes, "unanswered": open_ids, "indicated": indicated, "not_detected": not_detected},
        "questions": rows, **({"agency_obligation": agency} if agency else {}),
        "data_inventory": scan.get("data_inventory"), "issues_for_pia": issues, "open_questions": open_questions,
        "citations": citations,
        "next_steps": _next_steps(outcome, open_ids, issues),
        "caveats": ["A threshold assessment is a documented judgement by the team, not a tool output. Review every answer.",
                    "Code evidence shows what the system can do, not what it does in production or what people were told.",
                    "Not legal advice."],
        "kb_built": kb.built, "tool_version": __version__,
    }
    result["report_markdown"] = render_markdown(result, project_description)
    return result


def _issues(scan: dict) -> list[dict]:
    order = ["info", "low", "medium", "high", "critical"]
    fs = scan.get("findings", [])
    if any("level" in f for f in fs):  # a review: carry the critical and high levels
        keep = [f for f in fs if f.get("level") in ("critical", "high") and f.get("kb")]
    else:
        keep = [f for f in fs if f.get("kb") and (order.index(f["severity"]) >= 3 or (f["tier"] == "rule" and f["severity"] == "medium"))]
    def provision(f: dict) -> str:
        e = next((x for x in f["kb"] if x["kind"] == "rule"), f["kb"][0])
        return (e["provisions"] or [""])[0]

    return [{"id": f["id"], **({"level": f["level"]} if f.get("level") else {}), "severity": f["severity"], "tier": f["tier"],
             "provision": provision(f), **({"precedent": f["precedent"]["title"]} if f.get("precedent") else {}),
             "message": f["message"], "location": f.get("file", "(repository)") + (f":{f['line']}" if f.get("line") else ""),
             "occurrences": f.get("occurrences", 1), "entries": [e["id"] for e in f["kb"]]} for f in keep]


def _next_steps(outcome: str, open_ids: list[str], issues: list[dict]) -> list[str]:
    steps = []
    if open_ids:
        steps.append(f"Answer the {len(open_ids)} open question(s) and re-run the assessment with those answers.")
    steps.append("Check the data inventory: confirm each item, and add collection and disclosures the code cannot show.")
    if outcome in ("pia_required", "pia_recommended"):
        steps += ["Start a PIA using the OAIC's Guide to undertaking privacy impact assessments; this record, the inventory and the "
                  "issues list are its starting evidence.",
                  "Plan stakeholder consultation and decide who signs the PIA off. Do the PIA before the system is built or changed, "
                  "while findings can still change the design."]
    if issues:
        steps.append(f"Triage the {len(issues)} issue(s) listed: call get_entry for each to check the exceptions before treating it as a breach.")
    steps.append("Have the privacy officer review and sign this record, and file it with the project's governance documents.")
    return steps


def _md_escape(s: str) -> str:
    return str(s).replace("|", "\\|").replace("\n", " ")


def render_markdown(r: dict, description: str | None = None) -> str:
    L: list[str] = []
    L += [f"# Privacy threshold assessment: {r['project']}", "",
          f"**Status:** DRAFT, generated {r['as_at']} by au-privacy-review {r['tool_version']} (knowledge base built "
          f"{r['kb_built']}). Every answer below needs review by the project team and the privacy officer. Not legal advice.", ""]
    L += ["## 1. Project", "", description or "_Describe the project: what it does, who it affects, and what is new or changing._", ""]
    L += ["## 2. Outcome", "", f"**{r['outcome_label']}**", ""] + [f"- {x}" for x in r["reasons"]] + [""]
    if r.get("agency_obligation"):
        L += [f"**Agency obligation.** {r['agency_obligation']['assessment']}", ""]
    L += ["## 3. Threshold questions", "", "| # | Question | Answer | Basis | Evidence |", "|---|---|---|---|---|"]
    for i, q in enumerate(r["questions"], 1):
        ev = "; ".join(q["evidence"][:3]) + (" …" if len(q["evidence"]) > 3 else "")
        ans = q["answer"].upper() + (" ⚠" if q.get("conflict") else "")
        L.append(f"| {i} | {_md_escape(q['question'])} | {ans} | {q['basis']} | {_md_escape(ev) or '-'} |")
    conflicts = [q for q in r["questions"] if q.get("conflict")]
    if conflicts:
        L += ["", "⚠ " + " ".join(f"Q{r['questions'].index(q) + 1}: {q['conflict']}" for q in conflicts)]
    L += [""]
    inv = r.get("data_inventory") or {}
    L += ["## 4. Personal information inventory (from code)", ""]
    if inv.get("personal_information"):
        L += ["| Category | Fields seen | Where |", "|---|---|---|"]
        for c in inv["personal_information"].values():
            L.append(f"| {c['label']} | {_md_escape(', '.join(c['fields'][:10]))} | {_md_escape(', '.join(c['files'][:3]))} |")
        L.append("")
    else:
        L += ["_No personal-information fields found in code._", ""]
    if inv.get("collection_points"):
        L += ["**Collection points:** " + "; ".join(f"{c['file']} ({', '.join(c['fields'][:5])})" for c in inv["collection_points"][:10]), ""]
    if inv.get("stores"):
        L += ["**Stores:** " + ", ".join(s["store"] for s in inv["stores"]), ""]
    if inv.get("recipients"):
        L += ["**Recipients:** " + "; ".join(f"{x['name']} ({x['kind']}{', likely overseas' if x['overseas_likely'] else ''})"
                                             for x in inv["recipients"]), ""]
    ov = inv.get("overseas") or {}
    if ov.get("non_australian_regions"):
        L += ["**Non-Australian regions:** " + ", ".join(ov["non_australian_regions"]), ""]
    L += ["**Retention:** " + (", ".join(inv["retention_mechanisms"][:5]) if inv.get("retention_mechanisms") else
                               "no retention or deletion mechanism found in code"), ""]
    if inv:
        L += [f"_{inv.get('note', '')}_", ""]
    L += ["## 5. Issues to carry into the PIA", ""]
    if r["issues_for_pia"]:
        L += ["| ID | Level | Provision | Issue | Location |", "|---|---|---|---|---|"]
        for x in r["issues_for_pia"]:
            loc = x["location"] + (f" (+{x['occurrences'] - 1} more)" if x["occurrences"] > 1 else "")
            lvl = x.get("level") or f"{x['severity']} ({x['tier']})"
            msg = x["message"] + (f" Resembles: {x['precedent']}." if x.get("precedent") else "")
            L.append(f"| {x['id']} | {lvl} | {_md_escape(x['provision'])} | {_md_escape(msg)} | {_md_escape(loc)} |")
        L += ["", "_Critical: the facts resemble a decided case that went against the entity. High: reads as an APP contravention "
                  "if the facts are as they appear. Check each against its exceptions and distinguishing facts before relying on it._", ""]
    else:
        L += ["_None at high severity._", ""]
    L += ["## 6. Open questions", ""] + ([f"- {q['question']}" + (f" _Evidence: {q['resolve']}_" if q.get("resolve") else "")
                                          for q in r["open_questions"]] or ["_None._"]) + [""]
    L += ["## 7. Next steps", ""] + [f"{i}. {s}" for i, s in enumerate(r["next_steps"], 1)] + [""]
    L += ["## 8. Legal basis", ""]
    for c in r["citations"]:
        sec = " (quoted from an OAIC summary)" if c.get("secondary") else ""
        st = f" Status: {c['status']}" if c.get("status") else ""
        L.append(f"- **{c['citation']} {c.get('pinpoint', '')}**{sec}: \"{c['quote']}\"{st}")
    if r.get("agency_obligation"):
        for c in r["agency_obligation"]["citations"]:
            L.append(f"- **{c['citation']} {c.get('pinpoint', '')}**: \"{c['quote']}\"")
    L += ["", "## 9. Sign-off", "", "| Role | Name | Date |", "|---|---|---|", "| Assessed by | | |", "| Privacy officer review | | |",
          "| Project owner | | |", ""]
    return "\n".join(L)
