# Findings reference

## Decided-case patterns (critical)

A finding is critical only through one of these patterns. Two conditions must both hold:

- the condition the decisions turned on is visible in the evidence, or was recorded as an observation;
- at least one of the decisions is a final determination, judgment or tribunal decision. Media
  releases, allegations, and decisions under review or varied on review never count.

| Pattern | Decisions it rests on | Raised when | Related authorities shown |
| --- | --- | --- | --- |
| `P-FRT-IDENTIFICATION`: facial recognition used to identify people | 7-Eleven [2021] AICmr 50; Clearview AI [2021] AICmr 54 | Biometric code that searches or indexes faces, or uses a watchlist or gallery; or observation `facial_recognition_identification` | Kmart [2025] AICmr 155 (reported as under ART review); Bunnings [2024] AICmr 230 (varied on review); Bunnings [2026] ARTA 130 (the exemption was available on Bunnings' facts) |
| `P-PIXEL-SENSITIVE`: advertising pixels in a sensitive setting | Monash IVF [2026] AICmr 40; Medmate [2026] AICmr 41 | An ad or conversion pixel in a repository that describes a health or other sensitive setting; or observation `tracking_pixel_sensitive` | |
| `P-SCRAPING`: scraping personal information from public sources | Clearview AI [2021] AICmr 54 | Scraper code alongside social-media or profile targets; or observation `scraping_public_data` | |
| `P-REAL-DATA-NONPROD`: real identity or financial data outside production | Flight Centre [2020] AICmr 57 | Checksum-valid card, TFN or Medicare numbers in test or fixture data; or observation `real_data_in_non_production` | DMP v Sydney Local Health District [2021] NSWCATAD 246 (no breach where safeguards around a production copy were reasonable; NSW law) |
| `P-HEDGED-NOTICE`: notice that facial recognition only "may" be used | Bunnings [2026] ARTA 130 | Notice or policy text saying biometrics "may" be used; or observation `hedged_biometric_notice` | Bunnings [2024] AICmr 230 |
| `P-BUNDLED-CONSENT`: consent bundled into agreeing to terms or a policy | Flight Centre [2020] AICmr 57 | "I agree to the Terms ... Privacy Policy ... marketing" style consent; or observation `bundled_consent` | 7-Eleven [2021] AICmr 50 (implied consent fails on ambiguity) |

The full text of Bunnings [2026] ARTA 130 could not be retrieved. Its quotations come from the OAIC's
statement on the decision and are marked as secondary. Biometric code that only *verifies* an enrolled
user (one-to-one) does not match `P-FRT-IDENTIFICATION`. If it has no consent capture it is high under
APP 3.3; otherwise it is caution.

Each match lists the decisions with their status, the related authorities, and the facts that would
distinguish your project (`to_confirm`). A match says the visible facts look like a case that was lost.
It is not a finding that the law was contravened.

## Rules and heuristics

Every finding links to entries in the knowledge base. There are 22 rules and 18 heuristics, with 131
verified citations.

| Tier | What it is | Examples |
| --- | --- | --- |
| **Rule** | A requirement that is contravened if the facts are as they appear. A finding links to a rule only when the condition the rule turns on is visible: a tracking pixel engages APP 3.3 only once the repository shows a sensitive setting. | No privacy policy (APP 1.3); government identifier used as a primary key (APP 9.1); world-readable storage (APP 11.1) |
| **Heuristic** | An area of concern inferred from what decision-makers found, with the reasoning, the status of each authority, and the questions to answer before concluding anything. | Facial recognition on the public; tracking pixels on health sites; real data in test fixtures |

`get_entry` returns an entry in full: requirement or concern, exceptions, remediation, and each
citation with its pinpoint, quote and the status of the authority.

Five rules come from the **Digital ID Act 2024**: biometrics need express consent, no tracking of
service use, prohibited attributes, limits on unique identifiers, and voluntary use. They bind only
accredited entities and participating relying parties, so findings link to them only when you pass
`digital_id_role`. The scanner reports references to the Digital ID System (myID, `myid.gov.au` hosts)
as evidence, but never infers the role.

## What the scanner detects

- **Pixels and tracking:** ad and conversion pixels (Meta, TikTok, LinkedIn, Google Ads and others),
  escalated in a health or other sensitive setting; session replay; hashed-identifier matching; SDK
  auto-collection switched on.
- **Biometrics and collection:** facial recognition and biometric templates; scraping; device location;
  camera, microphone, screen and keystroke capture; sensitive-information fields without consent
  capture; excessive fields; pre-ticked or bundled consent; "may use facial recognition" notices.
- **Security (APP 11):** public buckets and databases in infrastructure code; MFA switched off; wildcard
  IAM; weak password hashing; committed secrets; disabled TLS verification; plain-HTTP endpoints;
  personal information in logs; suppressed security findings.
- **Identifiers:** government identifiers used as keys; TFN handling.
- **Overseas processing:** non-Australian cloud regions; overseas SaaS and AI APIs.
- **Marketing:** marketing templates without an unsubscribe.
- **Governance and policy:** automated decisions (APP 1.7, from 10 December 2026); real personal data in
  fixtures; committed data dumps; missing retention, breach-response, audit-logging or PIA material;
  privacy policies that are missing, omit APP 1.4 matters, or omit capabilities the code uses.
- **Documents:** passages about scale, data sources, recipients, biometrics, automated decisions,
  vulnerable people, new or changed handling and similar. These are reported as mentions to read, not
  as facts.

## Staying quiet

A review is only useful if a team can read it. The scanner:

- honours `.gitignore` inside a git work tree, and skips build output (`dist`, `.next`, `.vercel`,
  `cdk.out` and others) and minified bundles, even when committed;
- treats plain data JSON as data, not as infrastructure code or a schema;
- matches sensitive terms only where they appear as fields (`diagnosis TEXT`, `religion:`,
  `name="ethnicity"`), not in prose or in identifiers such as `diagnostics`;
- groups findings by cause: a pixel snippet over three lines is one finding, and a file copied into two
  folders is one finding with its other location listed;
- works out whether the code is an application or a library. It skips the "no privacy policy", "no
  retention" and "no breach runbook" checks for libraries and for code with no personal information;
- lowers the severity of credentials found in test files;
- counts SaaS SDKs found in code once, not as both "third party" and "overseas". On their own they never
  recommend a PIA.

To silence a finding, put `privacy-review: ignore` on the line, or `privacy-review: ignore-file`
anywhere in a file.
