# How the knowledge base was made

## Layers

`src/ism_requirements_au/data/kb.json` is compiled once from a private research corpus and shipped read-only.

| Layer | Content | Source |
| --- | --- | --- |
| Controls | 1,143 controls and 49 principles: statement (verbatim), revision, update month, applicability at each classification, Essential Eight maturity levels | ASD ISM OSCAL catalog and resolved baseline profiles, v2026.09.4 |
| Essentials | 58 enterprise IT actions with principle, domains and 113 cross-referenced controls | ASD Essentials and its assessment workbook |
| Obligations | PSPF Release 2026 sections 13 to 15 and Direction 002-2026, as paraphrase with short verified quotations | Department of Home Affairs |
| Preconditions | The documents and records authorisation depends on | ISM, PSPF |
| Rules, heuristics | Authored by DeepCivic: the requirement (verbatim control), what non-conformance looks like in a repository, fidelity, phase, remediation | the layers above |
| Guidance | Short anchored quotations on how to implement | ASD (CC BY 4.0), NIST (public domain); OWASP by reference only |

## Method

- Control text is never retyped. The build copies it from OSCAL and fails if a rule names a control that does not exist.
- The per-classification applicability tags on each control are cross-checked against ASD's resolved baseline profile
  catalogs; the build fails if they disagree.
- Every quotation records the sha256 of its source passage and its start and end offsets; the build fails if the quotation is
  not a literal substring of the passage. Quotations that merely reproduce ISM text are excluded.
- Rule selection favoured areas where a repository can show evidence, where little existing assessment tooling reaches
  (software development, AI application development, credentials, TLS), and where guidance is strong. Priority and wording
  were informed by published enforcement outcomes and ASD reporting; those sources are not reproduced here.
- Each rule has a lifecycle `phase` from the ISM's six-step risk management framework, so a team in the implement step is
  not told about assessment logistics.

## Known limits

- **Not an assessment.** Static analysis of one directory. Absence findings (confidence low) mean "not found here".
- **Requirement numbers.** PSPF requirements are cited by section. Only requirement 0098 is given by number, because its source
  states it; the others need re-keying from the PDF before they can be cited.
- **Guidance coverage.** A small number of anchored quotations were selected by relevance scoring, with sentence filters; they are not
  curated control by control, and some rules have none. Treat them as pointers to the source.
- **Essential Eight strategy.** The OSCAL data gives maturity level but not strategy name; strategy is carried only on the rules
  where it was authored.
- **One release.** Only the current ISM release is bundled. `diff_release` lists controls updated in it; `track_impact` compares
  a manifest's pinned hashes against it.
- **Quarterly refresh.** The ISM is released quarterly. A new OSCAL release means rebuilding the controls layer, diffing it and
  reviewing rules whose controls changed. The Essentials transition changes the obligation layer, not the rules.
- **Excluded.** ANAO material and court proceedings are not used. AESCSF practice identifiers appear in the crosswalk only.
