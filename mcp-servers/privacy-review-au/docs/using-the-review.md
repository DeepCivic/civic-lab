# Using the review

`review_project` is the main tool. It reads what is available, ranks what it shows, and lists what is
still unknown. It needs no answers from anyone, so it can run before anyone has thought about privacy.

## Inputs

| Parameter | What to pass |
| --- | --- |
| `path` | The repository. Code, templates, schemas, infrastructure configuration and in-repo docs are scanned. `.gitignore` is honoured. |
| `documents` | Design, requirements or architecture documents, as files or folders, inside or outside the repository. Markdown, text and HTML are read. PDFs, Word files and slides are listed as unread. |
| `observations` | Facts recorded from anything else (see below). |
| `answers` | Optional `true`/`false` answers to threshold questions by id. Prefer observations, which carry their source. |
| `entity_type` | `agency` for Australian Government agencies, which have a mandatory PIA duty for high privacy risk projects. |
| `digital_id_role` | `accredited_entity` or `relying_party` if the project is part of the Australian Government Digital ID System. |
| `min_level` | The lowest finding level to return (default `caution`). The summary always counts every level. |

You can pass any one of `path`, `documents` and `observations`, or any combination.

## Output

| Field | What it holds |
| --- | --- |
| `headline` | One line: counts by level and open questions. |
| `findings` | Each finding has a `level`, message, location, the APPs and rules it bears on (`kb`), and `to_confirm` (the facts to check). Rule findings also list `exceptions_to_check`. Critical findings also carry a `precedent` with the decisions they resemble. |
| `gaps` | Open questions in priority order (see below). |
| `coverage` | What was examined: counts of code, markup, schema, infrastructure and document files, documents not read, and data files not parsed. |
| `threshold_readiness` | Where a threshold assessment would land on current evidence, and why. |
| `data_inventory` | Personal-information candidates from the code: fields by category, collection points, stores, recipients and overseas regions. |
| `report_markdown` | A readable version for a pull request comment or the team. |

## Levels

| Level | What gets there | What to do |
| --- | --- | --- |
| **critical** | The condition a decided case turned on is visible, and at least one of those decisions is final. For example, a pixel *in a health setting*, or faces matched *against a watchlist*. | Check the `to_confirm` questions. They are the facts that would distinguish your project from the case. |
| **high** | A rule-tier finding at high severity, with firm evidence. For example, world-readable storage, a government identifier as a primary key, or sensitive fields with no consent capture. | Check `exceptions_to_check`, then fix, or record why an exception applies. |
| **caution** | A heuristic with no matching final decision, a weak signal, something missing from the repository, or a passage in a document that needs reading. | Answer the `to_confirm` questions. Many cautions turn out to be fine. |
| info | Recorded for completeness. | |

Two things never make a finding critical. One is an authority that is under review, varied on review, or
only alleged. The other is a fact pattern whose deciding condition the scan cannot see. Both stay at high
or caution. The decided-case patterns are listed in [findings-reference.md](findings-reference.md).

## Open questions (gaps)

Each gap says:

- **why it matters**: which threshold factor or finding depends on it;
- **what would settle it**: the evidence to look for, and who usually holds it;
- **record as**: the observation kinds that answer it;
- **looked in**: what the scan examined.

Kinds of gap:

| Type | Raised when |
| --- | --- |
| `threshold_question` | A threshold question is still unknown, or documents mention it but nobody has confirmed it (`indicated`). |
| `distinguishing_facts` | A critical finding needs its facts checked against the case it resembles. |
| `regime` | Another Act may apply (Digital ID Act roles, the SOCI Act for large government data holdings). |
| `input` | Material was missing or unreadable: PDFs and Word files, no design documents, or no code. |

"Not detected" is only claimed about material that was examined. A review of documents alone reports
questions that code would usually answer as `unknown`, not as absent.

## Documents and observations

The scanner reads prose documents and flags passages that bear on privacy: scale, data sources,
overseas recipients, biometrics, automated decisions and others. A flagged passage is a **mention**,
not a fact. It raises a caution finding of type `document-mention` and marks the question `indicated`
until someone reads the passage. Mentions skip negated phrases ("we do not send data overseas") and
privacy policies, which have their own checks.

An observation records a fact, with where it came from:

```json
[
  {"kind": "facial_recognition_identification", "fact": "Cameras match visitors against a banned-customer watchlist",
   "source": "docs/solution-design.md:2"},
  {"kind": "large_scale", "fact": "About 2 million customers", "source": "business case p 4"},
  {"kind": "overseas_disclosure", "fact": "All hosting and support is in Australia", "source": "team", "present": false}
]
```

- `fact` is required: say what the material shows, in a sentence.
- `source` should let someone find it again: a file and line, a document and page, or "team".
- `present: false` records that something is confirmed absent, and answers the question "no".

An observation answers its threshold question, links the rules and heuristics, and can match a
decided-case pattern, exactly as a detector hit does. A team answer in `answers` takes precedence over
observations, observations over code evidence, and code over document mentions. If a "no" conflicts with
code evidence, the record flags the conflict.

### Observation kinds

`list_observation_kinds` (or `privacy-review-au kinds`) gives the full descriptions and
what to look for.

| Kind | Label | Answers | Level when present |
| --- | --- | --- | --- |
| `personal_information` | Personal information handled | handles_personal_information | (no finding) |
| `new_or_changed_handling` | New or changed handling | new_or_changed_handling | (no finding) |
| `sensitive_information` | Sensitive information | sensitive_information | caution |
| `biometric_processing` | Biometrics or facial recognition | biometrics_or_surveillance | caution |
| `facial_recognition_identification` | Facial recognition used to identify people | biometrics_or_surveillance | critical |
| `surveillance_monitoring` | Monitoring of people | biometrics_or_surveillance | caution |
| `automated_decision` | Automated decisions about people | automated_decisions | caution |
| `vulnerable_individuals` | Children or people who may be vulnerable | vulnerable_individuals | (no finding) |
| `large_scale` | Large scale | large_scale | (no finding) |
| `data_matching` | Data matching, linkage or profiling | data_matching_or_linkage | caution |
| `indirect_collection` | Collection from someone other than the individual | indirect_collection | caution |
| `scraping_public_data` | Scraping personal information from public sources | indirect_collection | critical |
| `digital_id` | Australian Government Digital ID System | digital_id_system | (no finding) |
| `tracking` | Online tracking or location tracking | tracking_and_profiling | caution |
| `tracking_pixel_sensitive` | Advertising pixels in a sensitive setting | tracking_and_profiling | critical |
| `government_identifier` | Government related identifiers | government_identifiers | caution |
| `government_identifier_as_key` | Government identifier used as the organisation's own identifier | government_identifiers | high |
| `overseas_disclosure` | Storage, processing or disclosure overseas | overseas_disclosure | caution |
| `third_party_disclosure` | Disclosure to other organisations | third_party_disclosure | caution |
| `secondary_use` | Use for another purpose | secondary_use | caution |
| `security_weakness` | Known security weakness | security_weaknesses | caution |
| `public_storage` | Personal information in publicly accessible storage | security_weaknesses | high |
| `community_concern` | Likely community or media concern | community_expectations | (no finding) |
| `real_data_in_non_production` | Real personal information in non-production environments | (none) | critical |
| `bundled_consent` | Bundled or pre-ticked consent | (none) | critical |
| `hedged_biometric_notice` | Notice says biometric collection only 'may' occur | (none) | critical |
| `no_collection_notice` | No collection notice | (none) | high |
| `no_privacy_policy` | No privacy policy covering the system | (none) | high |
| `retention_undefined` | No retention or destruction arrangements | (none) | caution |

"(no finding)" kinds answer a threshold question but are not issues in themselves. A "critical" kind is
critical only while the decisions behind its pattern remain final. Some findings bear on APP 1.7, which
commences on 10 December 2026; until then they are reported at caution.

## Interrogate

`interrogate(topic, ...)` explains one thing, using the same evidence as the review. Pass the same
`path`, `documents` and `observations`, because finding ids depend on them.

| Topic | Returns |
| --- | --- |
| A finding id (`F003`) | The finding, its rules and heuristics in full, the threshold questions it bears on, and its gaps. |
| A threshold question (`large_scale`) | The current answer and basis, evidence for and against, document passages, related findings, what was examined, and what would settle it. |
| An observation kind (`data_matching`) | What to look for, the observations recorded, related findings, and the decided-case pattern if any. |
| A rule or heuristic (`H-FRT-PROPORTIONALITY`) | The entry, findings that cite it, and the decided-case patterns built on it. |

## In CI

```bash
privacy-review-au review . --doc docs --out privacy-review.md --fail-on high
```

The command exits 1 when any finding is at or above `--fail-on` (`critical`, `high`, `caution` or
`never`). `--observations obs.json` lets a team keep its recorded facts in the repository next to the
code they describe.

To silence a finding you have checked, put `privacy-review: ignore` on the line, or
`privacy-review: ignore-file` anywhere in a file. Say why in the same comment.
