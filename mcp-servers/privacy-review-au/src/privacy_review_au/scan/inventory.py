"""Build a personal-information inventory from code: what is collected, where it is stored,
who receives it, and where in the world it goes.

privacy-review: ignore-file

This is the first thing a threshold or privacy impact assessment needs, and the thing a team
can check fastest. Everything here is a *candidate* drawn from field names, forms,
dependencies and configuration; the team confirms or corrects it.
"""

from __future__ import annotations

import re

from . import detectors as D
from .files import SourceFile

CATEGORIES: dict[str, tuple[str, str]] = {
    # id: (label, field-name terms)
    "identity": ("Identity", r"first_?name|last_?name|surname|full_?name|given_?names?|family_?name|preferred_?name|date_?of_?birth|dob|"
                             r"birth_?date|gender|sex|photo(?:_?url)?|signature"),
    "contact": ("Contact details", r"email(?:_?address)?|phone(?:_?number)?|mobile(?:_?number)?|street(?:_?address)?|home_?address|"
                                   r"postal_?address|residential_?address|address_?line_?\d?|postcode|post_?code|suburb"),
    "government_identifier": ("Government related identifiers", r"tfn|tax_?file_?(?:no|number)|medicare(?:_?(?:no|number|card))?|passport(?:_?(?:no|number))?|"
                                                                 r"driver_?s?_?licen[cs]e(?:_?(?:no|number))?|licen[cs]e_?(?:no|number)|centrelink(?:_?\w+)?|crn|ihi|"
                                                                 r"dva_?(?:no|number|file)|usi|visa_?(?:grant_?)?number"),
    "financial": ("Financial", r"card_?number|credit_?card(?:_?number)?|bsb|account_?number|bank_?account(?:_?\w+)?|iban|income|salary|wages?"),
    "sensitive": ("Sensitive information (s 6(1))", D.SENSITIVE_TERMS),
    "biometric": ("Biometric", r"face_?(?:embedding|encoding|template|vector)s?|faceprint|fingerprint_?(?:template|hash|data)|voice_?print|"
                               r"biometric_?\w*|selfie(?:_?\w+)?|liveness\w*"),
    "location": ("Location", r"lat(?:itude)?|lng|lon(?:gitude)?|geo_?location|geo_?point|coords|gps_?\w*|home_?location|current_?location"),
    "online_identifier": ("Online and device identifiers", r"ip_?address|ip_?addr|device_?id|idfa|gaid|advertising_?id|ad_?id|user_?agent|"
                                                           r"cookie_?id|push_?token|fcm_?token|apns_?token"),
    "children": ("Children or young people", r"child_?(?:name|dob|age|id|details|first_?name|last_?name)|children_?(?:names?|ages?|count|details)|number_?of_?children|is_?minor|under_?(?:16|18)|guardian\w*|parent_?(?:name|email|phone|consent)|"
                                             r"student_?(?:id|number)|year_?level|school_?name"),
}
_RX = {k: D.field_rx(terms) for k, (_, terms) in CATEGORIES.items()}
_CLASSIFY = {k: re.compile(rf"^(?:{terms})$", re.I) for k, (_, terms) in CATEGORIES.items()}

MODEL_PATH = re.compile(r"(?:^|/)(?:models?|schemas?|entities|entity|migrations?|db|database|types|dtos?|forms?|validators?|"
                        r"serializers?|prisma|graphql|supabase)(?:/|\.|_)", re.I)
MODEL_CONTENT = re.compile(r"models\.Model|Column\(|mapped_column|declarative_base|BaseModel\)|\bSchema\(|new\s+Schema\(|@Entity\b|"
                           r"pgTable\(|mysqlTable\(|sqliteTable\(|z\.object\(|yup\.object\(|CREATE\s+TABLE|ActiveRecord::|"
                           r"@Column\b|type\s+\w+\s*=\s*\{|interface\s+\w+\s*\{|class\s+\w+\(.*(?:Model|Schema|Base)\)", re.I)
FORM_CONTROL = re.compile(r"<(?:input|textarea|select)\b[^>]*?\bname\s*=\s*['\"{]?\s*['\"]?([\w.\[\]-]+)", re.I)
FORM_NAME_ONLY = re.compile(r"^(?:name|full_?name|your_?name)$", re.I)

STORES = {
    "PostgreSQL": r"\bpsycopg2?\b|['\"]pg['\"]\s*:|postgres(?:ql)?://|\bpostgresql\b|aws_db_instance|aws_rds_cluster",
    "MySQL/MariaDB": r"\bmysqlclient\b|['\"]mysql2?['\"]\s*:|mysql://|\bpymysql\b|mariadb",
    "MongoDB": r"\bmongoose\b|\bpymongo\b|mongodb(?:\+srv)?://|['\"]mongodb['\"]\s*:",
    "Redis": r"['\"](?:redis|ioredis)['\"]\s*:|^redis\b|redis://|aws_elasticache",
    "DynamoDB": r"dynamodb|aws_dynamodb_table|AWS::DynamoDB",
    "Amazon S3": r"aws_s3_bucket\b|AWS::S3::Bucket|@aws-sdk/client-s3|boto3\.client\(\s*['\"]s3",
    "Firebase / Firestore": r"firebase-admin|['\"]firebase['\"]\s*:|firestore",
    "Supabase": r"@supabase/|supabase-py|supabase\.co",
    "SQLite": r"\bsqlite3?\b|better-sqlite3",
    "Elasticsearch / OpenSearch": r"elasticsearch|opensearch",
    "Google BigQuery": r"bigquery",
    "Azure storage / Cosmos DB": r"azurerm_storage_account|azurerm_cosmosdb|@azure/storage-blob|@azure/cosmos",
}
_STORE_RX = {k: re.compile(v, re.I | re.M) for k, v in STORES.items()}
HOSTS = {"vercel.json": "Vercel", "netlify.toml": "Netlify", "fly.toml": "Fly.io", "render.yaml": "Render", "firebase.json": "Firebase Hosting",
         "wrangler.toml": "Cloudflare Workers", "app.yaml": "Google App Engine", "amplify.yml": "AWS Amplify", "railway.json": "Railway",
         "heroku.yml": "Heroku", "procfile": "Heroku (or another Procfile host)"}
AU_REGION = re.compile(r"\bsyd1\b|\bsyd\b|ap-southeast-[24]|australia-southeast[12]|australia(?:east|southeast|central)|\bmel\b", re.I)
_REGION = re.compile(r"(?:us|eu|sa|ca|me|af|il|mx|cn|ap)-[a-z]+-\d|(?:us|europe|asia|northamerica|southamerica)-[a-z]+\d|"
                     r"eastus2?|westus[23]?|centralus|northeurope|westeurope|uksouth|southeastasia|eastasia|japaneast|canadacentral")


def _is_model_file(f: SourceFile) -> bool:
    ext = D._ext(f)
    if f.is_test or f.is_doc or ext not in D.SCHEMA_EXT:
        return False
    if ext in {".sql", ".prisma", ".graphql", ".gql"}:
        return True
    return bool(MODEL_PATH.search(f.lower_rel) or MODEL_CONTENT.search(f.text[:200000]))


def classify(field: str) -> str | None:
    f = re.sub(r"[\[\].-]", "_", field.lower()).strip("_").split("_", 1)[-1] if "." in field or "[" in field else field.lower()
    for k, rx in _CLASSIFY.items():
        if rx.match(f):
            return k
    if FORM_NAME_ONLY.match(f):
        return "identity"
    return None


def build(files: list[SourceFile], findings: list[D.Finding]) -> dict:
    cats: dict[str, dict[str, set[str]]] = {}

    def note(cat: str, field: str, rel: str) -> None:
        c = cats.setdefault(cat, {"fields": set(), "files": set()})
        c["fields"].add(field)
        c["files"].add(rel)

    collection_points = []
    for f in files:
        if f.is_test:
            continue
        ext = D._ext(f)
        if ext in D.MARKUP_EXT:
            fields = []
            for m in FORM_CONTROL.finditer(f.text):
                name = m.group(1)
                cat = classify(name)
                if cat:
                    note(cat, name.lower(), f.rel)
                    fields.append(name.lower())
            if fields:
                collection_points.append({"file": f.rel, "fields": sorted(set(fields))})
        if _is_model_file(f):
            for cat, rx in _RX.items():
                for name, _ in D.field_names(rx, f.text):
                    note(cat, name, f.rel)

    by_det: dict[str, list[D.Finding]] = {}
    for fd in findings:
        by_det.setdefault(fd.detector, []).append(fd)
    for fd in by_det.get("biometric-processing", []):
        note("biometric", "biometric processing (code)", fd.file or "")
    for fd in by_det.get("location-collection", []):
        note("location", "device location (code)", fd.file or "")
        collection_points.append({"file": fd.file, "fields": ["device location"]})
    for fd in by_det.get("covert-capture", []):
        collection_points.append({"file": fd.file, "fields": ["camera / microphone / screen / keystrokes"]})

    recipients: list[dict] = []
    for fd in by_det.get("overseas-processor-sdk", []):
        p = fd.extra.get("processor")
        recipients.append({"name": p, "kind": "AI API" if fd.extra.get("llm") else "service provider (SDK)",
                           "overseas_likely": True, "files": fd.extra.get("files", [fd.file])[:5]})
    for det, vendors, kind in (("tracking-pixel", D.PIXEL_VENDORS, "advertising / conversion pixel"),
                               ("session-replay", D.REPLAY_VENDORS, "session replay")):
        seen: dict[str, set[str]] = {}
        for fd in by_det.get(det, []):
            ev = fd.evidence or ""
            name = next((v for v, rx in vendors.items() if re.search(rx, ev, re.I)), "unidentified vendor")
            seen.setdefault(name, set()).add(fd.file or "")
        recipients += [{"name": n, "kind": kind, "overseas_likely": True, "files": sorted(fs)[:5]} for n, fs in sorted(seen.items())]
    if by_det.get("hashed-identifier-sharing"):
        recipients.append({"name": "hashed-identifier matching (ad platform audience or conversions API)", "kind": "identifier matching",
                           "overseas_likely": True, "files": sorted({fd.file or "" for fd in by_det["hashed-identifier-sharing"]})[:5]})

    for f in files:
        name = f.path.name.lower()
        host = HOSTS.get(name)
        if host and f.rel.count("/") <= 2 and not f.is_test:
            au = bool(AU_REGION.search(f.text))
            recipients.append({"name": host, "kind": "hosting provider", "overseas_likely": not au, "files": [f.rel],
                               **({"note": "Australian region configured"} if au else
                                  {"note": "no Australian region configured; the provider's default region is usually overseas"})})

    regions = sorted({m.group(0) for fd in by_det.get("non-au-region", []) for m in _REGION.finditer(fd.evidence or "")})

    stores = []
    for name, rx in _STORE_RX.items():
        rels = [f.rel for f in files if not f.is_test and not f.is_doc and rx.search(f.text)]
        if rels:
            stores.append({"store": name, "files": rels[:5]})

    retention = [f.rel for f in files if not f.is_doc and D.RETENTION.search(f.text)][:10]
    pi = {k: {"label": CATEGORIES[k][0], "fields": sorted(v["fields"])[:25], "files": sorted(v["files"])[:10]}
          for k, v in sorted(cats.items(), key=lambda kv: list(CATEGORIES).index(kv[0]))}
    handles = bool(pi or collection_points or any(r["kind"] not in ("service provider (SDK)", "hosting provider") for r in recipients))
    return {
        "handles_personal_information": handles,
        "personal_information": pi,
        "collection_points": collection_points[:30],
        "stores": stores,
        "recipients": recipients,
        "overseas": {"non_australian_regions": regions,
                     "likely_overseas_recipients": sorted({r["name"] for r in recipients if r["overseas_likely"]})},
        "retention_mechanisms": retention,
        "note": "Candidates drawn from field names, forms, dependencies and configuration. Confirm each item, add what the code "
                "cannot show (paper forms, call centres, data received from other organisations), and correct anything wrong.",
    }
