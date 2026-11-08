"""Observations: facts an agent (or the team) has established from material the scanner cannot read.

privacy-review: ignore-file  (this module is made of the phrases it looks for)

The scanner reads code. Design documents, requirements, data flow diagrams, contracts, PDFs and the
team's own knowledge say what the system is *for*, who it affects and where the data goes. An agent
reads those, and records each relevant fact as an observation:

    {"kind": "facial_recognition_identification", "fact": "Cameras match visitors against a banned-customer
     watchlist", "source": "docs/solution-design.md:2"}

The server treats an observation like a detector hit: it answers the threshold question the kind bears
on, links the knowledge-base entries, and matches decided cases. ``present: false`` records that
something is confirmed absent ("no data is sent overseas"), which answers the question "no".

Each kind also has a ``doc_pattern``: a deliberately broad phrase match run over prose documents. A
match is a *mention*, never a finding of fact. It marks the question as ``indicated`` and raises a
caution so the agent reads the passage and records what it actually says.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Kind:
    id: str
    label: str
    look_for: str
    question: str | None = None
    entries: tuple[str, ...] = ()
    level: str = "caution"  # "high" when the fact, as stated, reads as an APP contravention on its face
    precedent: str | None = None
    doc_pattern: str | None = None
    sensitive: bool = False  # establishes a sensitive setting (escalates pixels and session replay in code)
    _rx: re.Pattern | None = field(default=None, compare=False, repr=False)

    def brief(self) -> dict:
        return {"kind": self.id, "label": self.label, "look_for": self.look_for,
                **({"answers_question": self.question} if self.question else {}),
                **({"entries": list(self.entries)} if self.entries else {}),
                "level_when_present": "critical (if the decided cases are final)" if self.precedent else self.level,
                **({"precedent_pattern": self.precedent} if self.precedent else {})}


def _k(*a, **kw) -> Kind:
    k = Kind(*a, **kw)
    if k.doc_pattern:
        object.__setattr__(k, "_rx", re.compile(k.doc_pattern, re.I))
    return k


KINDS: list[Kind] = [
    _k("personal_information", "Personal information handled",
       "Any information about an identifiable person: names, contact details, accounts, device or location data, images.",
       "handles_personal_information",
       doc_pattern=r"\bpersonal (?:information|data|details)\b|\b(?:customer|user|patient|client|member|citizen|staff) (?:records?|data|details|profiles?)\b"),
    _k("new_or_changed_handling", "New or changed handling",
       "A new system, a replacement, a migration, a new purpose, new recipients or new technology.",
       "new_or_changed_handling",
       doc_pattern=r"\breplac(?:e|es|ing) the (?:existing|current|legacy)|\bnew (?:system|platform|service|capability)\b|\bmigrat(?:e|ion|ing)\b|"
                   r"\bpilot\b|\broll-?out\b|\bre-?platform|\bgo-?live\b"),
    _k("sensitive_information", "Sensitive information",
       "Health, genetic, biometric, racial or ethnic origin, political, religious, union, sexual orientation, criminal record; "
       "or a setting that reveals it (a clinic, a counselling service).",
       "sensitive_information", ("R-APP3.3-SENSITIVE-WITHOUT-CONSENT",), sensitive=True,
       doc_pattern=r"\b(?:health (?:information|records?|data|service)|medical|diagnos\w+|mental health|patients?|clinic(?:al)?|"
                   r"religio\w+|ethnic\w*|racial|sexual orientation|criminal (?:record|history)|trade union|genetic)\b"),
    _k("biometric_processing", "Biometrics or facial recognition",
       "Any use of faces, fingerprints, voice or other biometrics. Record whether it identifies people (one-to-many) "
       "or verifies an enrolled, consenting user (one-to-one).",
       "biometrics_or_surveillance", ("H-FRT-PROPORTIONALITY", "R-APP3.3-SENSITIVE-WITHOUT-CONSENT"), sensitive=True,
       doc_pattern=r"\bfacial recognition\b|\bface (?:matching|recognition|detection|verification)\b|\bbiometric\w*|\bfingerprint\w*|"
                   r"\bvoice ?print|\bwatch ?list\b"),
    _k("facial_recognition_identification", "Facial recognition used to identify people",
       "Faces matched one-to-many against a gallery, watchlist or database (identification), especially of the public.",
       "biometrics_or_surveillance", ("H-FRT-PROPORTIONALITY", "R-APP3.3-SENSITIVE-WITHOUT-CONSENT"),
       precedent="P-FRT-IDENTIFICATION", sensitive=True),
    _k("surveillance_monitoring", "Monitoring of people",
       "CCTV analytics, session recording, keystroke, screen, camera or microphone capture, employee monitoring.",
       "biometrics_or_surveillance", ("H-SURVEILLANCE-TORT",),
       doc_pattern=r"\bCCTV\b|\bsession (?:replay|recording)\b|\bkeystroke\w*|\bscreen (?:capture|recording)\b|\bmonitor(?:ing)? (?:staff|employees|users|visitors)\b"),
    _k("automated_decision", "Automated decisions about people",
       "A program makes, or substantially and directly assists, decisions that significantly affect people "
       "(eligibility, approvals, pricing, risk scores).",
       "automated_decisions", ("R-APP1.7-AUTOMATED-DECISIONS",),
       doc_pattern=r"\bautomat(?:ed|ically)\b[^.\n]{0,50}\b(?:approv\w*|declin\w*|decid\w*|decisions?|assess\w*|eligib\w*|scor\w*|reject\w*)|"
                   r"\b(?:eligibility|risk|credit|fraud) scor\w*|\bmachine learning model\b[^.\n]{0,40}\bdecid"),
    _k("vulnerable_individuals", "Children or people who may be vulnerable",
       "Children, patients, people with disability, in crisis, experiencing family violence or homelessness, or in the justice system.",
       "vulnerable_individuals",
       doc_pattern=r"\b(?:children|child|minors?|young people|students|aged care|NDIS|disabilit\w+|homeless\w*|family violence|"
                   r"domestic violence|refugees?|asylum|youth justice|out-of-home care)\b"),
    _k("large_scale", "Large scale",
       "Numbers of people affected (whole customer base, population group), or large volumes about each person.",
       "large_scale",
       doc_pattern=r"\b\d[\d,.]*\s*(?:million|m|k|thousand|000)?\s+(?:customers|users|people|individuals|members|clients|patients|"
                   r"citizens|residents|records|students|visitors)\b|\bnation(?:al|wide)\b|\ball (?:customers|users|residents|Australians)\b"),
    _k("data_matching", "Data matching, linkage or profiling",
       "Matching, linking or combining datasets about people (with other organisations, ad platforms or public data), or building profiles.",
       "data_matching_or_linkage", ("H-IDENTIFIERS-ARE-PERSONAL",),
       doc_pattern=r"\bdata matching\b|\bmatch(?:ed|ing)? (?:against|with)\b|\b(?:data )?linkage\b|\bcombin\w+[^.\n]{0,40}\b(?:data|datasets?|records)\b|"
                   r"\b(?:customer|user) profiles?\b|\bprofiling\b|\bsingle (?:customer|client) view\b|\bcustom audiences?\b"),
    _k("indirect_collection", "Collection from someone other than the individual",
       "Data bought from brokers, received from other organisations or agencies, or taken from social media or public sources.",
       "indirect_collection", ("H-SCRAPING-PUBLIC-DATA",),
       doc_pattern=r"\bdata brokers?\b|\bpurchased data\b|\bdata (?:purchased|bought|acquired) from\b|\b(?:purchased|bought|acquired) from (?:a |an )?(?:data )?brokers?\b|\b(?:buy|bought|acquire[ds]?) (?:\w+ )?data\b|\bthird[- ]party data\b|\bscrap(?:e|ed|ing)\b|"
                   r"\b(?:obtained|sourced|received) from (?:other|partner|third)"),
    _k("scraping_public_data", "Scraping personal information from public sources",
       "Collecting profiles, photos or posts about people from websites or social media at scale.",
       "indirect_collection", ("H-SCRAPING-PUBLIC-DATA",), precedent="P-SCRAPING"),
    _k("digital_id", "Australian Government Digital ID System",
       "Use of myID or another accredited digital ID, as an accredited entity or a participating relying party.",
       "digital_id_system", doc_pattern=r"\bmyID\b|\bmyGovID\b|\bDigital ID (?:System|Act)\b|\baccredited (?:identity|digital ID)"),
    _k("tracking", "Online tracking or location tracking",
       "Advertising pixels, analytics that identify people, retargeting, or device location.",
       "tracking_and_profiling", ("H-TRACKING-PIXEL-SENSITIVE", "H-LOCATION-TRANSPARENCY"),
       doc_pattern=r"\btracking pixels?\b|\bMeta pixel\b|\bretarget\w*|\bremarketing\b|\bconversion API\b|\bgeolocat\w+|\blocation tracking\b"),
    _k("tracking_pixel_sensitive", "Advertising pixels in a sensitive setting",
       "A third-party advertising or conversion pixel on pages that reveal health or other sensitive information.",
       "tracking_and_profiling", ("H-TRACKING-PIXEL-SENSITIVE", "R-APP3.3-SENSITIVE-WITHOUT-CONSENT"),
       precedent="P-PIXEL-SENSITIVE", sensitive=True),
    _k("government_identifier", "Government related identifiers",
       "TFN, Medicare number, passport, driver licence, Centrelink CRN, IHI.",
       "government_identifiers", ("R-APP9-GOVERNMENT-IDENTIFIER",),
       doc_pattern=r"\bTFN\b|\btax file number\b|\bMedicare (?:card|number)\b|\bpassport (?:number|details)\b|\bdriver'?s? licen[cs]e\b|\bCentrelink\b|\bCRN\b"),
    _k("government_identifier_as_key", "Government identifier used as the organisation's own identifier",
       "A government identifier adopted as a customer number, primary key or account identifier.",
       "government_identifiers", ("R-APP9-GOVERNMENT-IDENTIFIER",), level="high"),
    _k("overseas_disclosure", "Storage, processing or disclosure overseas",
       "Hosting, support teams, vendors or AI services outside Australia, with the countries if known.",
       "overseas_disclosure", ("H-OVERSEAS-PROCESSING",),
       doc_pattern=r"\b(?:offshore|overseas|outside (?:of )?Australia)\b|\b(?:US|USA|United States|EU|European|UK|India|Philippines|Singapore)[- ]"
                   r"(?:based )?(?:vendor|provider|team|servers?|hosting|region|data ?cent(?:re|er)|support|analytics|company)\b"),
    _k("third_party_disclosure", "Disclosure to other organisations",
       "Processors, partners, vendors or other agencies that receive personal information.",
       "third_party_disclosure", ("R-APP6-SECONDARY-USE",),
       doc_pattern=r"\bshar(?:e|ed|ing)\b[^.\n]{0,40}\b(?:with|to) (?:our )?(?:partners?|third parties|vendors?|other (?:agencies|organisations))\b|"
                   r"\bdisclos\w+ to\b|\bsend(?:s|ing)? (?:\w+ )?(?:records|data) to\b"),
    _k("secondary_use", "Use for another purpose",
       "Using personal information for a purpose other than the one it was collected for: analytics, AI training or prompts, research, marketing.",
       "secondary_use", ("R-APP6-SECONDARY-USE",),
       doc_pattern=r"\btrain(?:ing)? (?:a |the |our )?(?:model|AI|LLM)\b|\bmarketing purposes\b|\bresearch purposes\b|\brepurpos\w+|\bsecondary use\b"),
    _k("security_weakness", "Known security weakness",
       "Public storage, shared or weak credentials, no MFA on remote or privileged access, unencrypted transfer, deferred security work.",
       "security_weaknesses", ("H-KNOWN-SECURITY-DEBT", "H-MFA-AND-PRIVILEGED-ACCESS")),
    _k("public_storage", "Personal information in publicly accessible storage",
       "A bucket, database or API that exposes personal information without authentication.",
       "security_weaknesses", ("R-APP11-PUBLIC-STORAGE",), level="high"),
    _k("community_concern", "Likely community or media concern",
       "People would be surprised or object; media, stakeholder or advocacy concern is likely or has occurred.",
       "community_expectations",
       doc_pattern=r"\b(?:media|public|community|stakeholder) (?:interest|concern|scrutiny|backlash)\b|\bcontrovers\w+|\bsocial licen[cs]e\b"),
    _k("real_data_in_non_production", "Real personal information in non-production environments",
       "Production data copied into test, training, demo, hackathon or development environments.",
       None, ("H-PROD-DATA-NON-PROD",), precedent="P-REAL-DATA-NONPROD",
       doc_pattern=r"\b(?:copy|copies|snapshot|extract)\b[^.\n]{0,30}\bproduction\b[^.\n]{0,40}\b(?:test|testing|training|dev|development|UAT|staging)\b"),
    _k("bundled_consent", "Bundled or pre-ticked consent",
       "Consent to several purposes (terms, privacy policy, marketing, sharing) given by one action, or pre-selected.",
       None, ("H-CONSENT-DESIGN",), precedent="P-BUNDLED-CONSENT",
       doc_pattern=r"\bbundled consent\b|\bpre-?ticked\b|\bopt-?out by default\b|\bdeemed consent\b|\bby using (?:this|our) (?:site|service|app),? you (?:agree|consent)"),
    _k("hedged_biometric_notice", "Notice says biometric collection only 'may' occur",
       "Signs or notices that say facial recognition or biometrics 'may' be used, rather than that they are in use.",
       None, ("R-APP5-NO-COLLECTION-NOTICE", "H-FRT-PROPORTIONALITY"), precedent="P-HEDGED-NOTICE"),
    _k("no_collection_notice", "No collection notice",
       "Personal information collected with no APP 5 notice at or before the time of collection.",
       None, ("R-APP5-NO-COLLECTION-NOTICE",), level="high"),
    _k("no_privacy_policy", "No privacy policy covering the system",
       "No APP privacy policy, or one that does not cover this system.", None, ("R-APP1.3-NO-PRIVACY-POLICY",), level="high"),
    _k("retention_undefined", "No retention or destruction arrangements",
       "No retention period, or no mechanism to destroy or de-identify personal information that is no longer needed.",
       None, ("H-RETENTION-NO-DESTRUCTION",),
       doc_pattern=r"\b(?:kept|retained|stored|held) (?:indefinitely|forever|permanently)\b|\bno (?:retention|deletion|destruction) (?:policy|period|schedule)\b"),
]
BY_ID = {k.id: k for k in KINDS}


def kinds() -> list[dict]:
    return [k.brief() for k in KINDS]


def normalise(observations: list[dict] | None, answers: dict[str, bool] | None = None) -> list[dict]:
    """Validate observations; fold team answers in as observations with source 'team'."""
    from .threshold import QUESTION_IDS

    out: list[dict] = []
    for i, o in enumerate(observations or []):
        if not isinstance(o, dict) or "kind" not in o:
            raise ValueError(f"observation {i}: each observation needs at least 'kind' and 'fact'")
        kind = str(o["kind"]).strip()
        if kind not in BY_ID:
            raise ValueError(f"observation {i}: unknown kind {kind!r}; use list_observation_kinds")
        fact = str(o.get("fact") or "").strip()
        if not fact:
            raise ValueError(f"observation {i} ({kind}): 'fact' is required: say what the material shows, in a sentence")
        present = o.get("present", True)
        if not isinstance(present, bool):
            raise ValueError(f"observation {i} ({kind}): 'present' must be true or false")
        out.append({"kind": kind, "fact": fact, "source": str(o.get("source") or "(source not given)").strip(), "present": present})
    unknown = sorted(set(answers or {}) - set(QUESTION_IDS))
    if unknown:
        raise ValueError(f"unknown question id(s): {', '.join(unknown)}; use list_threshold_questions")
    return out


def mentions(files: list, *, max_per_kind: int = 6) -> dict[str, list[dict]]:
    """Phrase matches in prose documents, per kind. A mention says 'read this passage', nothing more."""
    from .scan.detectors import _line_of, redact

    out: dict[str, list[dict]] = {}
    for f in files:
        for k in KINDS:
            if k._rx is None or len(out.get(k.id, [])) >= max_per_kind:
                continue
            m = next((m for m in k._rx.finditer(f.text) if not _NEGATED.search(f.text[max(0, m.start() - 60):m.start()])), None)
            if not m or "privacy-review: ignore" in _line_text(f.text, _line_of(f.text, m.start())):
                continue
            ln = _line_of(f.text, m.start())
            line = _line_text(f.text, ln)
            col = max(0, m.start() - f.text.rfind("\n", 0, m.start()) - 1)
            excerpt = line[max(0, col - 90): col + 150].strip()
            out.setdefault(k.id, []).append({"file": f.rel, "line": ln, "match": m.group(0), "excerpt": redact(excerpt, 240)})
    return out


# "We do not disclose ... overseas", "no biometric data is collected": a negation shortly before the phrase.
_NEGATED = re.compile(r"\b(?:not|never|no|without|nor|n't)\b[^.\n]{0,50}$", re.I)


def _line_text(text: str, ln: int) -> str:
    lines = text.splitlines()
    return lines[ln - 1] if 0 < ln <= len(lines) else ""
