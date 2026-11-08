"""Static detectors. Each maps a repository signal to a rule id in the knowledge base.

ism-review: ignore-file  (this module is made of the patterns it looks for)

A detector never decides that a control is unmet. It reports a signal with file and line evidence against the rule it bears
on; the server attaches the requirement, fidelity and guidance. Presence signals (a setting that is off, a secret in a file)
carry confidence "high" or "medium". Absence signals (no SBOM step, no security headers) carry "low": the repository is not
the whole system, and the finding says what would settle it.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field

from .files import SourceFile

LINE_IGNORE = "ism-review: ignore"
CONFIDENCES = ["low", "medium", "high"]


@dataclass
class Finding:
    detector: str
    rule: str
    confidence: str
    message: str
    file: str | None = None
    line: int | None = None
    evidence: str | None = None
    kind: str = "presence"  # presence | absence
    extra: dict = field(default_factory=dict)


# ---- redaction -------------------------------------------------------------------------------------------------------
_SECRET_VALUE = re.compile(r"""(?i)((?:pass(?:word|wd)?|secret|token|api[_-]?key|access[_-]?key|private[_-]?key|client[_-]?secret)\w*["']?\s*[:=]\s*["']?)([^"'\s,;]{4,})""")
_KNOWN_KEYS = re.compile(r"AKIA[0-9A-Z]{12}[0-9A-Z]{4}|gh[pousr]_[A-Za-z0-9]{12,}|xox[baprs]-[A-Za-z0-9-]{10,}|AIza[0-9A-Za-z_\-]{25,}|[sr]k_live_[0-9A-Za-z]{10,}")


_URL_PASSWORD = re.compile(r"(://[^/\s:@\"']+:)[^/\s@\"']+(@)")


def redact(line: str, limit: int = 200) -> str:
    line = _URL_PASSWORD.sub(r"\1[redacted]\2", line)
    line = _KNOWN_KEYS.sub(lambda m: m.group(0)[:4] + "…[redacted]", line.strip())
    line = _SECRET_VALUE.sub(lambda m: m.group(1) + "[redacted]", line)
    return line if len(line) <= limit else line[:limit] + "…"


# ---- line patterns ---------------------------------------------------------------------------------------------------
CODE = {".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".vue", ".svelte", ".astro", ".php", ".rb", ".go", ".java", ".kt", ".cs", ".rs", ".scala", ".swift", ".sh"}
IAC = {".tf", ".tfvars", ".hcl", ".yaml", ".yml", ".json", ".toml", ".env", ".ini", ".conf", ".properties", ".cfg"}
CONFIG_AND_CODE = CODE | IAC | {".dockerfile", ".xml", ".gradle"}


@dataclass
class Pat:
    detector: str
    rule: str
    regex: re.Pattern
    confidence: str
    message: str
    exts: set[str] | None = None
    skip_tests: bool = True
    near: re.Pattern | None = None  # also require this within +/-6 lines
    unless: re.Pattern | None = None  # skip the line if this matches it
    extra: dict = field(default_factory=dict)

    def run(self, f: SourceFile) -> list[Finding]:
        if f.ext == ".json" and (len(f.text) > 100_000 or "/data/" in "/" + f.lower_rel):
            return []  # bulk data (datasets, knowledge bases) quotes text; it is not configuration
        if (self.skip_tests and f.is_test) or (self.exts is not None and f.ext not in self.exts and not (".dockerfile" in self.exts and f.name.startswith("dockerfile"))):
            return []
        out: list[Finding] = []
        lines = f.lines
        for i, ln in enumerate(lines):
            if LINE_IGNORE in ln or len(ln) > 2000:
                continue
            if self.regex.search(ln) and not (self.unless and self.unless.search(ln)):
                if self.near:
                    window = "\n".join(lines[max(0, i - 6): i + 7])
                    if not self.near.search(window):
                        continue
                out.append(Finding(self.detector, self.rule, self.confidence, self.message, f.rel, i + 1, redact(ln), extra=dict(self.extra)))
        return out


def P(detector, rule, regex, confidence, message, exts=None, **kw) -> Pat:
    return Pat(detector, rule, re.compile(regex), confidence, message, exts, **kw)


PLACEHOLDER = re.compile(r"(?i)(example|sample|changeme|change_me|your[_-]|<[^>]+>|\$\{|\{\{|xxx|\*{3,}|todo|dummy|placeholder|fake|test|redacted|os\.environ|getenv|process\.env|secretsmanager|ssm:|vault:|var\.|data\.|\bnone\b|\bnull\b)")

PATTERNS: list[Pat] = [
    # credentials
    P("static-cloud-key", "R-CRED-SHORT-LIVED", r"AKIA[0-9A-Z]{16}|aws_secret_access_key\s*[:=]\s*[\"']?[A-Za-z0-9/+=]{30,}|\"private_key_id\"\s*:|AccountKey=[A-Za-z0-9+/=]{20,}", "high",
      "A long-lived cloud access key is present in the repository.", unless=PLACEHOLDER),
    P("private-key-committed", "R-CRED-CLEAR", r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |ENCRYPTED |PGP )?PRIVATE KEY(?: BLOCK)?-----", "high",
      "A private key is stored in the repository.", skip_tests=True),
    P("secret-literal", "R-CRED-SECRETS-MANAGER",
      r"""(?i)\b(?:[\w-]*(?:password|passwd|pwd|secret|api[_-]?key|apikey|auth[_-]?token|access[_-]?token|client[_-]?secret|private[_-]?key|connection[_-]?string))\b["']?\s*(?::|=|=>)\s*["'][^"'\s${}<>]{8,}["']""",
      "high", "A credential appears to be written into a file.", CONFIG_AND_CODE, unless=PLACEHOLDER),
    P("secret-literal", "R-CRED-SECRETS-MANAGER", r"gh[pousr]_[A-Za-z0-9]{20,}|xox[baprs]-[A-Za-z0-9-]{20,}|[sr]k_live_[0-9A-Za-z]{16,}|AIza[0-9A-Za-z_\-]{35}", "high",
      "A provider token is present in a file.", unless=PLACEHOLDER),
    P("secret-literal", "R-CRED-SECRETS-MANAGER", r"[a-z][a-z0-9+.-]*://[^/\s:@\"']+:[^/\s:@\"'$]{6,}@[\w.-]+", "high",
      "A connection URL embeds a password.", CONFIG_AND_CODE, unless=PLACEHOLDER),
    P("default-credentials", "R-DEFAULT-CREDS",
      r"""(?i)(?:POSTGRES_PASSWORD|MYSQL_ROOT_PASSWORD|MYSQL_PASSWORD|MONGO_INITDB_ROOT_PASSWORD|RABBITMQ_DEFAULT_PASS|REDIS_PASSWORD|ADMIN_PASSWORD|GF_SECURITY_ADMIN_PASSWORD|MINIO_ROOT_PASSWORD)["']?\s*[:=]\s*["']?(?:postgres|password|passw0rd|admin|root|guest|changeme|secret|123456|minioadmin|test|letmein)["']?\s*$""",
      "high", "A service is configured with a well-known default password.", CONFIG_AND_CODE | {".env"}),
    P("default-credentials", "R-DEFAULT-CREDS", r"""(?i)\b(?:username|user)\b["']?\s*[:=]\s*["']?admin["']?.{0,40}\bpassword\b["']?\s*[:=]\s*["']?(?:admin|password|changeme|123456)["']?""", "high",
      "An administrator account is configured with a default password.", CONFIG_AND_CODE),
    # identity
    P("mfa-disabled", "R-MFA", r"""(?i)(?:mfa_configuration["']?\s*[:=]\s*["']?OFF|(?:enable[_-]?|require[_-]?|enforce[_-]?)?mfa(?:[_-]?(?:enabled|required|enforced|status))?["']?\s*[:=]\s*["']?(?:false|off|disabled|0)["']?\b|mfa[_-]?enabled["']?\s*[:=]\s*false)""",
      "high", "Multi-factor authentication is switched off in configuration.", IAC | CODE),
    # TLS
    P("tls-old-version", "R-TLS-VERSION",
      r"""(?i)(?:\bSSLv[23]\b|\bTLSv?1(?:\.0|\.1|_0|_1)?(?![\d._]*[2-9])\b(?!\.?[23])|PROTOCOL_(?:SSLv23|TLSv1|TLSv1_1)\b|min(?:imum)?[_-]?(?:tls|protocol)[_-]?version["']?\s*[:=]\s*["']?(?:tls)?v?1[._]?[01]\b|ssl_protocols[^;\n]*\bTLSv1(?:\.1)?\b|TLS1_[01]\b|TLS_?1_?[01]\b|NODE_TLS_MIN_VERSION\s*=\s*TLSv1(?:\.1)?\b)""",
      "high", "A TLS or SSL version below TLS 1.2 is permitted or selected.", CONFIG_AND_CODE | {".conf"}, unless=re.compile(r"(?i)TLSv?1[._]?[23]|disable|\bno[_ -]?(?:ssl|tls)|OP_NO_")),
    P("tls-weak-cipher", "R-TLS-CIPHERS", r"""(?i)(?:ssl_ciphers|cipher[_ -]?(?:suite|list)s?|ciphers|TLS_?PROTOCOL|SSLCipherSuite)\b[^\n]*(?:\bRC4\b|\b3DES\b|DES-CBC3|\bNULL\b|\bEXPORT\b|\baNULL\b|\bADH\b|-CBC-|_CBC_|\bMD5\b)""",
      "medium", "A TLS cipher list permits weak or non-GCM suites.", CONFIG_AND_CODE | {".conf"}, unless=re.compile(r"[!-]\s*(?:RC4|3DES|NULL|EXPORT|aNULL|ADH|MD5)")),
    P("tls-weak-cipher", "R-TLS-CIPHERS", r"(?i)\btls[_-]?compression\b[\"']?\s*[:=]\s*[\"']?(?:true|on|enabled)", "medium", "TLS compression is enabled.", CONFIG_AND_CODE),
    P("https-not-enforced", "R-HTTPS-ONLY",
      r"""(?i)(?:ssl[_-]?redirect|force[_-]?https|enforce[_-]?https|https[_-]?only|SECURE_SSL_REDIRECT|redirect_http_to_https)["']?\s*[:=]\s*["']?(?:false|off|0|no)\b|viewer_protocol_policy\s*=\s*["']allow-all["']|(?:allow|permit)[_-]?http["']?\s*[:=]\s*["']?(?:true|on|yes)""",
      "high", "HTTPS redirection is turned off or plain HTTP is permitted.", CONFIG_AND_CODE),
    # network
    P("open-ingress", "R-INGRESS", r"""(?:0\.0\.0\.0/0|::/0)""", "medium", "A rule admits the whole internet.", IAC | {".dockerfile"},
      near=re.compile(r"(?i)\b(?:ingress|inbound|from_port|ingress_rules|source[_-]?address|source_ranges|allow)\b"), unless=re.compile(r"(?i)egress|outbound|destination|^\s*#")),
    P("public-storage", "R-INGRESS", r"""(?i)\bacl\s*=\s*["']public-read(?:-write)?["']|block_public_(?:acls|policy)\s*=\s*false|restrict_public_buckets\s*=\s*false|publicly_accessible\s*=\s*true|\ballUsers\b|\ballAuthenticatedUsers\b|public_network_access(?:_enabled)?\s*[=:]\s*["']?(?:true|Enabled)["']?|"Principal"\s*:\s*"\*"|allow_blob_public_access\s*=\s*true""",
      "high", "Storage or a database endpoint is publicly accessible.", IAC),
    # web
    P("cookie-flags-off", "R-COOKIE-FLAGS",
      r"""(?i)(?:SESSION_COOKIE_(?:SECURE|HTTPONLY)|CSRF_COOKIE_SECURE)\s*=\s*False|cookie[^\n]{0,80}\b(?:httponly|http_only|secure)["']?\s*[:=]\s*["']?false|\b(?:httponly|secure)["']?\s*[:=]\s*["']?false["']?[^\n]{0,80}cookie|samesite["']?\s*[:=]\s*["']?none["']?""",
      "high", "A session cookie flag (HttpOnly, Secure or SameSite) is explicitly turned off.", CODE | IAC),
    P("output-encoding-off", "R-OUTPUT-ENCODING", r"""\.innerHTML\s*=|dangerouslySetInnerHTML|\|\s*safe\b|\{%\s*autoescape\s+off|\bv-html\b|\{@html\b|\bmark_safe\(|autoescape\s*=\s*False|document\.write\(""",
      "medium", "Output is written without encoding.", CODE | {".html", ".htm", ".j2", ".jinja", ".erb", ".ejs"}),
    P("injection-sink", "R-INPUT-VALIDATION",
      r"""(?:execute|executemany|raw|query)\(\s*(?:f["']|"[^"]*"\s*(?:%|\+|\.format\()|'[^']*'\s*(?:%|\+|\.format\()|[A-Za-z_.]+\s*\+\s*)|\bos\.system\(\s*f?["'][^"']*(?:\{|%s|"\s*\+)|subprocess\.\w+\([^)]*shell\s*=\s*True|\beval\(\s*(?:request|req\.|input\()|child_process\.exec\(\s*`[^`]*\$\{|\bmysql_query\(.*\$_(?:GET|POST|REQUEST)""",
      "medium", "Request or variable data reaches an interpreter by string construction.", CODE,
      unless=re.compile(r"""["']\s*,\s*[(\[]|["']\s*,\s*\w+\s*\)""")),
    P("unsafe-deserialisation", "R-UNSAFE-DESER",
      r"""\bpickle\.loads?\(|\bcPickle\.loads?\(|\bmarshal\.loads?\(|\byaml\.load\((?![^)]*Loader\s*=\s*(?:yaml\.)?(?:Safe|CSafe))(?![^)]*SafeLoader)|\bObjectInputStream\(|\bunserialize\(|\bjsonpickle\.decode\(|node-serialize|\bBinaryFormatter\b""",
      "medium", "Data is deserialised with a format that can execute code.", CODE),
    # AI
    P("unsafe-model-format", "R-AI-MODEL-FORMAT",
      r"""\btorch\.load\((?![^)]*weights_only\s*=\s*True)|\bjoblib\.load\(|allow_dangerous_deserialization\s*=\s*True|trust_remote_code\s*=\s*True|use_safetensors\s*=\s*False|\bkeras\.models\.load_model\([^)]*safe_mode\s*=\s*False""",
      "high", "A model is loaded with a method that can execute arbitrary code.", CODE),
    P("ai-confidence-exposed", "R-AI-CONFIDENCE", r"""\blogprobs["']?\s*[:=]\s*(?:True|true|\d+)|\btop_logprobs\b|\breturn_logprobs\b""", "low",
      "Log-probabilities are requested; if returned to callers they expose exact confidence.", CODE),
    P("ai-training-on-user-data", "R-AI-TRAINING-CONSENT",
      r"""(?i)\b(?:fine-?tun\w*|train\w*|retrain\w*)\b[^.\n]{0,40}\b(?:on|using|with|from)\b[^.\n]{0,30}\b(?:user|customer|client|conversation|chat|prompt)s?\b[^.\n]{0,20}\b(?:data|conversations?|messages|logs|history|prompts)\b""",
      "low", "Training or fine-tuning on data collected from users is described.", CODE | {".md", ".mdx", ".txt", ".rst"}, skip_tests=True),
    P("agent-broad-tools", "R-AI-AGENT-LEAST-TOOLS",
      r"""\b(?:ShellTool|BashTool|PythonREPLTool|PythonAstREPLTool|LocalCommandLineCodeExecutor)\b|allow_dangerous_code\s*=\s*True|dangerously[-_ ]?skip[-_ ]?permissions|bypassPermissions|auto_?approve\w*["']?\s*[:=]\s*["']?(?:true|True|1)|human_input_mode\s*=\s*["']NEVER["']|allowed_tools\s*=\s*\[\s*["']\*["']""",
      "medium", "An agent is given broad execution capability or run without an approval step.", CODE | IAC),
    # supply chain
    P("untrusted-source", "R-TRUSTED-SOURCES", r"""--extra-index-url|--trusted-host|git\+https?://|\bcurl\b[^\n|]*\|\s*(?:sudo\s+)?(?:ba)?sh\b|\bwget\b[^\n|]*\|\s*(?:sudo\s+)?(?:ba)?sh\b|^\s*ADD\s+https?://|npm\s+install\s+https?://""",
      "medium", "A dependency or build step is fetched from outside a controlled registry.", {".txt", ".toml", ".dockerfile", ".sh", ".yml", ".yaml", ".cfg"},
      unless=re.compile(r"^\s*#")),
    P("untrusted-source", "R-TRUSTED-SOURCES", r"""^\s*"(?!homepage|url|repository|bugs|\$schema|main|types|funding|license)[@\w./-]+"\s*:\s*"(?:git\+|git://|github:|https?://)[^"]+"\s*,?\s*$""",
      "medium", "A package.json dependency is fetched from a URL rather than a registry.", {".json"}),
    P("unpinned-dependencies", "R-PINNED-DEPS", r"""uses:\s*[\w./-]+@(?:main|master|latest|develop)\b""", "medium", "A CI action is referenced by a moving branch.", {".yml", ".yaml"}),
    P("unpinned-dependencies", "R-PINNED-DEPS", r""""[@\w./-]+"\s*:\s*"(?:latest|\*|x)"\s*,?\s*$""", "medium", "A dependency uses 'latest' or a wildcard.", {".json"}),
    # logging
    P("log-retention-short", "R-LOG-CENTRAL", r"""(?i)retention(?:_in)?_days\s*[=:]\s*(?:[1-9]|[1-9]\d|[1-2]\d\d|3[0-5]\d)\b""", "medium",
      "Log retention is configured below twelve months.", IAC),
]


# ---- repository-level checks -----------------------------------------------------------------------------------------
CI_FILES = re.compile(r"(?i)(?:^|/)(?:\.github/workflows/[^/]+\.ya?ml|\.gitlab-ci\.ya?ml|azure-pipelines\.ya?ml|jenkinsfile|\.circleci/config\.ya?ml|bitbucket-pipelines\.ya?ml|buildspec\.ya?ml|cloudbuild\.ya?ml|\.drone\.ya?ml)$")
SEC_TESTING = re.compile(r"(?i)codeql|semgrep|bandit|snyk|trivy|grype|sonar|osv-scanner|dependency-review|pip-audit|npm audit|yarn audit|gosec|checkmarx|veracode|zaproxy|owasp[/ -]zap|\bzap-|\bsast\b|\bdast\b|\bsca\b|safety check|brakeman|cargo[- ]audit|cargo[- ]deny|govulncheck|detect-secrets|gitleaks|trufflehog|checkov|tfsec|devskim|fortify|mend|whitesource")
SBOM_RE = re.compile(r"(?i)cyclonedx|\bspdx\b|\bsyft\b|\bsbom\b|cdxgen|bom\.json|sbom-action|docker/build-push-action[^\n]*sbom|sbom\s*:\s*true")
UPDATE_RE = re.compile(r"(?i)(?:^|/)(?:\.github/dependabot\.ya?ml|renovate\.json5?|\.renovaterc(?:\.json)?|\.gitlab/renovate\.json)$|dependabot|renovate")
HEADERS_RE = re.compile(r"(?i)helmet|content-security-policy|strict-transport-security|x-frame-options|secure_headers|django-csp|SECURE_HSTS|flask-talisman|talisman|\badd_header\b|SecurityHeaders|secure-headers|csp\(|Header always set")
WEB_FRAMEWORKS = re.compile(r"(?i)\b(?:flask|django|fastapi|starlette|express|koa|fastify|hapi|nestjs|@nestjs|rails|sinatra|spring-boot|springframework|aspnetcore|laravel|symfony|gin-gonic|echo|next|nuxt|sveltekit|@sveltejs/kit|remix|astro)\b")
AI_USAGE = re.compile(r"(?i)\b(?:openai|anthropic|langchain\w*|llama[_-]?index|transformers|torch|tensorflow|keras|vertexai|google\.generativeai|google-genai|bedrock|mistralai|cohere|ollama|litellm|huggingface[_-]hub|sentence[_-]transformers|onnxruntime)\b")
AGENT_USAGE = re.compile(r"(?i)\b(?:langgraph|autogen|crewai|openai-agents|agents\.Agent|AgentExecutor|create_react_agent|claude[-_]agent[-_]sdk|smolagents|pydantic[-_]ai)\b")
AI_DOCS = re.compile(r"(?i)model[ _-]?cards?|system[ _-]?cards?|MODEL_CARD|SYSTEM_CARD")
AGENT_REGISTER = re.compile(r"(?i)agent[ _-]?register|agents?\.(?:ya?ml|json|md)\b|register of (?:ai )?agents")
LOG_FWD = re.compile(r"(?i)fluent(?:d|-bit|bit)?|filebeat|logstash|\bvector\b|opentelemetry|\botel\b|cloudwatch|log_group|aws_cloudwatch_log|datadog|splunk|syslog|\bloki\b|promtail|stackdriver|cloud logging|azure[ _-]?monitor|log[ _-]?analytics|elastic|sentinel|firehose|papertrail|sumologic|graylog|logging\.googleapis")
SERVICE_RE = re.compile(r"(?i)^\s*FROM\s|apiVersion:\s*apps/v1|kind:\s*(?:Deployment|StatefulSet|DaemonSet)|aws_(?:instance|ecs_service|lambda_function|eks_cluster)|google_compute_instance|azurerm_(?:linux|windows)_virtual_machine|azurerm_app_service|services:\s*$")
DEP_MANIFESTS = {"package.json": {"package-lock.json", "yarn.lock", "pnpm-lock.yaml", "bun.lockb", "bun.lock"},
                 "pyproject.toml": {"uv.lock", "poetry.lock", "pdm.lock", "pipfile.lock"}, "pipfile": {"pipfile.lock"},
                 "cargo.toml": {"cargo.lock"}, "go.mod": {"go.sum"}, "gemfile": {"gemfile.lock"}, "composer.json": {"composer.lock"}}
MODEL_EXT = {".pkl", ".pickle", ".pt", ".pth", ".joblib", ".ckpt", ".h5", ".npy"}


def _first(files: list[SourceFile], regex: re.Pattern, only=lambda f: True) -> tuple[str, int, str] | None:
    for f in files:
        if not only(f):
            continue
        for i, ln in enumerate(f.lines):
            if regex.search(ln):
                return f.rel, i + 1, redact(ln)
    return None


def _any(files: list[SourceFile], regex: re.Pattern, only=lambda f: True) -> bool:
    return any(regex.search(f.text) for f in files if only(f))


def detect_context(files: list[SourceFile], all_paths: list[str]) -> dict:
    code = [f for f in files if not f.is_test]
    manifests = [f for f in code if f.name in {"package.json", "pyproject.toml", "requirements.txt", "gemfile", "pom.xml", "build.gradle", "go.mod", "composer.json", "cargo.toml"}
                 or f.name.startswith("requirements")]
    mtext = "\n".join(f.text for f in manifests)
    code_ext = {f.ext for f in code}
    return {
        "has_code": bool(code_ext & CODE), "has_ci": any(CI_FILES.search(p) for p in all_paths), "has_manifests": bool(manifests),
        "web": bool(WEB_FRAMEWORKS.search(mtext)) or any(f.ext in {".html", ".htm", ".vue", ".svelte", ".tsx", ".jsx"} for f in code),
        "ai": bool(AI_USAGE.search(mtext)) or _any(code, re.compile(r"(?i)^\s*(?:import|from)\s+(?:openai|anthropic|langchain|transformers|torch|tensorflow)"), lambda f: f.ext == ".py"),
        "agents": _any(code, AGENT_USAGE, lambda f: f.ext in CODE | {".toml", ".json", ".txt"}),
        "services": _any(files, SERVICE_RE, lambda f: f.name.startswith("dockerfile") or f.ext in {".yaml", ".yml", ".tf"}),
        "cloud": any(p.endswith((".tf", ".tfvars")) or "cloudformation" in p.lower() or p.lower().endswith(("serverless.yml", "template.yaml", "cdk.json")) for p in all_paths),
    }


def repo_level(files: list[SourceFile], all_paths: list[str], ctx: dict) -> list[Finding]:
    out: list[Finding] = []
    ci = [f for f in files if CI_FILES.search(f.rel)]
    build_text_files = ci + [f for f in files if f.name in {"makefile", "justfile", "package.json", "pyproject.toml", "tox.ini", "noxfile.py"}]

    # CI security testing
    if ctx["has_code"]:
        if ci and not _any(build_text_files, SEC_TESTING):
            out.append(Finding("ci-no-security-testing", "R-SAST-SCA", "medium",
                               "The CI pipeline builds the software but runs no static analysis, dependency (SCA) or dynamic security test.", ci[0].rel, kind="absence"))
        elif not ci:
            out.append(Finding("ci-no-security-testing", "R-SAST-SCA", "low",
                               "No CI pipeline definition was found, so no security testing step can be evidenced from the repository.", kind="absence"))
    # SBOM
    if ctx["has_manifests"]:
        has = _any(files, SBOM_RE, lambda f: CI_FILES.search(f.rel) is not None or f.name in {"makefile", "package.json", "pyproject.toml", "dockerfile"}) or any(
            re.search(r"(?i)(sbom|\.cdx\.json|\.spdx|bom\.(?:json|xml))", p) for p in all_paths)
        if not has:
            for rule in ("R-SBOM-PRODUCE", "R-SBOM-USE"):
                out.append(Finding("no-sbom", rule, "low", "No software bill of materials generation or SBOM file was found.", kind="absence"))
        # update automation
        if not any(UPDATE_RE.search(p) for p in all_paths):
            out.append(Finding("no-update-automation", "R-PATCH-AUTOMATION", "low", "No dependency update automation (Dependabot, Renovate) was found.", kind="absence"))
    # lockfiles
    names = {p.rsplit("/", 1)[-1].lower() for p in all_paths}
    for m in [f for f in files if f.name in DEP_MANIFESTS and not f.is_test]:
        if m.name == "package.json" and '"dependencies"' not in m.text and '"devDependencies"' not in m.text:
            continue
        if m.name == "pyproject.toml" and "dependencies" not in m.text:
            continue
        base = m.rel.rsplit("/", 1)[0] + "/" if "/" in m.rel else ""
        local = {p.rsplit("/", 1)[-1].lower() for p in all_paths if p.lower().startswith(base.lower()) and "/" not in p[len(base):]}
        if not (DEP_MANIFESTS[m.name] & (local | (names if not base else set()))):
            out.append(Finding("missing-lockfile", "R-PINNED-DEPS", "medium", f"{m.rel} declares dependencies but no lockfile ({', '.join(sorted(DEP_MANIFESTS[m.name]))}) is committed.", m.rel, kind="absence"))
    for f in files:
        if f.is_test or not (f.name.startswith("requirements") and f.ext == ".txt"):
            continue
        for i, ln in enumerate(f.lines):
            s = ln.strip()
            if s and not s.startswith(("#", "-", "git+")) and not re.search(r"==|@ |\bfile:", s) and not LINE_IGNORE in ln:
                out.append(Finding("unpinned-dependencies", "R-PINNED-DEPS", "medium", "A Python requirement is not pinned to an exact version.", f.rel, i + 1, s[:120]))
    # floating base images
    for f in files:
        if f.is_test or not (f.name.startswith("dockerfile") or f.ext == ".dockerfile"):
            continue
        for i, ln in enumerate(f.lines):
            m = re.match(r"^\s*FROM\s+(?:--platform=\S+\s+)?(\S+)", ln, re.I)
            if not m or LINE_IGNORE in ln:
                continue
            img = m.group(1)
            if img.lower() == "scratch" or "$" in img or "@sha256:" in img or img in {a.lower() for a in re.findall(r"(?i)\bAS\s+(\S+)", f.text)}:
                continue
            tag = img.split(":", 1)[1] if ":" in img.rsplit("/", 1)[-1] else ""
            if not tag or tag == "latest":
                out.append(Finding("unpinned-dependencies", "R-PINNED-DEPS", "medium", "A base image uses a floating tag; pin a version or digest.", f.rel, i + 1, ln.strip()[:120]))
    # security headers
    if ctx["web"] and not _any([f for f in files if not f.is_test], HEADERS_RE):
        out.append(Finding("no-security-headers", "R-SEC-HEADERS", "low",
                           "A web application is present but no Content-Security-Policy, Strict-Transport-Security or X-Frame-Options configuration was found (they may be set at the proxy or CDN).", kind="absence"))
    # AI
    if ctx["ai"] and not (_any(files, AI_DOCS, lambda f: f.is_prose) or any(AI_DOCS.search(p) for p in all_paths)):
        out.append(Finding("ai-no-model-card", "R-AI-DOCS", "low", "AI models are used but no model card or system card was found.", kind="absence"))
    if ctx["agents"] and not (_any(files, AGENT_REGISTER, lambda f: not f.is_test) or any(AGENT_REGISTER.search(p) for p in all_paths)):
        out.append(Finding("agent-no-register", "R-AI-AGENT-REGISTER", "low", "AI agents or tools are defined but no AI agent register was found.", kind="absence"))
    for p in all_paths:
        if any(p.lower().endswith(e) for e in MODEL_EXT) and "/test" not in p.lower():
            out.append(Finding("unsafe-model-format", "R-AI-MODEL-FORMAT", "medium", "A model artefact in a format that can execute code on load is committed.", p))
    # logging
    if ctx["services"] and not (_any(files, LOG_FWD) or any(LOG_FWD.search(p) for p in all_paths)):
        out.append(Finding("no-log-forwarding", "R-LOG-CENTRAL", "low", "Services are defined but no log forwarding or central logging configuration was found.", kind="absence"))
    # committed env and production configuration
    for f in files:
        if f.is_test:
            continue
        n = f.name
        if re.match(r"^\.env(\..+)?$", n) and not re.search(r"example|sample|template|dist|defaults?$", n):
            vals = [ln for ln in f.lines if re.match(r"^\s*[A-Z][A-Z0-9_]*(?:SECRET|PASSWORD|PASSWD|TOKEN|KEY|PRIVATE)[A-Z0-9_]*\s*=\s*\S{6,}", ln) and not PLACEHOLDER.search(ln)]
            if vals:
                out.append(Finding("env-file-committed", "R-CRED-SECRETS-MANAGER", "high", f"{f.rel} is committed and holds {len(vals)} secret-like value(s).", f.rel, 1, redact(vals[0])))
        if re.search(r"(?i)(?:^|[._/-])(?:prod|production)[._-](?:env|tfvars|secrets?|credentials?)|(?:env|secrets?)[._-](?:prod|production)\b", f.rel):
            out.append(Finding("prod-config-in-repo", "R-ENV-SEGREGATION", "medium", f"Production configuration is committed ({f.rel}).", f.rel, 1))
    out.extend(shared_secrets(files))
    return out


_ENV_WORDS = {"dev": ("dev", "development", "local"), "test": ("test", "testing", "qa", "uat"), "staging": ("stag", "staging", "preprod", "pre-prod"), "prod": ("prod", "production", "live")}
_KV = re.compile(r"""(?i)\b([\w-]*(?:password|secret|token|api[_-]?key|private[_-]?key|access[_-]?key)[\w-]*)["']?\s*[:=]\s*["']?([A-Za-z0-9/+=_\-.!@#$%^&*]{12,})["']?\s*,?\s*$""")


def _env_of(rel: str) -> str | None:
    parts = re.split(r"[/._-]+", rel.lower())
    for env, words in _ENV_WORDS.items():
        if any(w in parts for w in words):
            return env
    return None


def shared_secrets(files: list[SourceFile]) -> list[Finding]:
    seen: dict[str, list[tuple[str, int, str]]] = defaultdict(list)
    for f in files:
        if f.is_test or f.ext not in IAC | {".dockerfile"} | CODE:
            continue
        env = _env_of(f.rel)
        for i, ln in enumerate(f.lines):
            m = _KV.search(ln)
            if m and not PLACEHOLDER.search(ln) and LINE_IGNORE not in ln:
                seen[m.group(2)].append((f.rel, i + 1, env or "?"))
    out = []
    for _, locs in seen.items():
        envs = {e for _, _, e in locs if e != "?"}
        files_ = {r for r, _, _ in locs}
        if len(envs) >= 2 or (len(files_) >= 2 and len(envs) >= 1):
            r, ln, _ = locs[0]
            out.append(Finding("env-shared-secret", "R-CRED-UNIQUE", "high",
                               f"The same credential value appears in {len(files_)} files" + (f" across environments ({', '.join(sorted(envs))})" if envs else "") + ".",
                               r, ln, None, extra={"also_at": [f"{a}:{b}" for a, b, _ in locs[1:6]]}))
            out.append(Finding("env-shared-secret", "R-ENV-SEGREGATION", "high", "A credential is shared across files that belong to different environments.", r, ln, None))
    return out


# ---- precondition documents ------------------------------------------------------------------------------------------
def precondition_status(kb_pre: list[dict], files: list[SourceFile], all_paths: list[str], unread: list[str]) -> list[dict]:
    """For each authorisation precondition: where it appears to exist, by file name or heading."""
    out = []
    for p in kb_pre:
        terms = [t.strip() for t in p["looks_for"].split(",") if t.strip()]
        rx = re.compile("|".join(re.escape(t).replace(r"\ ", r"[\s_-]*") for t in terms), re.I)
        by_name = [x for x in all_paths if rx.search(x.rsplit("/", 1)[-1]) or rx.search(x)]
        by_heading = [f.rel for f in files if f.is_prose and not f.is_test and any(rx.search(ln) for ln in f.lines[:40] if ln.lstrip().startswith("#") or ln.isupper())]
        found = sorted(set(by_name + by_heading))
        out.append({"id": p["id"], "title": p["title"], "found": found[:5], "unread": [x for x in found if x in unread][:5]})
    return out
