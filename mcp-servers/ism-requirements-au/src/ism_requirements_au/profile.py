"""System profile: which obligations bind, which controls are in scope, and which Essentials domains the repository suggests."""

from __future__ import annotations

import re

from .kb import CLASSIFICATION_NAMES, E8_LEVELS, KB, classification_tag

ENTITY_TYPES = ["non_corporate_commonwealth", "corporate_commonwealth", "state_territory", "private_sector", "other"]
HOSTING = ["unknown", "cloud_csp", "on_premises", "hybrid", "gateway"]
FEATURES = ["email", "gateway", "transfer"]
PHASE_LABELS = {"define": "Define the system", "select": "Select controls", "implement": "Implement controls",
                "assess": "Assess controls", "authorise": "Authorise the system", "monitor": "Monitor the system"}


def assess_applicability(kb: KB, entity_type: str, classification: str = "PROTECTED", hosting: str = "unknown",
                         provides_cloud_service: bool = False, provides_gateway: bool = False, supplies_government: bool = True,
                         apra_regulated: bool = False, critical_infrastructure: bool = False) -> dict:
    if entity_type not in ENTITY_TYPES:
        raise ValueError(f"entity_type must be one of {ENTITY_TYPES}")
    tag = classification_tag(classification)
    ncce = entity_type == "non_corporate_commonwealth"
    corp = entity_type == "corporate_commonwealth"
    csp_or_gw = provides_cloud_service or provides_gateway or hosting == "gateway"
    auth = ncce or corp or supplies_government
    if ncce:
        pspf = {"binds": "yes", "basis": "Non-corporate Commonwealth entities must apply the PSPF; section 13 routes system authorisation and section 14 the Essential Eight through the ISM."}
    elif corp:
        pspf = {"binds": "confirm", "basis": "The PSPF applies to corporate Commonwealth entities as Government policy where directed or adopted by the entity; confirm with the entity's security adviser."}
    else:
        pspf = {"binds": "no", "basis": "The PSPF does not bind this entity type directly. The ISM and Essential Eight reach it through contract, a funding condition, or sector regulation."}
    e8_target = "ML2" if (ncce or corp) else None
    mandate = ("mandatory (PSPF section 14)" if ncce else "recommended; confirm entity policy" if corp else "not mandated; adopt as target if supplying government")
    obligations = []
    for o in kb.obligations:
        if o["id"] == "PSPF-15-IRAP" and not csp_or_gw and hosting != "cloud_csp":
            status = "not_triggered"
        elif o["id"] in ("PSPF-15-GATEWAY",) and hosting != "gateway" and not provides_gateway:
            status = "applies_if_internet_connected"
        else:
            status = "binds" if ncce else "confirm" if corp else "contractual_or_voluntary"
        obligations.append({"id": o["id"], "section": o["section"], "status": status, "phase": o["phase"]})
    overlays = []
    if apra_regulated:
        overlays.append({"id": "CPS-234", "note": "APRA CPS 234 expects information security capability commensurate with threats, tested controls and incident notification. It does not mandate the ISM; the ISM is a credible control set to map to it. Confirm with the entity's compliance team."})
    if critical_infrastructure:
        overlays.append({"id": "SOCI", "note": "Security of Critical Infrastructure Act 2018 obligations (risk management program, incident reporting) may apply to critical infrastructure assets. The ISM does not replace them. Confirm the asset class with the responsible regulator."})
    return {
        "classification": CLASSIFICATION_NAMES[tag], "classification_tag": tag, "entity_type": entity_type, "pspf": pspf,
        "authorisation_required": auth, "authorisation_basis": "ISM-0027: system owners obtain an authorisation to operate from the authorising officer." if auth else "Not required unless a contract or regulator asks for it.",
        "e8_target": e8_target, "e8_mandate": mandate,
        "irap": {"required_for_this_system": csp_or_gw, "rule": "Cloud service providers and gateways need an IRAP assessment against the latest ISM within the previous 24 months (PSPF section 15).",
                 "consumer_check": "If this system runs on a cloud service, confirm that service's IRAP report is under 24 months old and covers the services used." if hosting in ("cloud_csp", "hybrid") else None},
        "obligations": obligations, "sector_overlays": overlays,
        "highest_classification_note": "Authorise to the highest classification of the information the system will process, store or communicate (PSPF section 13).",
    }


def scope_system(kb: KB, classification: str, e8_target: str | None = None, features: list[str] | None = None, section: str | None = None,
                 include_ids: bool = False) -> dict:
    tag = classification_tag(classification)
    if e8_target and e8_target not in E8_LEVELS:
        raise ValueError("e8_target must be ML1, ML2 or ML3")
    features = set(features or [])
    wanted = {"always", "software"} | ({"email"} if "email" in features else set()) | ({"gateway"} if "gateway" in features else set()) | ({"transfer"} if "transfer" in features else set())
    rule_controls = {c for r in kb.rules for c in r["controls"]}
    groups: dict[tuple[str, str], dict] = {}
    out_of_scope: dict[str, int] = {}
    total = 0
    for c in kb.controls():
        if not kb.applies(c, tag, e8_target):
            continue
        total += 1
        scope = kb.section_scope(c)
        if scope not in wanted:
            out_of_scope[scope] = out_of_scope.get(scope, 0) + 1
            continue
        g = groups.setdefault((c["guideline"], c["section"]), {"guideline": c["guideline"], "section": c["section"], "controls": 0, "e8": 0, "essentials": 0, "with_rules": 0, "_ids": []})
        g["controls"] += 1
        g["e8"] += bool(c["e8"])
        g["essentials"] += bool(c["essentials"])
        g["with_rules"] += c["id"] in rule_controls
        g["_ids"].append(c["id"])
    rows = sorted(groups.values(), key=lambda g: (g["guideline"], g["section"]))
    if section:
        rows = [g for g in rows if section.lower() in g["section"].lower() or section.lower() in g["guideline"].lower()]
        include_ids = True
    for g in rows:
        ids = g.pop("_ids")
        if include_ids:
            g["ids"] = ids
    return {"classification": CLASSIFICATION_NAMES[tag], "e8_target": e8_target, "applicable_controls": total, "in_project_scope": sum(g["controls"] for g in groups.values()),
            "sections": rows, "outside_project_scope": {k: v for k, v in sorted(out_of_scope.items())},
            "outside_scope_note": "Counted, not listed: physical, personnel, communications infrastructure, media, IT equipment, organisation-level and (unless requested via features) email, gateway and data-transfer controls. They still bind the system owner; they are not repository-evidenceable.",
            "next": "Use get_control for text, or scope_system(section=...) to list ids in one section."}


_DOMAIN_SIGNALS = {
    "Identity services": (r"(?i)cognito|okta|auth0|keycloak|entra|azure[ _-]?ad|oidc|saml|oauth|passport|next-auth|authlib|identity[_-]?provider|aws_iam_(?:user|role)|iam_policy|google_iam", "identity provider, OAuth/OIDC or IAM configuration"),
    "Boundary services": (r"(?i)aws_(?:lb|alb|elb)\b|cloudfront|api[_-]?gateway|\bwaf\b|nginx|traefik|haproxy|ingress|security_group|firewall|virtual_network|\bvpc\b|load[_-]?balancer", "load balancer, gateway, WAF, ingress or network rules"),
    "Privileged environments": (r"(?i)terraform|pulumi|cdk\b|ansible|helm|kubernetes|\brbac\b|bastion|sudoers|\bgithub/workflows|aws_iam_role|clusterrole|deploy(?:ment)?[_-]?key", "infrastructure-as-code, deployment pipelines or role definitions"),
    "Business systems": (r"(?i)postgres|mysql|mariadb|mongodb|dynamodb|prisma|sqlalchemy|django|flask|fastapi|express|rails|spring|\bsql\b|rds_instance|aws_db_instance", "application code and data stores"),
    "User devices": (r"(?i)intune|\bmdm\b|jamf|device[_ -]?compliance|endpoint[_ -]?manager|workstation|laptop", "device management or workstation configuration"),
    "Visibility and response": (r"(?i)cloudtrail|guardduty|security[_ -]?hub|sentinel|siem|splunk|datadog|opentelemetry|fluent|cloudwatch|log[_ -]?analytics|audit[_ -]?log", "logging, monitoring or detection tooling"),
    "Critical processes and services": (r"(?i)backup|restore|disaster[_ -]?recovery|\brto\b|\brpo\b|failover|multi[_-]?az|replica|snapshot|business continuity", "backup, recovery or failover configuration"),
    "Governance and culture": (r"(?i)risk register|security policy|governance|risk management plan|\bcharter\b", "governance or risk documents"),
}


def infer_essentials_domains(files: list, all_paths: list[str], known: list[str]) -> dict:
    """Infer likely Essentials domains from repository evidence. Returned with the evidence so the user can correct it."""
    out = []
    for domain, (rx, label) in _DOMAIN_SIGNALS.items():
        if domain not in known:
            continue
        r = re.compile(rx)
        ev = [p for p in all_paths if r.search(p)][:3]
        for f in files:
            if len(ev) >= 3:
                break
            if f.rel not in ev and not f.is_test and r.search(f.text[:60000]):
                ev.append(f.rel)
        if ev:
            out.append({"domain": domain, "signal": label, "evidence": ev[:3]})
    return {"source": "inferred", "domains": out, "note": "Inferred from file names and contents. Correct this and record the result in the tracking manifest as scope.essentials_domains with source: user."}
