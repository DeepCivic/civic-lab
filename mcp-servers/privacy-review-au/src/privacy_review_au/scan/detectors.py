"""Static detectors. Each maps code or configuration signals to KB rule or heuristic ids.

privacy-review: ignore-file  (this module is made of the patterns it looks for)

A detector never decides that the law has been contravened. It reports a signal,
with file/line evidence, against the rules or heuristics it bears on. The
server attaches the legal requirement, exceptions and citations.

A finding is linked to a *rule* only when the condition the rule turns on is visible
in the evidence (for example, R-APP3.3 for a tracking pixel only once a sensitive
context is established, R-TFN only when a tax file number is actually seen). Otherwise
it is linked to heuristics only, so the `rule` tier keeps its meaning: an obvious
contravention if the facts are as they appear.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from .files import SourceFile

SEVERITIES = ["info", "low", "medium", "high", "critical"]
LINE_IGNORE = "privacy-review: ignore"

CODE_EXT = {".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".vue", ".svelte", ".astro", ".php", ".rb", ".go",
            ".java", ".kt", ".swift", ".m", ".cs", ".rs", ".scala", ".sh", ".ipynb"}
MARKUP_EXT = {".html", ".htm", ".jsx", ".tsx", ".vue", ".svelte", ".astro", ".php", ".erb", ".ejs", ".hbs",
              ".handlebars", ".liquid", ".njk", ".jinja", ".j2", ".twig", ".mustache"}
# ".json" here means configuration/IaC/schema JSON. Plain data JSON is classed ".jsondata" by _ext().
IAC_EXT = {".tf", ".tfvars", ".hcl", ".yaml", ".yml", ".json", ".toml", ".env", ".ini", ".conf", ".properties"}
SCHEMA_EXT = {".sql", ".prisma", ".py", ".ts", ".js", ".rb", ".go", ".java", ".kt", ".cs", ".graphql", ".gql", ".json",
              ".yaml", ".yml"} | MARKUP_EXT


@dataclass
class Finding:
    detector: str
    entries: list[str]
    severity: str
    confidence: str
    message: str
    file: str | None = None
    line: int | None = None
    evidence: str | None = None
    extra: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v not in (None, {}, [])}


_SECRETISH = re.compile(r"(AKIA[0-9A-Z]{12})[0-9A-Z]{4}|((?:sk|pk|rk)_live_)[0-9A-Za-z]{8,}|(ghp_)[A-Za-z0-9]{8,}|"
                        r"(xox[baprs]-)[A-Za-z0-9-]{8,}|(AIza)[0-9A-Za-z_\-]{20,}|(://[^:/\s]+:)[^@\s]+(@)")


def redact(line: str, limit: int = 220) -> str:
    def sub(m: re.Match) -> str:
        g = [x for x in m.groups() if x]
        return (g[0] + "****" + (g[1] if len(g) > 1 else "")) if g else "****"

    s = _SECRETISH.sub(sub, line.strip())
    s = re.sub(r"\b\d{9,19}\b", lambda m: m.group(0)[:3] + "…" + m.group(0)[-2:], s)
    s = re.sub(r"\b(\d{4})([ -])\d{4}\2\d{4}\2(\d{1,7})\b", r"\1\2****\2****\2\3", s)
    return s[:limit] + ("…" if len(s) > limit else "")


def _line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def _line_text(f: SourceFile, ln: int) -> str:
    lines = f.text.splitlines()
    return lines[ln - 1] if 0 < ln <= len(lines) else ""


def _suppressed(f: SourceFile, ln: int | None) -> bool:
    return bool(ln) and LINE_IGNORE in _line_text(f, ln)


_JSON_IAC = re.compile(r'"(?:AWSTemplateFormatVersion|Resources|Statement|Effect|resource|provider|terraform|'
                       r'PolicyDocument|bindings|iamPolicy|properties\.(?:publicAccess|allowBlobPublicAccess))"\s*:')
_JSON_SCHEMA = re.compile(r'"(?:\$schema|openapi|swagger|definitions|\$defs)"\s*:|"properties"\s*:\s*\{\s*"[\w-]+"\s*:\s*\{\s*"type"')
_CONFIG_JSON = re.compile(r"(?:^|/)(?:package|composer|app|manifest|tsconfig|jsconfig|vercel|firebase|now|serverless|"
                          r"host|appsettings[\w.-]*|\.?eslintrc|cdk|amplify[\w-]*|[\w.-]*policy[\w.-]*|[\w.-]*\.template)\.json$", re.I)


def _ext(f: SourceFile) -> str:
    n = f.path.name.lower()
    if n == "dockerfile":
        return ".dockerfile"
    suf = f.path.suffix.lower()
    if suf == ".json":
        head = f.text[:20000]
        if _CONFIG_JSON.search(f.lower_rel) or _JSON_IAC.search(head) or _JSON_SCHEMA.search(head):
            return ".json"
        return ".jsondata"
    return suf or ("." + n if n.startswith(".env") else "")


# --------------------------------------------------------------------------- pattern detectors

@dataclass
class PatternDetector:
    id: str
    entries: list[str]
    severity: str
    confidence: str
    message: str
    patterns: list[str]
    exts: set[str] | None = None
    skip_tests: bool = True
    only_fixtures: bool = False
    skip_docs: bool = True
    max_per_file: int = 3
    flags: int = re.I
    # (regex over the matched text, extra KB entries): rules attached only when their condition is visible
    conditional: list[tuple[str, list[str]]] = field(default_factory=list)
    # severity used when the match is in a test file (None: same as severity)
    test_severity: str | None = None
    # for prose files (.md, .txt ...): only scan paths matching this, e.g. notices and policies
    prose_path: str | None = None

    def __post_init__(self) -> None:
        self._re = [re.compile(p, self.flags) for p in self.patterns]
        self._cond = [(re.compile(rx, re.I), ents) for rx, ents in self.conditional]

    def run(self, f: SourceFile) -> list[Finding]:
        if self.exts is not None and _ext(f) not in self.exts:
            return []
        if self.skip_tests and f.is_test:
            return []
        if self.only_fixtures and not (f.is_fixture or f.is_test):
            return []
        if self.skip_docs and f.is_prose and not (self.exts and _ext(f) in self.exts):
            return []
        if self.prose_path and f.is_prose and not re.search(self.prose_path, f.path.name.lower()):
            return []
        out: list[Finding] = []
        seen_lines: set[int] = set()
        for rx in self._re:
            for m in rx.finditer(f.text):
                ln = _line_of(f.text, m.start())
                if ln in seen_lines or _suppressed(f, ln):
                    continue
                seen_lines.add(ln)
                entries = list(self.entries)
                for crx, extra in self._cond:
                    if crx.search(m.group(0)):
                        entries += [e for e in extra if e not in entries]
                sev = self.test_severity if (self.test_severity and f.is_test) else self.severity
                msg = self.message + (" In a test file: confirm it is a dummy value." if self.test_severity and f.is_test else "")
                out.append(Finding(self.id, entries, sev, self.confidence, msg, f.rel, ln, redact(_line_text(f, ln))))
                if len(out) >= self.max_per_file:
                    return out
        return out


WEB_EXT = CODE_EXT | MARKUP_EXT | IAC_EXT | {".mjml", ".xml"}
NOTICE_PATH = r"privacy|notice|collection|terms|consent|policy|signage|legal"

LOCAL_HOST = r"(?!localhost|127\.|0\.0\.0\.0|\[::1\]|[\w.-]*\.(?:local|test|example|internal|localhost|invalid)\b|" \
             r"(?:www\.)?w3\.org|schemas\.|[\w.-]*xmlsoap|json-schema\.org|example\.(?:com|org|net)|purl\.org|" \
             r"ns\.adobe|apache\.org/licenses|www\.apache|opensource\.org|creativecommons)"

PIXEL_VENDORS = {
    "Meta Pixel": r"fbq\(|connect\.facebook\.net|facebook-pixel|meta-pixel", "TikTok Pixel": r"tiktok\.com|ttq\.",
    "LinkedIn Insight": r"licdn\.com|_linkedin_partner_id", "Snap Pixel": r"sc-static\.net|snaptr\(", "Pinterest Tag": r"pinimg\.com|pintrk\(",
    "Reddit Pixel": r"redditstatic|rdt\(", "X (Twitter) Pixel": r"ads-twitter|twq\(", "Google Ads": r"googleadservices|AW-|doubleclick",
    "Google Tag Manager": r"googletagmanager", "Microsoft Ads (UET)": r"bat\.bing|uetq",
}
REPLAY_VENDORS = {"FullStory": r"fullstory|FS\.identify", "Hotjar": r"hotjar|hj\(", "LogRocket": r"logrocket",
                  "Microsoft Clarity": r"clarity", "PostHog/Amplitude session recording": r"session_recording|startSessionRecording",
                  "Smartlook": r"smartlook", "Mouseflow": r"mouseflow", "Inspectlet": r"inspectlet"}

PATTERNS: list[PatternDetector] = [
    PatternDetector(
        "tracking-pixel", ["H-TRACKING-PIXEL-SENSITIVE"], "medium", "high",
        "Third-party advertising or conversion pixel. Sends page and visitor data to an overseas ad platform.",
        [r"fbq\(\s*['\"](?:init|track|trackCustom)", r"connect\.facebook\.net/[^\"'\s]*fbevents\.js",
         r"react-facebook-pixel|@?meta-pixel|facebook-pixel", r"analytics\.tiktok\.com|ttq\.(?:load|track|page)\(",
         r"snap\.licdn\.com|_linkedin_partner_id", r"sc-static\.net/scevent|snaptr\(", r"s\.pinimg\.com/ct/|pintrk\(",
         r"redditstatic\.com/ads|rdt\(\s*['\"]init", r"static\.ads-twitter\.com/uwt\.js|twq\(",
         r"googleadservices\.com/pagead|gtag\(\s*['\"]config['\"]\s*,\s*['\"]AW-", r"fls\.doubleclick\.net|googletagmanager\.com/gtm\.js",
         r"bat\.bing\.com/bat\.js|window\.uetq"], exts=WEB_EXT),
    PatternDetector(
        "session-replay", ["H-SURVEILLANCE-TORT", "H-VENDOR-DEFAULT-DRIFT"], "medium", "high",
        "Session replay or recording tool. Records user interactions and possibly form input.",
        [r"fullstory|edge\.fullstory\.com|FS\.identify", r"static\.hotjar\.com|hotjar|hj\(\s*['\"]identify",
         r"logrocket|LogRocket\.init", r"clarity\.ms/tag|microsoft-clarity|@microsoft/clarity",
         r"session_recording|disable_session_recording\s*:\s*false|startSessionRecording", r"smartlook|mouseflow|inspectlet"],
        exts=WEB_EXT),
    PatternDetector(
        "biometric-processing", ["H-FRT-PROPORTIONALITY", "H-NO-PIA-HIGH-RISK"], "high", "high",
        "Facial recognition or biometric template processing (sensitive information when used for identification or verification).",
        [r"\bimport\s+face_recognition|from\s+face_recognition|face_recognition\.(?:face_encodings|compare_faces)",
         r"dlib\.(?:get_frontal_face_detector|face_recognition_model)", r"\binsightface\b|\bdeepface\b|DeepFace\.",
         r"face[-_]api(?:\.js)?['\"]|@vladmandic/(?:human|face-api)", r"index_faces|search_faces(?:_by_image)?|IndexFaces|SearchFacesByImage|compare_faces|CompareFaces",
         r"FaceClient|/face/v1\.0/(?:identify|verify|detect)|face\.(?:identify|verify)\(",
         r"\b(?:face|facial)_?(?:embedding|encoding|template|vector|print)s?\b|faceprint",
         r"\b(?:voice|speaker)_?(?:print|embedding|verification)\b|fingerprint_template|biometric_template"],
        exts=CODE_EXT | SCHEMA_EXT | IAC_EXT),
    PatternDetector(
        "hardcoded-secret", ["R-APP11-CREDENTIALS"], "critical", "high",
        "Credential committed to the repository.",
        [r"AKIA[0-9A-Z]{16}", r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----", r"\bsk_live_[0-9A-Za-z]{16,}",
         r"\bghp_[A-Za-z0-9]{36}\b", r"\bxox[baprs]-[A-Za-z0-9-]{10,}", r"\bAIza[0-9A-Za-z_\-]{35}\b",
         r"(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis|amqp)://[^:/\s'\"]+:(?!\$\{|<|\*|password@|pass@|changeme|secret@)[^@\s'\"]{4,}@" + LOCAL_HOST],
        skip_tests=False, skip_docs=False, flags=0, test_severity="low"),
    PatternDetector(
        "weak-password-hashing", ["R-APP11-CREDENTIALS"], "high", "high",
        "Password hashed with a fast general-purpose hash (not a password KDF).",
        [r"(?:md5|sha1|sha256|sha512)\s*\(\s*[^)\n]*pass(?:word|wd)?", r"hashlib\.(?:md5|sha1|sha256|sha512)\([^)\n]*pass",
         r"createHash\(\s*['\"](?:md5|sha1|sha256)['\"]\s*\)[^\n]{0,80}pass", r"MessageDigest\.getInstance\(\s*\"(?:MD5|SHA-?1|SHA-?256)\"\)[^\n]{0,120}pass",
         r"password_?hash\s*=\s*(?:md5|sha1)"], exts=CODE_EXT),
    PatternDetector(
        "tls-verification-disabled", ["R-APP11-TRANSPORT"], "high", "high",
        "TLS certificate verification disabled.",
        [r"verify\s*=\s*False", r"rejectUnauthorized\s*:\s*false", r"InsecureSkipVerify\s*:\s*true",
         r"NODE_TLS_REJECT_UNAUTHORIZED['\"]?\s*[:=]\s*['\"]?0", r"CURLOPT_SSL_VERIFY(?:PEER|HOST)\s*,\s*(?:0|false)",
         r"ssl\._create_unverified_context|CERT_NONE", r"TrustAllCerts|ALLOW_ALL_HOSTNAME_VERIFIER|trustAllCertificates"],
        exts=CODE_EXT | IAC_EXT | {".dockerfile"}),
    PatternDetector(
        "plaintext-http-endpoint", ["R-APP11-TRANSPORT"], "medium", "medium",
        "Non-local plain-HTTP endpoint used by code or a form.",
        [r"<form[^>]+action\s*=\s*['\"]http://" + LOCAL_HOST,
         r"(?:url|endpoint|base_?url|api_?url|host|webhook|fetch|axios\.\w+|requests\.\w+|http\.\w+)\s*[(:=]\s*\(?\s*['\"`]http://" + LOCAL_HOST],
        exts=CODE_EXT | MARKUP_EXT | IAC_EXT),
    PatternDetector(
        "iac-public-storage", ["R-APP11-PUBLIC-STORAGE"], "critical", "medium",
        "Infrastructure configuration makes storage or a database publicly accessible.",
        [r"acl\s*=\s*['\"]public-read(?:-write)?['\"]", r"(?:block_public_acls|block_public_policy|ignore_public_acls|restrict_public_buckets)\s*=\s*false",
         r"(?:BlockPublicAcls|BlockPublicPolicy|IgnorePublicAcls|RestrictPublicBuckets)['\"]?\s*:\s*false", r"AccessControl['\"]?\s*:\s*['\"]?PublicRead",
         r"['\"](?:allUsers|allAuthenticatedUsers)['\"]", r"publicly_accessible\s*=\s*true|PubliclyAccessible['\"]?\s*:\s*true",
         r"container_access_type\s*=\s*['\"](?:blob|container)['\"]", r"allow_(?:nested_items_to_be_public|blob_public_access)\s*=\s*true"],
        exts=IAC_EXT),
    PatternDetector(
        "iam-wildcard", ["H-MFA-AND-PRIVILEGED-ACCESS"], "medium", "medium",
        "IAM policy grants wildcard actions (least privilege not applied).",
        [r"['\"]Action['\"]\s*:\s*['\"]\*['\"]", r"actions\s*=\s*\[\s*['\"]\*['\"]\s*\]", r"Action:\s*['\"]?\*['\"]?\s*$"],
        exts=IAC_EXT, flags=re.M),
    PatternDetector(
        "mfa-disabled", ["H-MFA-AND-PRIVILEGED-ACCESS"], "high", "medium",
        "Multi-factor authentication explicitly disabled.",
        [r"mfa_configuration\s*=\s*['\"]OFF['\"]", r"MfaConfiguration['\"]?\s*:\s*['\"]?OFF", r"['\"]?(?:require_?mfa|mfa_?required|mfa_?enabled|MFA_ENABLED)['\"]?\s*[:=]\s*(?:false|False|0)\b"],
        exts=IAC_EXT | CODE_EXT),
    PatternDetector(
        "non-au-region", ["H-OVERSEAS-PROCESSING"], "medium", "high",
        "Infrastructure region outside Australia.",
        [r"\b(?:region|aws_region|AWS_REGION|AWS_DEFAULT_REGION|default_region)['\"]?\s*[:=]\s*['\"]?(?:us|eu|sa|ca|me|af|il|mx|cn)-[a-z]+-\d\b",
         r"\b(?:region|aws_region|AWS_REGION|AWS_DEFAULT_REGION)['\"]?\s*[:=]\s*['\"]?ap-(?!southeast-2\b|southeast-4\b)[a-z]+-\d\b",
         r"\b(?:region|location|zone)['\"]?\s*[:=]\s*['\"](?:us|europe|asia|northamerica|southamerica|me|africa)-[a-z]+\d(?:-[a-z])?['\"]",
         r"\blocation\s*[:=]\s*['\"](?:eastus2?|westus[23]?|centralus|northeurope|westeurope|uksouth|southeastasia|eastasia|japaneast|canadacentral)['\"]"],
        exts=IAC_EXT | {".py", ".ts", ".js"}),
    PatternDetector(
        "pii-in-logs", ["H-IDENTIFIERS-ARE-PERSONAL"], "medium", "medium",
        "Personal information or credentials written to logs.",
        [r"(?:log(?:ger|ging)?|console|print|puts|fmt\.Print\w*|Log\.\w)\s*[.(][^\n]{0,120}\b(?:password|passwd|tfn|tax_?file|medicare|passport|date_?of_?birth|dob|credit_?card|card_?number|cvv)\b",
         r"(?:log(?:ger|ging)?|console)\.(?:info|debug|log|warn|error)\([^\n]{0,80}\b(?:user\.email|email|phone|mobile|address)\b"],
        exts=CODE_EXT,
        conditional=[(r"\bpass(?:word|wd)\b|\bcvv\b", ["R-APP11-CREDENTIALS"]), (r"\btfn\b|tax_?file", ["R-TFN-MISHANDLING"])]),
    PatternDetector(
        "hashed-identifier-sharing", ["H-IDENTIFIERS-ARE-PERSONAL", "H-TRACKING-PIXEL-SENSITIVE"], "medium", "medium",
        "Hashed email or phone prepared for matching (pseudonymous, still personal information).",
        [r"(?:sha256|md5|sha1|createHash\([^)]*\))[^\n]{0,60}\b(?:email|phone)\b[^\n]{0,80}", r"['\"](?:em|ph|external_id)['\"]\s*:\s*[^\n]{0,40}(?:hash|sha)",
         r"graph\.facebook\.com/v[\d.]+/\d*/?events|conversions?_api|\bcapi\b", r"hashed_?(?:email|phone)|email_?sha256"],
        exts=CODE_EXT | MARKUP_EXT),
    PatternDetector(
        "location-collection", ["H-LOCATION-TRANSPARENCY"], "medium", "high",
        "Device location collected.",
        [r"navigator\.geolocation|getCurrentPosition|watchPosition", r"CLLocationManager|requestAlwaysAuthorization|startMonitoringSignificantLocationChanges",
         r"ACCESS_BACKGROUND_LOCATION|ACCESS_FINE_LOCATION", r"FusedLocationProviderClient|LocationServices\.getFused",
         r"expo-location|react-native-geolocation|@capacitor/geolocation"], exts=CODE_EXT | MARKUP_EXT | {".xml", ".plist", ".json"}),
    PatternDetector(
        "sdk-autocollect-defaults", ["H-VENDOR-DEFAULT-DRIFT"], "low", "medium",
        "SDK automatic data collection explicitly enabled.",
        [r"(?:FacebookAutoLogAppEventsEnabled|AutoLogAppEventsEnabled|FacebookAdvertiserIDCollectionEnabled|AdvertiserIDCollectionEnabled)[^\n]*(?:true|<true\s*/>)",
         r"<key>FacebookAutoLogAppEventsEnabled</key>\s*<true\s*/>", r"\bautocapture\s*:\s*true", r"firebase_analytics_collection_enabled[^\n]*true",
         r"setAnalyticsCollectionEnabled\(\s*true", r"google_analytics_adid_collection_enabled[^\n]*true"], exts=WEB_EXT | {".xml", ".plist"}),
    PatternDetector(
        "covert-capture", ["H-SURVEILLANCE-TORT"], "low", "low",
        "Camera, microphone, screen or keystroke capture. Check that it is disclosed and visible to the user.",
        [r"getUserMedia\(|getDisplayMedia\(|new\s+MediaRecorder\(", r"pynput\.keyboard|keylogger|ImageGrab\.grab\(",
         r"addEventListener\(\s*['\"]key(?:down|up|press)['\"][^\n]{0,160}(?:fetch|sendBeacon|XMLHttpRequest|axios)"],
        exts=CODE_EXT | MARKUP_EXT),
    PatternDetector(
        "government-identifier-as-key", ["R-APP9-GOVERNMENT-IDENTIFIER"], "high", "medium",
        "Government related identifier used as a key or unique identifier.",
        [r"\b(?:medicare|passport|driver_?s?_?licen[cs]e|licen[cs]e_?(?:no|number)|centrelink|crn|tfn|tax_?file_?(?:no|number)|ihi|dva_?(?:no|number))\w*\b[^\n]{0,80}(?:PRIMARY\s+KEY|primary_key\s*=\s*True|@id\b|@unique|unique\s*[:=]\s*(?:true|True)|\bUNIQUE\b|\bunique=True|index:\s*\{\s*unique)",
         r"PRIMARY\s+KEY\s*\(\s*['\"`]?(?:medicare|passport|tfn|tax_?file|licen[cs]e|crn)\w*"],
        exts=SCHEMA_EXT - {".json"}, skip_tests=True,
        conditional=[(r"\btfn|tax_?file", ["R-TFN-MISHANDLING"])]),
    PatternDetector(
        "tfn-handling", ["R-TFN-MISHANDLING"], "medium", "medium",
        "Tax file numbers handled. Confirm a taxation/superannuation purpose, encryption, and exclusion from logs and analytics.",
        [r"\b(?:tfn|tax_?file_?(?:no|number)|taxFileNumber)\b"], exts=(SCHEMA_EXT | CODE_EXT) - {".json"}, max_per_file=1),
    PatternDetector(
        "hedged-notice-language", ["R-APP5-NO-COLLECTION-NOTICE", "H-FRT-PROPORTIONALITY"], "medium", "high",
        "Notice says biometric or facial recognition collection 'may' occur. The ART held similar wording did not positively convey collection.",
        [r"may\s+(?:include|use|involve|employ)\s+(?:facial\s+recognition|biometric|face)", r"(?:facial\s+recognition|biometric)[^\n.]{0,60}may\s+be\s+(?:used|in\s+(?:use|operation))"],
        exts=MARKUP_EXT | {".md", ".mdx", ".txt", ".liquid", ".mjml"}, skip_docs=False, skip_tests=True, prose_path=NOTICE_PATH),
    PatternDetector(
        "consent-dark-patterns", ["H-CONSENT-DESIGN"], "medium", "medium",
        "Consent pre-selected, bundled, or declined through pressure wording.",
        [r"<input[^>]*type\s*=\s*['\"]checkbox['\"][^>]*\b(?:checked|defaultChecked)\b[^>]*(?:consent|marketing|newsletter|subscribe|opt.?in|partner|share)",
         r"<input[^>]*(?:consent|marketing|newsletter|subscribe|opt.?in|partner|share)[^>]*\b(?:checked|defaultChecked(?:=\{true\})?)\b",
         r"(?:consent|marketing|optIn|opt_in|newsletter|subscribe)\w*\s*[:=]\s*(?:useState\()?\s*true\b",
         r"No\s+thanks,?\s+I\s+(?:don'?t|do\s+not)\s+(?:want|like|care|need)",
         r"I\s+agree\s+to\s+the\s+Terms[^\n<]{0,40}Privacy\s+Policy[^\n<]{0,40}(?:marketing|promotional|offers|partners)"],
        exts=MARKUP_EXT | CODE_EXT),
    PatternDetector(
        "suppressed-security-findings", ["H-KNOWN-SECURITY-DEBT"], "low", "medium",
        "Security finding suppressed or security work deferred in a comment.",
        [r"#\s*nosec\b|//\s*nosemgrep|#\s*nosemgrep|eslint-disable[^\n]*security|#\s*noqa:\s*S\d+|@SuppressWarnings\(\"(?:java:S|squid)",
         r"(?:TODO|FIXME|HACK|XXX)\b[^\n]{0,80}\b(?:auth\w*|encrypt\w*|password|secur\w*|mfa|2fa|pii|personal\s+info|privacy|tls|ssl|sanitis\w*|sanitiz\w*|permission)"],
        exts=CODE_EXT | {".tf", ".hcl"}, max_per_file=5),
]

# --------------------------------------------------------------------------- field-based detectors

# A term only counts as a *field* in a field-like position: an object key or assignment, a SQL/Prisma
# column with a type, or a form control name. "race condition" or "diagnostics" in prose does not.
_COL_TYPES = r"(?:text|varchar|n?char|citext|string|int\w*|bigint|smallint|bool\w*|jsonb?|date\w*|timestamp\w*|enum|uuid|numeric|decimal|bytea|blob)"


def field_rx(terms: str) -> re.Pattern:
    return re.compile(
        rf"(?:\b(?P<a>{terms})\b['\"`]?\s*(?:[:=]|\?\s*:|\s+{_COL_TYPES}\b)"
        rf"|(?:name|id|v-model|formControlName|bind:value)\s*=\s*['\"{{][^'\"}}\n]{{0,40}}?\b(?P<b>{terms})\b)", re.I)


def field_names(rx: re.Pattern, text: str) -> list[tuple[str, int]]:
    return [((m.group("a") or m.group("b")).lower(), m.start()) for m in rx.finditer(text)]


SENSITIVE_TERMS = (r"diagnos(?:is|es|ed\w*)|medical_?(?:condition|history|record)s?|health_?(?:condition|status|info\w*|record)s?|"
                   r"medications?|prescriptions?|disabilit(?:y|ies)(?:_?\w+)?|mental_?health\w*|pregnan\w*|hiv_?status|ethnicity|ethnic_?origin|"
                   r"indigenous_?status|atsi_?status|racial_?\w*|race_?(?:ethnicity|group|origin)|religion|religious_?\w*|sexual_?orientation|sexuality|gender_?identity|"
                   r"criminal_?(?:record|history)|convictions?|union_?member\w*|political_?(?:party|opinion|affiliation)\w*|blood_?type|"
                   r"genetic_?\w*|biometric_?\w*")
SENSITIVE_FIELD = field_rx(SENSITIVE_TERMS)
EXCESSIVE_FIELD = re.compile(
    r"\b(?:gender|sex|date_?of_?birth|dob|birth_?date|birthday|marital_?status|dependants?|dependents?|number_?of_?children|"
    r"citizenship|nationality|visa_?(?:status|expiry|type|class)|previous_?address\w*|bankrupt\w*|student_?status|retire\w*|"
    r"employer_?reference|income_?proof|religion)\b", re.I)
CONSENT_MARK = re.compile(r"\bconsent\w*|opt_?in|agreed_?at|accepted_?terms|permission_?granted", re.I)
FORM_NAME_FILE = re.compile(r"contact|feedback|survey|complain|enquir|inquir|support", re.I)
REQUIRED_ID = re.compile(r"(?:\bname\b|first_?name|last_?name|surname|full_?name|dob|date_?of_?birth)[^\n]{0,100}\brequired\b|"
                         r"\brequired\b[^\n]{0,60}(?:\bname\b|first_?name|last_?name|surname|dob|date_?of_?birth)", re.I)
MARKETING_FILE = re.compile(r"marketing|newsletter|promo|campaign|digest|announce|offer|edm", re.I)
UNSUB = re.compile(r"unsubscribe|opt[- ]?out|manage\s+(?:your\s+)?(?:email\s+)?preferences|List-Unsubscribe|%unsubscribe%|\{\{\s*unsub", re.I)
TEMPLATE_EXT = {".html", ".htm", ".hbs", ".handlebars", ".mjml", ".liquid", ".njk", ".ejs", ".jinja", ".j2", ".erb", ".mustache",
                ".txt", ".md", ".jsx", ".tsx"}
FORM_PI = re.compile(r"<(?:input|textarea|select)\b[^>]*\bname\s*=\s*['\"{]?\s*['\"]?(?:email|phone|mobile|name|first_?name|last_?name|"
                     r"full_?name|surname|address|street|postcode|dob|birth|date_?of_?birth|medicare|tfn|passport|licen[cs]e)", re.I)
NOTICE = re.compile(r"privacy|collection\s+(?:notice|statement)|personal\s+information", re.I)
AUTO_DECISION = re.compile(
    r"\b(?:auto_?approv\w*|auto_?declin\w*|auto_?reject\w*|decline_?reason|eligibility_?(?:check|score|decision)|credit_?score|risk_?score|"
    r"fraud_?score|underwrit\w*|decision_?engine|scoring_?model|rules?_?engine|approve_?if|is_?eligible)\b", re.I)
SCRAPER = re.compile(r"\bscrapy\b|BeautifulSoup|playwright|selenium|puppeteer|cheerio|requests_html|crawlee", re.I)
SCRAPE_TARGET = re.compile(r"linkedin\.com|facebook\.com|instagram\.com|twitter\.com|x\.com/|tiktok\.com|whitepages|"
                           r"people[-_ ]?search|profile_?(?:url|page|image|photo)|avatar|(?:email|phone)_?(?:address|number)", re.I)
PROCESSORS = {
    "Sentry": r"sentry_sdk|@sentry/|sentry-sdk|io\.sentry", "Datadog": r"\bddtrace\b|dd-trace|@datadog/", "Segment": r"@segment/|analytics-node|segment\.io|analytics-python",
    "Mixpanel": r"\bmixpanel\b", "Amplitude": r"@amplitude/|amplitude-js", "Intercom": r"\bintercom\b", "HubSpot": r"\bhubspot\b|hs-scripts",
    "Google Analytics": r"google-analytics\.com|gtag\(|googletagmanager|firebase/analytics|@react-native-firebase/analytics",
    "OpenAI": r"\bopenai\b", "Anthropic": r"\banthropic\b|@anthropic-ai/", "Google Gemini": r"google\.generativeai|@google/generative-ai|google-genai|vertexai",
    "Cohere": r"\bcohere\b", "Mistral": r"\bmistralai\b", "Twilio": r"\btwilio\b", "SendGrid": r"sendgrid", "Mailchimp": r"mailchimp",
    "Zendesk": r"zendesk", "Salesforce": r"salesforce|jsforce", "Algolia": r"algoliasearch|\balgolia\b", "Auth0": r"\bauth0\b", "Stripe": r"\bstripe\b",
}
LLM_PROCESSORS = {"OpenAI", "Anthropic", "Google Gemini", "Cohere", "Mistral"}
DEP_FILES = {"package.json", "requirements.txt", "pyproject.toml", "pipfile", "go.mod", "gemfile", "pom.xml", "build.gradle",
             "podfile", "pubspec.yaml", "composer.json", "cargo.toml"}


def _luhn(num: str) -> bool:
    s, alt = 0, False
    for d in reversed(num):
        n = int(d)
        if alt:
            n = n * 2 - 9 if n > 4 else n * 2
        s += n
        alt = not alt
    return s % 10 == 0


def _tfn_ok(num: str) -> bool:
    w = [1, 4, 3, 7, 5, 8, 6, 9, 10]
    return len(num) == 9 and sum(int(d) * w[i] for i, d in enumerate(num)) % 11 == 0


def _medicare_ok(num: str) -> bool:
    if len(num) not in (10, 11) or num[0] not in "23456":
        return False
    w = [1, 3, 7, 9, 1, 3, 7, 9]
    return sum(int(num[i]) * w[i] for i in range(8)) % 10 == int(num[8])


TEST_CARDS = {"4111111111111111", "4242424242424242", "5555555555554444", "378282246310005", "4000056655665556",
              "5105105105105100", "4012888888881881", "6011111111111117", "3530111333300000", "371449635398431"}
PII_EMAIL = re.compile(r"\b[\w.+-]+@(?:gmail|outlook|hotmail|yahoo|bigpond|optusnet|icloud|live|me|protonmail|aol|tpg|iinet)\.[a-z.]+\b", re.I)
AU_MOBILE = re.compile(r"(?<![\w-])(?:\+?61\s?4|04)\d{2}[\s-]?\d{3}[\s-]?\d{3}(?![\w-])")
# Card numbers: contiguous, or grouped with one consistent separator (4-4-4-x, or Amex 4-6-5). Bounded by
# non-word, non-hyphen characters so digit runs inside UUIDs, hashes and ids are not read as cards.
CARD = re.compile(r"(?<![\w-])(?:\d{13,19}|\d{4}([ -])\d{4}\1\d{4}\1\d{1,7}|\d{4}([ -])\d{6}\2\d{5})(?![\w-])")
NINE = re.compile(r"(?<![\w-])\d{3}([ -]?)\d{3}\1\d{3}(?![\w-])")
TEN = re.compile(r"(?<![\w-])\d{4}([ -]?)\d{5}\1\d{1,2}(?![\w-])")


def fixture_pii(f: SourceFile) -> list[Finding]:
    if not (f.is_fixture or f.is_test or _ext(f) in {".csv", ".sql", ".ipynb", ".jsonl"}):
        return []
    hits: list[tuple[str, int, str]] = []
    t = f.text
    for m in PII_EMAIL.finditer(t):
        hits.append(("personal email address", m.start(), m.group(0)))
    for m in AU_MOBILE.finditer(t):
        digits = re.sub(r"\D", "", m.group(0))
        if not re.fullmatch(r"(?:61)?0?4\d{2}(?:000000|123456|111111)\d{0,2}", digits):
            hits.append(("Australian mobile number", m.start(), m.group(0)))
    for m in CARD.finditer(t):
        d = re.sub(r"\D", "", m.group(0))
        if 13 <= len(d) <= 19 and d[0] in "3456" and _luhn(d) and d not in TEST_CARDS and len(set(d)) > 3:
            hits.append(("payment card number (Luhn-valid)", m.start(), m.group(0)))
    for m in NINE.finditer(t):
        d = re.sub(r"\D", "", m.group(0))
        if _tfn_ok(d) and re.search(r"tfn|tax", t[max(0, m.start() - 80):m.start()], re.I):
            hits.append(("tax file number (checksum-valid)", m.start(), m.group(0)))
    for m in TEN.finditer(t):
        d = re.sub(r"\D", "", m.group(0))
        if _medicare_ok(d) and re.search(r"medicare", t[max(0, m.start() - 80):m.start()], re.I):
            hits.append(("Medicare number (checksum-valid)", m.start(), m.group(0)))
    hits = [h for h in hits if not _suppressed(f, _line_of(t, h[1]))]
    if not hits:
        return []
    kinds = sorted({h[0] for h in hits})
    first = min(hits, key=lambda h: h[1])
    ln = _line_of(t, first[1])
    sev = "high" if any(k.startswith(("payment", "tax", "Medicare")) for k in kinds) else "medium"
    entries = ["H-PROD-DATA-NON-PROD"] + (["R-TFN-MISHANDLING"] if any(k.startswith("tax") for k in kinds) else [])
    return [Finding("realistic-pii-in-fixtures", entries, sev, "medium",
                    f"Realistic personal data in test/fixture/data file: {', '.join(kinds)} ({len(hits)} value(s)).",
                    f.rel, ln, redact(_line_text(f, ln)), {"kinds": kinds, "count": len(hits)})]


def field_detectors(f: SourceFile) -> list[Finding]:
    out: list[Finding] = []
    ext = _ext(f)
    if f.is_test:
        return out
    t = f.text

    def add(fd: Finding) -> None:
        if not _suppressed(f, fd.line):
            out.append(fd)

    if ext in SCHEMA_EXT and not f.is_doc:
        sens = field_names(SENSITIVE_FIELD, t)
        if sens:
            names = sorted({n for n, _ in sens})
            consent_here = bool(CONSENT_MARK.search(t))
            ln = _line_of(t, sens[0][1])
            add(Finding("sensitive-fields-no-consent", ["R-APP3.3-SENSITIVE-WITHOUT-CONSENT"] if not consent_here else ["H-EXCESSIVE-COLLECTION"],
                        "high" if not consent_here else "medium", "medium",
                        f"Sensitive-information fields: {', '.join(names[:8])}."
                        + (" No consent capture in this file." if not consent_here else " A consent marker is present in this file; confirm consent is express and specific."),
                        f.rel, ln, redact(_line_text(f, ln)), {"fields": names, "consent_marker_in_file": consent_here}))
        exc = {m.group(0).lower() for m in EXCESSIVE_FIELD.finditer(t)}
        if len(exc) >= 3 and (ext in MARKUP_EXT or re.search(r"required|NOT NULL|nullable\s*=\s*False|z\.string\(\)|@IsNotEmpty", t)):
            m = EXCESSIVE_FIELD.search(t)
            ln = _line_of(t, m.start())
            add(Finding("excessive-fields", ["H-EXCESSIVE-COLLECTION"], "medium", "low",
                        f"Collects {len(exc)} commonly-unnecessary attributes ({', '.join(sorted(exc)[:8])}). Check each is reasonably necessary.",
                        f.rel, ln, redact(_line_text(f, ln)), {"fields": sorted(exc)}))
    if ext in MARKUP_EXT and FORM_NAME_FILE.search(f.rel):
        m = REQUIRED_ID.search(t)
        if m:
            ln = _line_of(t, m.start())
            add(Finding("forced-identification", ["R-APP2.1-FORCED-IDENTIFICATION"], "low", "low",
                        "Identity fields required on a contact/feedback-type form.", f.rel, ln, redact(_line_text(f, ln))))
    if ext in TEMPLATE_EXT and MARKETING_FILE.search(PurePosixPath(f.rel).name) and not UNSUB.search(t):
        add(Finding("marketing-no-unsubscribe", ["R-APP7-NO-OPT-OUT"], "medium", "medium",
                    "Marketing template with no unsubscribe or opt-out.", f.rel, 1))
    if ext in MARKUP_EXT and FORM_PI.search(t) and not NOTICE.search(t):
        m = FORM_PI.search(t)
        ln = _line_of(t, m.start())
        add(Finding("form-without-notice", ["R-APP5-NO-COLLECTION-NOTICE"], "low", "low",
                    "Form collects personal information with no privacy or collection notice in this view.", f.rel, ln,
                    redact(_line_text(f, ln))))
    if ext in CODE_EXT and SCRAPER.search(t) and SCRAPE_TARGET.search(t):
        m = SCRAPER.search(t)
        ln = _line_of(t, m.start())
        add(Finding("scraping-personal-data", ["H-SCRAPING-PUBLIC-DATA"], "high", "medium",
                    "Scraper code alongside social-media or profile targets.", f.rel, ln, redact(_line_text(f, ln))))
    return out


# --------------------------------------------------------------------------- repository-level

SENSITIVE_CONTEXT = re.compile(
    r"\b(?:health|medical|clinic|patients?|telehealth|pharmac\w*|fertility|ivf|mental\s+health|psycholog\w*|counsell?ing|"
    r"sexual\s+health|hiv|disabilit\w*|ndis|aged\s+care|hospital|gp|pathology|dental|religio\w*|church|trade\s+union|"
    r"political\s+party|dating|lgbt\w*|abortion|addiction|rehab\w*|domestic\s+violence|family\s+violence|"
    r"child\s+protection|out[- ]of[- ]home\s+care|youth\s+justice|homeless\w*|refugee|asylum)\b", re.I)
POLICY_PATH = re.compile(r"privacy[-_ ]?(?:policy|notice|statement)|/privacy(?:/|\.|$)|privacy\.(?:md|html?|mdx|tsx|jsx|vue|svelte|txt)$", re.I)
POLICY_LINK = re.compile(r"href\s*=\s*['\"{][^'\"}]*privacy|to\s*=\s*['\"]/privacy|path\s*[:=]\s*['\"]/privacy|['\"]/privacy(?:-policy)?['\"]", re.I)
RETENTION = re.compile(r"\bttl\b|expire_?after|expireAfterSeconds|lifecycle_rule|LifecycleConfiguration|lifecycle\s*\{|retention|purge|"
                       r"delete_?after|TimeToLiveSpecification|ttl_?attribute|expiration\s*\{|data_?deletion|anonymi[sz]e_?(?:old|after)|cleanup_?old", re.I)
RUNBOOK = re.compile(r"incident\s+response|data\s+breach|eligible\s+data\s+breach|notifiable\s+data\s+breach|breach\s+response|\bNDB\b", re.I)
AUDIT = re.compile(r"audit_?log|audit\s+trail|AuditLog|aws_cloudtrail|cloudtrail|pgaudit|access_?log|data_?access_?log", re.I)
PIA = re.compile(r"privacy\s+impact\s+assessment|privacy\s+threshold\s+assessment|\bDPIA\b|\bPIA\b", re.I)
PIA_PATH = re.compile(r"(?:^|/)(?:pia|dpia|pta)[-_.]|privacy[-_ ]?impact|privacy[-_ ]?(?:threshold[-_ ]?)?assessment", re.I)
CAPABILITY_TERMS = {
    "biometric-processing": (r"facial\s+recognition|biometric", "facial recognition / biometric processing"),
    "tracking-pixel": (r"pixel|advertis|cookie|tracking", "advertising pixels / tracking"),
    "session-replay": (r"session\s+(?:replay|record)|record\w*\s+(?:your\s+)?(?:session|interactions)", "session recording"),
    "location-collection": (r"location", "location data"),
    "automated-decision": (r"automated\s+decision|computer\s+program|algorithm|automated\s+means", "automated decisions"),
}
COUNTRY = re.compile(r"United\s+States|USA|\bUS\b|Ireland|United\s+Kingdom|\bUK\b|Singapore|Japan|India|Philippines|Germany|Netherlands|"
                     r"Canada|New\s+Zealand|European\s+Union|\bEU\b", re.I)

# What kind of codebase is this? Absence checks ("no privacy policy", "no retention") only make sense
# for something that is deployed and holds personal information.
DEPLOY_FILE = re.compile(r"(?:^|/)(?:dockerfile|docker-compose[\w.-]*\.ya?ml|compose\.ya?ml|procfile|vercel\.json|netlify\.toml|fly\.toml|"
                         r"app\.ya?ml|render\.ya?ml|serverless\.ya?ml|template\.ya?ml|samconfig\.toml|cdk\.json|wrangler\.toml|"
                         r"firebase\.json|amplify\.ya?ml|[\w-]+\.tf|chart\.ya?ml|k8s/[\w./-]+\.ya?ml|kustomization\.ya?ml)$", re.I)
MIGRATIONS = re.compile(r"(?:^|/)(?:migrations?|alembic|db/migrate|prisma/migrations|supabase/migrations)/", re.I)
APP_ROUTES = re.compile(r"(?:^|/)(?:src/routes|routes|pages|app|views|controllers|handlers|api)/[\w\[\]().@+-]+(?:/[\w\[\]().@+-]+)*\.(?:svelte|tsx|jsx|vue|ts|js|py|rb|php|astro)$", re.I)
SERVER_DEP = re.compile(r"['\"](?:express|fastify|koa|@nestjs/core|next|nuxt|@remix-run/\w+|hono|@sveltejs/adapter-[\w-]+|astro)['\"]\s*:|"
                        r"^\s*(?:django|flask|fastapi|starlette|rails|sinatra|laravel/framework|gin-gonic/gin)\b", re.I | re.M)


def system_kind(files: list[SourceFile]) -> tuple[str, list[str]]:
    """'application', 'library' or 'unknown', with the reasons."""
    why_app: list[str] = []
    deploy = [f.rel for f in files if DEPLOY_FILE.search(f.lower_rel)]
    if deploy:
        why_app.append(f"deployment configuration ({', '.join(deploy[:3])})")
    if any(MIGRATIONS.search(f.lower_rel) for f in files):
        why_app.append("database migrations")
    if any(FORM_PI.search(f.text) for f in files if _ext(f) in MARKUP_EXT and not f.is_test):
        why_app.append("forms that collect personal information")
    manifests = {f.path.name.lower(): f for f in files if f.path.name.lower() in DEP_FILES and "/" not in f.rel}
    lib_reasons: list[str] = []
    pkg = manifests.get("package.json")
    if pkg:
        try:
            pj = json.loads(pkg.text)
        except ValueError:
            pj = {}
        if isinstance(pj, dict):
            if (pj.get("exports") or pj.get("main") or pj.get("module")) and (pj.get("peerDependencies") or pj.get("files")):
                lib_reasons.append("package.json publishes a module (exports/main with peerDependencies or files)")
            if "svelte-package" in json.dumps(pj.get("scripts", {})):
                lib_reasons.append("svelte-package build")
    py = manifests.get("pyproject.toml")
    if py and "[project]" in py.text and not SERVER_DEP.search(py.text) and not deploy:
        lib_reasons.append("pyproject.toml declares a package without a web framework")
    if any(SERVER_DEP.search(m.text) for m in manifests.values()) and not lib_reasons:
        why_app.append("web/server framework dependency")
    if not lib_reasons and any(APP_ROUTES.search(f.lower_rel) for f in files if not f.is_test):
        why_app.append("application routes or handlers")
    if lib_reasons and not deploy and not any("migrations" in w or "forms" in w for w in why_app):
        return "library", lib_reasons
    if why_app:
        return "application", why_app
    return "unknown", ["no deployment configuration, routes, migrations or collection forms found"]


def sensitive_context_terms(files: list[SourceFile]) -> list[str]:
    """Terms suggesting a sensitive setting (health, religion, children at risk ...), from the README and
    manifests only. Needs two distinct terms, or one term used three or more times, to count."""
    text = " ".join(f.text[:20000] for f in files if f.rel.count("/") <= 1 and not f.is_test
                    and re.search(r"(?:^|/)(?:readme[\w.]*|package\.json|pyproject\.toml|app\.json|manifest\.json)$", f.lower_rel))
    found: dict[str, int] = {}
    for m in SENSITIVE_CONTEXT.finditer(text):
        k = m.group(0).lower()
        found[k] = found.get(k, 0) + 1
    if len(found) >= 2 or any(v >= 3 for v in found.values()):
        return sorted(found)[:12]
    return []


# Digital ID Act 2024. Strong phrases only: "relying party" alone is WebAuthn/OIDC vocabulary.
DIGITAL_ID_PROSE = re.compile(r"\bDigital ID Act\b|Australian Government Digital ID System|\bAGDIS\b|\bmyGovID\b|\bmyID\b|"
                              r"Trusted Digital Identity Framework|\bTDIF\b|digital ID accreditation|accredited (?:identity|attribute) service provider|"
                              r"identity exchange provider|participating relying party")
DIGITAL_ID_HOST = re.compile(r"\b(?:[\w-]+\.)*(?:digitalidentity|digitalid|mygovid|myid)\.gov\.au\b|\bmy\.gov\.au/(?:id|myid)\b", re.I)
# s 44(1) lists race or ethnicity, political opinions and associations, religion, philosophical beliefs, and sexual
# orientation or practices. Health and criminal record are not in the list.
DIGID_PROHIBITED = re.compile(r"ethnic|racial|race_|indigenous|atsi|religio|political|sexual|sexuality", re.I)
DIGID_LINKS = {"biometric-processing": "R-DIGID-BIOMETRIC-EXPRESS-CONSENT", "tracking-pixel": "R-DIGID-NO-PROFILING",
               "session-replay": "R-DIGID-NO-PROFILING", "sdk-autocollect-defaults": "R-DIGID-NO-PROFILING"}


def digital_id_terms(files: list[SourceFile]) -> list[str]:
    """Evidence that the project is part of, or relies on, the Australian Government Digital ID System: phrases in the
    README and manifests (depth <= 1), or Digital ID service hostnames in code and configuration."""
    found: set[str] = set()
    for f in files:
        if f.is_test:
            continue
        if f.rel.count("/") <= 1 and re.search(r"(?:^|/)(?:readme[\w.]*|package\.json|pyproject\.toml|app\.json)$", f.lower_rel):
            found |= {m.group(0) for m in DIGITAL_ID_PROSE.finditer(f.text[:50000])}
        if _ext(f) in CODE_EXT | MARKUP_EXT | IAC_EXT:
            found |= {m.group(0).lower() for m in DIGITAL_ID_HOST.finditer(f.text)}
    return sorted(found)[:10]


def link_digital_id(findings: list[Finding], role: str | None) -> None:
    """For an accredited entity, link the Digital ID Act rules to the detectors that engage them. The scan cannot
    tell whether a service is accredited, so this runs only when the team says so."""
    if role != "accredited_entity":
        return
    for fd in findings:
        rid = DIGID_LINKS.get(fd.detector)
        if fd.detector == "sensitive-fields-no-consent" and any(DIGID_PROHIBITED.search(n) for n in fd.extra.get("fields", [])):
            rid = "R-DIGID-PROHIBITED-ATTRIBUTES"
        if rid and rid not in fd.entries:
            fd.entries = fd.entries + [rid]
            if fd.detector in ("tracking-pixel", "session-replay") and SEVERITIES.index(fd.severity) < SEVERITIES.index("high"):
                fd.severity = "high"


def repo_level(files: list[SourceFile], findings: list[Finding], dumps: list[str], entity_type: str | None,
               kind: str, sens_ctx: list[str], handles_pi: bool) -> list[Finding]:
    out: list[Finding] = []
    by_det: dict[str, list[Finding]] = {}
    for fd in findings:
        by_det.setdefault(fd.detector, []).append(fd)

    policies = [f for f in files if POLICY_PATH.search(f.lower_rel) and not f.is_test]
    policy_text = "\n".join(f.text for f in policies)
    linked = any(POLICY_LINK.search(f.text) for f in files if _ext(f) in MARKUP_EXT | CODE_EXT)

    if sens_ctx:
        for d in ("tracking-pixel", "session-replay"):
            for fd in by_det.get(d, []):
                fd.severity = "critical" if d == "tracking-pixel" else "high"
                fd.extra["escalated"] = f"repository indicates sensitive context: {', '.join(sens_ctx[:5])}"
                if d == "tracking-pixel" and "R-APP3.3-SENSITIVE-WITHOUT-CONSENT" not in fd.entries:
                    fd.entries = fd.entries + ["R-APP3.3-SENSITIVE-WITHOUT-CONSENT"]
    for fd in by_det.get("biometric-processing", []):
        f = next((x for x in files if x.rel == fd.file), None)
        if f is not None and not CONSENT_MARK.search(f.text):
            fd.entries = fd.entries + ["R-APP3.3-SENSITIVE-WITHOUT-CONSENT"]
            fd.message += " No consent capture in this file."

    collects = bool(by_det.get("tracking-pixel") or by_det.get("session-replay")) or any(
        FORM_PI.search(f.text) for f in files if _ext(f) in MARKUP_EXT and not f.is_test)
    if kind != "library" and collects and not policies and not linked:
        out.append(Finding("privacy-policy-missing", ["R-APP1.3-NO-PRIVACY-POLICY"], "high", "medium",
                           "The code collects personal information (forms, pixels or session replay) but the repository has no privacy "
                           "policy file, route or link. It may be hosted elsewhere; confirm a policy is published and linked from every collection point."))

    adm = [f for f in files if _ext(f) in CODE_EXT and not f.is_test and AUTO_DECISION.search(f.text)]
    if adm:
        m = AUTO_DECISION.search(adm[0].text)
        ln = _line_of(adm[0].text, m.start())
        fd = Finding("automated-decision", ["R-APP1.7-AUTOMATED-DECISIONS"], "high" if policies else "medium", "low",
                     f"Code that appears to make or substantially assist decisions about individuals ({len(adm)} file(s)). From 10 December 2026 the privacy policy must describe automated decisions.",
                     adm[0].rel, ln, redact(_line_text(adm[0], ln)), {"files": [f.rel for f in adm[:10]]})
        if policies and re.search(CAPABILITY_TERMS["automated-decision"][0], policy_text, re.I):
            fd.severity, fd.message = "info", fd.message + " The policy appears to mention automated decisions; check it covers APP 1.8."
        out.append(fd)
        by_det.setdefault("automated-decision", []).append(fd)

    if policies:
        for det, (rx, label) in CAPABILITY_TERMS.items():
            if by_det.get(det) and not re.search(rx, policy_text, re.I):
                out.append(Finding("privacy-policy-omits-capability", ["R-APP1.3-NO-PRIVACY-POLICY", "R-APP1.4-POLICY-CONTENTS"], "medium", "medium",
                                   f"Repository uses {label}, but the privacy policy does not mention it.", policies[0].rel,
                                   extra={"capability": det}))
        missing = []
        for label, rx in (("access and correction", r"access[^.]{0,80}correct|correct[^.]{0,80}access"), ("complaints", r"complain"),
                          ("overseas disclosure", r"overseas|outside\s+(?:of\s+)?Australia|offshore|other\s+countries")):
            if not re.search(rx, policy_text, re.I):
                missing.append(label)
        offshore = by_det.get("non-au-region") or by_det.get("overseas-processor-sdk")
        if offshore and not COUNTRY.search(policy_text):
            missing.append("countries of overseas recipients (offshore regions/processors detected)")
        if missing:
            out.append(Finding("privacy-policy-contents", ["R-APP1.4-POLICY-CONTENTS"], "medium", "medium",
                               f"Privacy policy may be missing APP 1.4 matters: {', '.join(missing)}.", policies[0].rel, extra={"missing": missing}))

    # Absence checks: only for a deployed system that holds personal information. In a library, or a repo
    # with no evidence of personal information, "not found here" tells the team nothing.
    if kind != "library" and handles_pi:
        if not any(RETENTION.search(f.text) for f in files):
            out.append(Finding("no-retention-controls", ["H-RETENTION-NO-DESTRUCTION"], "low", "low",
                               "Personal information is stored but no TTL, lifecycle, purge or retention mechanism appears anywhere in the repository."))
        if not any(RUNBOOK.search(f.text) for f in files):
            out.append(Finding("no-breach-runbook", ["H-BREACH-ASSESSMENT-READINESS"], "low", "low",
                               "No data breach / incident response material in the repository (it may live elsewhere)."))
        if not any(AUDIT.search(f.text) for f in files if not f.is_doc):
            out.append(Finding("no-audit-logging", ["H-BREACH-ASSESSMENT-READINESS", "H-INSIDER-ACCESS-SAFEGUARDS"], "low", "low",
                               "No audit or data-access logging found. Breach scoping and detecting staff misuse both depend on it."))
        serious = [fd for fd in findings + out if SEVERITIES.index(fd.severity) >= 3]
        if serious and not any(PIA_PATH.search(f.lower_rel) or PIA.search(f.text) for f in files if f.is_doc):
            out.append(Finding("no-pia", ["H-NO-PIA-HIGH-RISK"], "high" if entity_type == "agency" else "medium", "medium",
                               f"{len(serious)} high/critical signal(s) and no privacy impact or threshold assessment in the repository."
                               + (" Australian Government agencies must conduct a PIA for high privacy risk projects." if entity_type == "agency" else "")))
    for rel in dumps[:20]:
        out.append(Finding("data-dump-committed", ["H-PROD-DATA-NON-PROD"], "medium", "low",
                           "Data export or database file committed (not parsed). Check whether it contains personal information.", rel))
    return out


def processor_findings(files: list[SourceFile]) -> list[Finding]:
    found: dict[str, list[str]] = {}
    for f in files:
        name = f.path.name.lower()
        if name in DEP_FILES or (_ext(f) in CODE_EXT | MARKUP_EXT and not f.is_test):
            for proc, rx in PROCESSORS.items():
                if re.search(rx, f.text, re.I if proc not in {"Stripe"} else 0):
                    found.setdefault(proc, []).append(f.rel)
    out = []
    for proc, rels in sorted(found.items()):
        llm = proc in LLM_PROCESSORS
        out.append(Finding("overseas-processor-sdk", ["H-OVERSEAS-PROCESSING"], "medium" if llm else "low", "medium",
                           f"{proc} SDK/API in use: likely an overseas recipient of personal information."
                           + (" Prompts and context sent to an AI API are disclosures; minimise or redact personal information." if llm else ""),
                           rels[0], extra={"processor": proc, "files": rels[:10], "llm": llm}))
    return out
