# Sources and limits

This page says what the server knows, how current it is, and what it does not cover. `kb_status`
reports the same things at run time.

## What is in the knowledge base

The server ships a compiled, read-only knowledge base built on 7 November 2026. It holds:

- **22 rules and 18 heuristics**, with 131 citations. Every quotation was checked word for word against
  its source text when the knowledge base was built; a quote that cannot be found fails the build.
- **54 sources:** 10 pieces of legislation, 12 OAIC determinations, 7 court judgments, 7 tribunal
  decisions, 15 OAIC media releases, 2 OAIC guidance documents and 1 pleading.
- **The OAIC determinations register:** metadata for 101 privacy determinations, searchable with
  `search_kb`.
- **The APP text** from the current compilation, including APP 1.7–1.9 (automated decisions), which
  commence on 10 December 2026.

| Source | Version | Notes |
| --- | --- | --- |
| Privacy Act 1988 (Cth) | Compilation No. 104 (C2026C00227), in force 4 June to 10 December 2026 | A new compilation takes effect on 10 December 2026, when APP 1.7–1.9 commence. The shipped text is current until then. |
| Privacy and Other Legislation Amendment Act 2024 | As made | Source of APP 1.7–1.9 and the Schedule 2 statutory tort. |
| Privacy Regulations 2025; Agencies APP Code 2017; TFN Rule 2015 | Current at 7 November 2026 | |
| Digital ID Act 2024; SOCI Act 2018; TIA Act 1979; Cyber Security Act 2024 | Current at 7 November 2026 | Cited for specific points only (see below). |
| OAIC determinations, media releases and guidance | To November 2026 | |
| Court and tribunal decisions | Open Australian Legal Corpus v7.1.0 (to March 2025) | Nothing decided after March 2025 is in the case-law layer, apart from what the OAIC published. |
| NSW tribunal decisions (DMP, EQH, FQW, FMM, iCare v FMM, Stalvies) | Open Australian Legal Corpus v7.1.0 | NSW law, used only by analogy to APP 11. Short quotations only. |

## How to read an authority

Every citation carries its authority's status, and the output repeats it. Pay attention to these:

| Authority | Status |
| --- | --- |
| Bunnings [2024] AICmr 230 | Varied on review. The ART set aside the APP 3.3 finding (an exemption was available) but affirmed the APP 1 and APP 5 contraventions. |
| Bunnings [2026] ARTA 130 | Final at tribunal level. The full text was not retrievable; quotations come from the OAIC's statement and are marked secondary. |
| Kmart [2025] AICmr 155 | Reported in secondary sources as under ART review; not confirmed from a primary source. |
| IRE [2026] AICmr 24 | Under review in the ART. The OAIC says its positions drawn from it are not settled. |
| Australian Clinical Labs [2025] FCA 1224 | Final (first civil penalties). Full text not retrievable; quotations come from the OAIC's media release. |
| Medibank (VID497/2024) | Allegations only. Proceedings pending; nothing in it is a finding. |
| Facebook v Australian Information Commissioner [2022] FCAFC 9 | Interlocutory (prima facie case only). |
| ACCC v Google [2021] FCA 367 | Australian Consumer Law, not the Privacy Act. |

In total, 23 citations come from an OAIC summary rather than the decision itself. These are marked
`secondary`. Two heuristics have no decided authority behind them and are marked `confidence: low`:
MFA and privileged access, and the surveillance tort. Neither can raise a critical finding.

## What it does not cover

- **State and territory privacy law.** That includes the NSW, Victorian, Queensland and other public
  sector Acts, health records Acts that bind private providers in some states, and surveillance and
  listening device Acts. NSW tribunal decisions are cited only by analogy to APP 11.
- **Other Commonwealth regimes, except for specific points.** The SOCI Act is cited for the
  20,000-person "business critical data" line and its incident reporting periods; the Cyber Security
  Act for ransomware payment reporting; the TIA Act for s 187LA (retained data is personal
  information). Digital ID Act rules rest on the statute alone, with no decided authority yet. The
  Digital ID Rules and Accreditation Rules are not included.
- **Exemptions beyond the small business test.** Related bodies corporate, employee records and
  journalism are not assessed.
- **Decisions after March 2025**, unless the OAIC published them. There are no decisions yet under the
  Schedule 2 statutory tort (in force from 10 June 2025).

## What the scanner can and cannot see

- **Code** shows what a system can do, not what happens in production, what people were told, or what
  contracts say. The data inventory is a list of candidates to confirm.
- **Documents** are matched by phrase to point at passages. The scanner does not understand them.
  Facts come from observations that a person or assistant records, with their source.
- **PDFs, Word files and slides** are listed, not read.
- **Absence checks** such as "no retention mechanism" or "no breach runbook" only cover the repository.
  The thing may well exist elsewhere, so these are always cautions.
- **Decided-case matches** rest on the visible facts. The distinguishing facts, such as whether consent
  was obtained or whether matching was one-to-one, usually are not visible. Each critical finding
  lists them.

## How it was made

[RESEARCH.md](../RESEARCH.md) describes the sources, the method (Womblex, the Isaacus Kanon-2 models,
local analysis, hand-written entries, mechanical quotation checks), the technologies used, which parts
are judgement rather than data, and the planned work.
