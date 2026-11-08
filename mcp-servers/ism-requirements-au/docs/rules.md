# Rules, heuristics and preconditions

Generated from the knowledge base (release 2026.09). Each rule names the ISM controls it bears on, how directly the repository signal evidences them (**fidelity**), the lifecycle step at which it first matters (**phase**), and what a non-conforming repository looks like. Control text is never restated here: use `get_control`.

Fidelity: **direct** (the signal is the control's mechanism, so 'enforced by' is accurate), **partial** (evidences part of the control), **supporting** (helps an assessor, does not settle it).

## Rules

| Rule | Controls | Fidelity | Phase | Non-conformance looks like |
| --- | --- | --- | --- | --- |
| `R-ENV-SEGREGATION` Environments are segregated | ISM-0400, ISM-2143 | partial | implement | The same credential or production endpoint appears in development, test and production configuration, or production values are committed alongside development ones. |
| `R-SAST-SCA` Software artefacts are tested for known weaknesses | ISM-2028 | partial | implement | Continuous integration builds and ships the software without a SAST, DAST or software composition analysis step. |
| `R-TRUSTED-SOURCES` Third-party components come from trustworthy sources | ISM-2029 | supporting | implement | Dependencies are fetched from raw URLs, unpinned git branches or extra package indexes, or build steps pipe downloaded scripts to a shell. |
| `R-PINNED-DEPS` Dependencies are pinned to approved versions | ISM-2154 | direct | implement | Dependency manifests use ranges, wildcards or 'latest', base images use floating tags, or no lockfile is committed. |
| `R-SBOM-PRODUCE` A software bill of materials is produced | ISM-1730 | partial | implement | No SBOM generation step or SBOM artefact was found for software that is delivered to others. |
| `R-SBOM-USE` Third-party SBOMs are used during development | ISM-2054 | supporting | implement | Imported components are not checked against their SBOMs or known-vulnerability data during development. |
| `R-INPUT-VALIDATION` Input from the internet is validated and sanitised | ISM-1240, ISM-1851 | partial | implement | Request data reaches an interpreter (SQL, shell, eval) by string construction. |
| `R-UNSAFE-DESER` Serialised data is validated before deserialisation | ISM-2058 | partial | implement | Untrusted data is deserialised with a format that can execute code (pickle, yaml.load, Java object streams). |
| `R-OUTPUT-ENCODING` Web application output is encoded | ISM-1241 | partial | implement | Templates or components disable auto-escaping or write raw HTML (innerHTML, |safe, dangerouslySetInnerHTML). |
| `R-COOKIE-FLAGS` Session cookies set HttpOnly, Secure and SameSite | ISM-2063 | direct | implement | Session cookie configuration explicitly turns off HttpOnly, Secure or SameSite. |
| `R-SEC-HEADERS` Security policy response headers are set | ISM-1424 | partial | implement | A web application is present but no Content-Security-Policy, HSTS or X-Frame-Options configuration was found. |
| `R-HTTPS-ONLY` Web content is offered only over HTTPS | ISM-1552 | partial | implement | Configuration turns off HTTPS redirection or serves on plain HTTP. |
| `R-AI-MODEL-FORMAT` AI models are stored in non-executable formats | ISM-2072 | direct | implement | Model artefacts are pickle-based (.pkl, .pt, .joblib) or loaded with arbitrary-code-execution options. |
| `R-AI-DOCS` AI model and system cards document the AI application | ISM-2084 | partial | implement | The system uses AI models but no model card, system card or equivalent was found. |
| `R-AI-CONFIDENCE` Exact model confidence scores are not exposed | ISM-2085 | partial | implement | Log-probabilities or exact confidence values are returned through an API or user interface. |
| `R-AI-TRAINING-CONSENT` Organisational data is not used to train AI without consent | ISM-2103 | supporting | implement | Code or documents describe fine-tuning or training on data the system collects from its users. |
| `R-AI-AGENT-REGISTER` AI agents are registered | ISM-2134, ISM-2135 | partial | implement | The system defines AI agents but no register (identifier, owner, purpose, identities, tools) was found. |
| `R-AI-AGENT-LEAST-TOOLS` Agents are limited to the minimum tools and permissions | ISM-2156, ISM-2157 | partial | implement | An agent is given shell, arbitrary file or network tools with no human approval step or scoping. |
| `R-CRED-SHORT-LIVED` Workloads use short-lived, dynamically issued credentials | ISM-2141 | partial | implement | Long-lived static access keys, tokens or private keys are present in code or configuration. |
| `R-CRED-SECRETS-MANAGER` Static credentials are held in a secrets manager | ISM-2142 | partial | implement | Passwords, API keys or tokens are written into source, IaC or committed environment files. |
| `R-CRED-UNIQUE` Credentials are unique per application and environment | ISM-2143 | partial | implement | The same secret value is used in more than one environment or application. |
| `R-CRED-CLEAR` Credentials are not stored in the clear | ISM-1875, ISM-2144 | supporting | monitor | Credentials or private keys are readable in files; a credentials scan would find them. |
| `R-MFA` Multi-factor authentication is used | ISM-1504, ISM-1173, ISM-0974 | direct | implement | Identity provider or IaC configuration explicitly disables MFA. |
| `R-DEFAULT-CREDS` Default credentials are changed | ISM-1260, ISM-0383 | direct | implement | Service configuration ships a well-known default or placeholder credential (admin/admin, postgres/postgres, changeme). |
| `R-TLS-VERSION` Only the latest TLS version is used | ISM-1139 | direct | implement | Configuration permits SSLv3, TLS 1.0 or 1.1 (or a minimum below TLS 1.2). |
| `R-TLS-CIPHERS` TLS uses approved cipher and key-establishment settings | ISM-1369, ISM-1373, ISM-1553 | partial | implement | Configuration allows RC4, 3DES, CBC, NULL, EXPORT or anonymous suites, or enables TLS compression. |
| `R-INGRESS` Network traffic is limited to what the business requires | ISM-1182, ISM-1416 | partial | implement | Security groups, firewall rules or storage policies admit the whole internet to administrative, database or storage endpoints. |
| `R-LOG-CENTRAL` Event logs go to a centralised facility and are retained | ISM-1405, ISM-1983, ISM-1988 | supporting | implement | No log forwarding, central logging or retention configuration was found for a system that runs services. |
| `R-PATCH-AUTOMATION` Updates for vulnerabilities are applied promptly | ISM-1690, ISM-1876 | supporting | monitor | No dependency or image update automation was found. |

## Heuristics (common assessment gaps)

Raised as questions when their context applies; they cannot be settled from a repository.

| Heuristic | Controls | Phase | The concern |
| --- | --- | --- | --- |
| `H-IRP-EXERCISED` Incident response plan exists and has been exercised | ISM-0043, ISM-0140 | implement | An assessor asks for the plan and evidence that it has been exercised, and that reporting to ASD is understood. |
| `H-PATCH-EVIDENCE` A patching plan with evidence of operation | ISM-1143, ISM-1690, ISM-1876, ISM-1691 | implement | Patch timeframes in the ISM are specific; assessors look for the procedure and for records showing they were met. |
| `H-VULN-SCANNING` Vulnerability scanning with reviewed results | ISM-1702, ISM-2118 | assess | Scanning that nobody reads is not a control. Assessors ask for scan cadence and for what was done with results. |
| `H-MFA-REMOTE-ADMIN` MFA on remote and administrative access | ISM-1504, ISM-1173, ISM-0974 | implement | Absent or partial MFA on remote and privileged access is the first thing an assessor tests. |
| `H-ALERTS-WATCHED` Alerts from security tooling are actually watched | ISM-1228, ISM-1986, ISM-1987 | monitor | Tooling that generates alerts no one reads is a recurring assessment finding. |
| `H-FIREWALL-DEFAULT` Firewall and egress rules restrict by default | ISM-1182, ISM-1416 | implement | Rules that allow any-any, or no egress control, are read as no boundary control. |
| `H-CRED-STORAGE` Credentials are not kept in files or code | ISM-2142, ISM-1875, ISM-2144 | implement | Privileged passwords in files and scripts are a recurring failure; assessors ask how secrets are stored and scanned for. |
| `H-AI-AGENTS` AI agents have owners, permissions and tool scopes on record | ISM-2134, ISM-2135, ISM-2156, ISM-2157, ISM-2158 | implement | Agentic services act with the permissions they are given; assessors ask who owns each agent and what it can do. |
| `H-NONPROD-DATA` Production data and credentials stay out of non-production | ISM-0400, ISM-2143 | implement | Copies of production data, or shared credentials, in development weaken the segregation the ISM requires. |
| `H-SBOM-PROVENANCE` SBOM produced and consumed; dependency provenance known | ISM-1730, ISM-2054, ISM-2029, ISM-2154 | implement | Supply chain questions increasingly start with the SBOM and where components come from. |
| `H-DOCS-MATCH` Documentation matches the deployed system | ISM-0041, ISM-1163 | assess | An assessor checks that the security plan describes the system as it actually runs, including its boundary. |
| `H-SECURE-ADMIN` Administration is segregated and logged | ISM-1385, ISM-1750, ISM-0585 | implement | Administrative paths that share the general network, or leave no log, are read as uncontrolled privilege. |

## Authorisation preconditions

| Precondition | Controls | Phase | Applies to |
| --- | --- | --- | --- |
| `PRE-SSP` System security plan | ISM-0041 | implement | authorisation |
| `PRE-SSP-ANNEX` System security plan annex (controls matrix) | ISM-0041 | assess | authorisation |
| `PRE-IRP` Cyber security incident response plan | ISM-0043 | implement | authorisation |
| `PRE-CMP` Continuous monitoring plan | ISM-1163 | implement | authorisation |
| `PRE-SRMP` Security risk management plan | ISM-1526 | define | authorisation |
| `PRE-ATO` Authorisation to operate | ISM-0027 | authorise | authorisation |
| `PRE-REGISTER` Register entry for the authorised system | (PSPF) | authorise | pspf |
| `PRE-IRAP` IRAP report less than 24 months old | (PSPF) | assess | csp_or_gateway |

## Detectors

Each detector is a pattern over files git would track. A line carrying `ism-review: ignore` is skipped, and a file carrying `ism-review: ignore-file` is not read. Absence detectors (no SBOM step, no security headers, no log forwarding, no CI security testing) report confidence `low`.

| Detector | Rule |
| --- | --- |
| `agent-broad-tools` | `R-AI-AGENT-LEAST-TOOLS` |
| `agent-no-register` | `R-AI-AGENT-REGISTER` |
| `ai-confidence-exposed` | `R-AI-CONFIDENCE` |
| `ai-no-model-card` | `R-AI-DOCS` |
| `ai-training-on-user-data` | `R-AI-TRAINING-CONSENT` |
| `ci-no-security-testing` | `R-SAST-SCA` |
| `cookie-flags-off` | `R-COOKIE-FLAGS` |
| `default-credentials` | `R-DEFAULT-CREDS` |
| `env-file-committed` | `R-CRED-SECRETS-MANAGER` |
| `env-shared-secret` | `R-CRED-UNIQUE` |
| `env-shared-secret` | `R-ENV-SEGREGATION` |
| `https-not-enforced` | `R-HTTPS-ONLY` |
| `injection-sink` | `R-INPUT-VALIDATION` |
| `log-retention-short` | `R-LOG-CENTRAL` |
| `mfa-disabled` | `R-MFA` |
| `missing-lockfile` | `R-PINNED-DEPS` |
| `no-log-forwarding` | `R-LOG-CENTRAL` |
| `no-security-headers` | `R-SEC-HEADERS` |
| `no-update-automation` | `R-PATCH-AUTOMATION` |
| `open-ingress` | `R-INGRESS` |
| `output-encoding-off` | `R-OUTPUT-ENCODING` |
| `private-key-committed` | `R-CRED-CLEAR` |
| `prod-config-in-repo` | `R-ENV-SEGREGATION` |
| `public-storage` | `R-INGRESS` |
| `secret-literal` | `R-CRED-SECRETS-MANAGER` |
| `static-cloud-key` | `R-CRED-SHORT-LIVED` |
| `tls-old-version` | `R-TLS-VERSION` |
| `tls-weak-cipher` | `R-TLS-CIPHERS` |
| `unpinned-dependencies` | `R-PINNED-DEPS` |
| `unsafe-deserialisation` | `R-UNSAFE-DESER` |
| `unsafe-model-format` | `R-AI-MODEL-FORMAT` |
| `untrusted-source` | `R-TRUSTED-SOURCES` |
| `no-sbom` | `R-SBOM-PRODUCE` |
| `no-sbom` | `R-SBOM-USE` |
