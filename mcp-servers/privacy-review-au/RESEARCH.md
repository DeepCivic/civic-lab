# Research: what is in this server and how it was made

This server makes legal claims, so you should be able to see where they come from. This document
covers four things: what the knowledge base contains, the sources it draws on, how it was built and
checked, and the technologies used. It also says which parts are judgement rather than data.

## What it contains

The server ships one compiled, read-only knowledge base, `src/privacy_review_au/data/kb.json`, built
on 7 November 2026. Nothing is fetched at run time.

| Part | Count | What each holds |
| --- | --- | --- |
| Rules | 22 | A requirement and what a contravention looks like, the signals that suggest it, exceptions, remediation, enforcement, when it commenced, and citations. |
| Heuristics | 18 | A concern inferred from decided cases, with the reasoning, signals, questions to answer before concluding anything, remediation, confidence, and citations. Two have no decided authority and say so (`confidence: low`, with an `evidence_gap`). |
| Citations | 131 | The source, pinpoint, the proposition it supports, the exact quotation, and an anchor to where the quotation sits in the source text. |
| Sources | 54 | Legislation, OAIC determinations, court and tribunal decisions, OAIC media releases and guidance, and one pleading. Each has its citation, status (final, varied, under review, allegations only), licence and provenance (URL, retrieval time, and a hash of the text used). |
| APP text | APPs 1–13 | Verbatim from Privacy Act Compilation No. 104, including APP 1.7–1.9, which commence on 10 December 2026. |
| OAIC determinations register | 101 | Metadata (title, provisions, catchwords, link) for searching. |
| Applicability | | Citations for whether the APPs bind an entity: the small business exemption, the s 6D(4) exceptions, agencies, and the Digital ID Act layer. |

`get_entry`, `get_authority`, `get_app` and `kb_status` return all of this.

### How to check a citation yourself

Each citation carries an `anchor`: a `source_hash` (the SHA-256 of the source record's id and text) and
the character `start` and `end` of the quotation in that text. Each source's provenance gives the URL it
came from and when it was retrieved. Open the URL, find the pinpoint, and the quotation is there word
for word. The only differences are normalised quotation marks, dashes and spaces.

Where the decision itself could not be retrieved, the quotation comes from the OAIC's published summary
or statement. Those citations are marked `secondary` and name the document quoted. There are 23 of them.

## Sources and their currency

As at 7 November 2026.

| Source | Version | How it was obtained |
| --- | --- | --- |
| Privacy Act 1988 (Cth) | Compilation No. 104 (C2026C00227), in force 4 June to 10 December 2026 | Federal Register of Legislation API |
| Privacy and Other Legislation Amendment Act 2024 | As made. APP 1.7–1.9 commence 10 December 2026 | Federal Register of Legislation API |
| Privacy Regulations 2025; Agencies APP Code 2017; TFN Rule 2015 | Current | Federal Register of Legislation API |
| Digital ID Act 2024; SOCI Act 2018; TIA Act 1979; Cyber Security Act 2024 | Current compilations | Federal Register of Legislation API |
| Court and tribunal decisions | Open Australian Legal Corpus v7.1.0 (collected March 2025) | Isaacus, via Hugging Face |
| OAIC determinations register | 101 privacy determinations to June 2026 | OAIC website |
| OAIC determinations, full text | Clearview, 7-Eleven, IRE, Optus | PDFs from the OAIC website |
| OAIC media releases and guidance | 23 documents to November 2026 | OAIC website |
| [2025] FCA 1224 (Australian Clinical Labs); [2026] ARTA 130 (Bunnings) | Full text not retrievable | Quoted from OAIC statements, marked `secondary` |
| NSW tribunal decisions (DMP, EQH, FQW, FMM, iCare v FMM, Stalvies); PPIP Act 1998 (NSW) | Open Australian Legal Corpus v7.1.0 | Cited only by analogy to APP 11; short quotations only |

The Open Australian Legal Corpus has not been re-released since March 2025, so decisions after that
date are included only where the OAIC published them.

## How it was built

```
1. Collect     legislation (FRL API), the Open Australian Legal Corpus, OAIC publications and PDFs
2. Structure   Womblex: records and PDFs become ordered elements (paragraphs, headings, footers, page numbers)
3. Enrich      Kanon-2 Enricher: each document's citations to statutes, provisions and cases, as structured data
4. Chunk/embed semchunk and the Kanon-2 Embedder: passages and their vectors
5. Analyse     locally: which provisions the case law engages, how later decisions treated each authority,
               and which passages sit near or far from each heuristic
6. Write       rules and heuristics written from reading the decisions; the analysis suggests, it does not decide
7. Compile     every quotation found verbatim in its source and anchored; the build fails otherwise
```

**1. Collect.** Legislation comes from the Federal Register of Legislation API: the current compilation
and the amending Acts. Case law comes from the Open Australian Legal Corpus. The cohort was every record
that cites Commonwealth privacy law, plus state privacy and surveillance legislation and state decisions
that bear on technology. OAIC determinations, media releases and guidance come from the OAIC website.

**2. Structure.** [Womblex](https://github.com/DeepCivic/womblex) turns each record and PDF into ordered
elements with page numbers. This is what lets the build check that a quotation sits in the paragraph its
pinpoint names. Flat text extraction put page numbers and footnotes in the way; one 7-Eleven quotation
at [6] read as [3]. Each record gets a stable address: `source_hash = sha256(id + text)`.

**3–4. Enrich, chunk and embed.** The evidence set was 858 documents: 853 records and 5 PDFs.
- The Isaacus **Kanon-2 Enricher** produced, for each document, its citations to statutes and provisions
  and the cases it relies on, with how it treats them (positive, negative, mixed or neutral).
- **semchunk** split the text into about 40,000 passages.
- The **Kanon-2 Embedder** produced a vector for each passage.
- An offline graph step linked each citation to the passage it appears in.

These were the only steps that called a paid service. Each run was sized first with the open-source
Kanon-2 tokeniser and started only after approval.

**5. Analyse.** This step ran locally, with network access blocked. It found:
- which provisions the case law actually engages that the knowledge base does not yet cover: 770 relevant
  documents and 479 provisions across 17 statutes;
- whether later decisions followed or distinguished each authority the knowledge base relies on;
- for each heuristic, the passages in other decisions closest to its anchored passages (candidate
  supporting or contrary authority);
- technology-related passages far from every heuristic, clustered as candidate new concerns.

**6. Write.** The rules and heuristics were written from those leads and from reading the decisions
themselves. The pipeline does not generate entries. The authoring rules are:
- a rule must cite the legislative text it applies;
- a heuristic must cite at least one decided authority, or declare an evidence gap and low confidence;
- quote only text that appears in the source, preferring the decision itself to a summary;
- record each authority's status (on review, varied, under appeal, allegations only).

**7. Compile and verify.** A build script compiles the authored entries into `kb.json`. It normalises
quotation marks, dashes and spaces, finds every quotation verbatim in its source text, records the
anchor, and checks paragraph pinpoints against the Womblex elements. Any quotation it cannot find
fails the build. This package's tests (`tests/test_kb.py`) check the compiled result: every citation
verified, every heuristic backed or flagged, and nothing quoted that may not be redistributed.

## What is judgement, not data

These parts are written by hand in the server code. They are reasoned choices, not outputs of the
pipeline, and they are worth reviewing before you rely on them:

- **The levels** (`src/privacy_review_au/review.py`): when a finding is critical, high or caution.
- **The decided-case patterns** (`src/privacy_review_au/precedents.py`): which decisions a finding is
  matched to, the condition that must be visible, and the one-sentence fact patterns. A pattern counts
  only when its decision is final, and that check is made at run time from the source's recorded status.
- **The observation kinds and document phrases** (`src/privacy_review_au/observations.py`): what facts can
  be recorded, and which phrases mark a passage as worth reading.
- **The detectors** (`src/privacy_review_au/scan/detectors.py`): the code patterns, and the severity each
  is given.
- **The threshold questions and outcome logic** (`src/privacy_review_au/threshold.py`).

## Technologies

| Technology | Used for | Licence or terms |
| --- | --- | --- |
| [Womblex](https://github.com/DeepCivic/womblex) (DeepCivic) | Document structure, PDF extraction, pipeline orchestration | Apache-2.0 |
| Isaacus Kanon-2 Enricher | Structured citations and their treatment in each decision | Paid API |
| Isaacus Kanon-2 Embedder | Passage vectors for the analysis | Paid API |
| Isaacus Kanon-2 tokeniser | Exact token counts for sizing runs before approval | Open source, local |
| semchunk | Splitting documents into passages | MIT |
| [Open Australian Legal Corpus](https://huggingface.co/datasets/isaacus/open-australian-legal-corpus) v7.1.0 (Isaacus) | Court, tribunal and legislation texts | CC BY 4.0 as a collection; each document keeps its own terms |
| Federal Register of Legislation API | Current Commonwealth legislation | CC BY 4.0 |
| pyarrow | Local analysis over the stored shards | Apache-2.0 |
| [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk), httpx | The server, and the opt-in live probe | MIT, BSD-3-Clause |

The server itself uses only the MCP SDK, httpx (for the opt-in live probe) and the Python standard
library. The Isaacus models are used only to build the knowledge base, never when the server runs.

## What is not in this repository

The working files that built the knowledge base are not in this repository. That covers the fetched
source texts, the Womblex evidence set, the enrichment and embedding outputs, the analysis outputs, the
authoring files and the build scripts. They are kept by the maintainer, for three reasons:

- **Licence.** Some source texts may not be redistributed. The High Court judgment is quoted briefly only,
  and NSW Caselaw's terms ask that decisions be kept out of search-engine indexing, so full NSW decisions
  are not republished.
- **Size.** The evidence set is around 300 MB.
- **Purpose.** They are working material, not something a user needs.

Everything the server relies on is in `kb.json`, with enough provenance to check each quotation against
its public source. See [NOTICE](NOTICE) for the terms of the quoted material, and
[docs/sources-and-limits.md](docs/sources-and-limits.md) for what the knowledge base does not cover.

## Planned work

- A state and territory layer, starting with NSW and the surveillance and listening device Acts.
- Primary text for the citations that are now secondary, from the OAIC-hosted determinations.
- Detectors for production snapshots copied into non-production, shared credentials, and bulk email
  attachments containing personal information.
