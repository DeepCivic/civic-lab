---
name: au-gov-formal-writing
description: >
  Draft or review formal Australian Government content in line with the
  Australian Government Style Manual. Applies formal tone,
  plain language, precise obligation wording, defined terms, and numbered
  structure for content that must be read exactly as written.
  Returns a polished draft and a completed quality checklist.
---

# AU Government Formal Writing

**What this skill does:**
- Draft or review formal government content: documents that set out obligations, conditions, requirements, rules or official positions, where readers need to rely on the exact wording.
- Apply the Style Manual's **formal tone** while keeping plain language, accessibility and inclusive language intact. The Style Manual is explicit: *formality does not affect plain language*.
- Always output the final draft together with a filled-in "Before Finalising" checklist.

**What this skill does NOT do:**
- Provide legal advice, legal drafting or policy content (the user supplies facts, obligations and intent).
- Replace agency templates, clause libraries or legal review.
- Write routine emails, letters or internal reports in standard tone – use `au-gov-email-letter` or `au-gov-report` for those.
- Build final layouts, branding or templates.

---

## Process

### Step 1: Receive the brief
Ask only for what's missing:
- Document type and purpose
- Audience (internal, external, both) and their relationship to the agency
- Who has obligations under the document (the agency, the reader, a third party)
- Any agency template, mandated wording or clause structure that must be kept
- Key content points, obligations and dates
- Security classification or dissemination limiting marker, if any

If the user supplies existing text, treat it as a review: keep mandated wording unless the user approves a change.

### Step 2: Build structure and draft
1. **Construct the structure**
   Use the **Writing Standards** below. If no template is supplied, present the outline (numbered headings only) for a quick yes/no before drafting. Skip this if the user wants speed or has already signed off.

2. **Draft or revise the content**
   Write each section in formal tone and plain language. Use the user's points to populate the structure. When reviewing, list each deviation with its Style Manual reference and a suggested rewrite.

### Step 3: Quality check
Run the **Agent QA Checklist** internally. Fix every issue.
If the `australian-writing-mcp` tools are available, run `check_spelling`, `check_grammar` and `get_reading_level` on the draft and resolve findings before returning it.
Return the final draft, followed by the completed checklist and a short list of any open questions (ambiguous obligations, undefined terms, missing facts).

---

## Writing Standards

All rules below follow the Australian Government Style Manual unless marked **(convention)**. Where an agency style guide or mandated template conflicts with this skill, the agency guidance wins – flag the conflict to the user.

### Tone and voice

**Formal tone:**
- No contractions (*do not*, *will not*, *it is*).
- Literal – words carry their dictionary meaning.
- No metaphor, slang or idioms.
- Often uses the third person. Refer to parties by role or defined name (*the Department*, *the Applicant*, *they*).

**Voice:** institutional – the voice of a definitive source. Respectful, clear and direct, objective and impartial.
- State facts, not opinion. Remove evaluative adjectives and adverbs (*robust*, *world-class*, *simply*, *clearly*) unless they are defined or measurable.
- Use *we* and *you* only if the document has defined them, or the agency template uses them. Otherwise use defined role names consistently. Never use *I* except in signed correspondence.
- Formal does not mean wordy or archaic. Avoid legalese: *hereby*, *herein*, *thereof*, *whereby*, *aforementioned*, *the said*, *in lieu of*, *prior to*, *pursuant to* (prefer *under*), *in the event that* (prefer *if*).

### Plain language
- Everyday words: *use* not *utilise*, *start* not *commence*, *end* not *terminate* (unless *terminate* is a defined act), *help* not *facilitate*, *about* not *in relation to*.
- Sentences average 15 words, never more than 25. Break long conditions into lists.
- **Active voice** – it shows who must do what. *The Supplier must give notice within 10 business days*, not *Notice must be given within 10 business days*.
- One idea per sentence. Write positive sentences; no double negatives.
- Write exactly what you mean – no ambiguity. Remove words that do no work.
- Expand every acronym on first use; avoid acronyms the reader is unlikely to know.

### Obligation and permission wording (convention)
The Style Manual lists modal verbs but does not set a drafting convention. Use this one, consistent with Australian plain-language drafting practice, and state it in the document if readers need it:

| Word | Meaning | Use for |
| --- | --- | --- |
| **must** | mandatory | obligations and requirements |
| **must not** | prohibited | prohibitions |
| **should** | expected but not mandatory | recommendations and preferred practice |
| **may** | permitted, optional | discretions and permissions |
| **will** | statement of future fact or intent | what the agency or a process will do |

- **Do not use *shall*.** It is ambiguous (obligation, future or permission). Replace with *must* or *will*.
- Never mix *must* and *should* for the same level of obligation.
- Avoid *may not* – it can mean "is not permitted" or "might not". Use *must not* or *might not*.
- Avoid *and/or* – write *A or B, or both*.
- Every obligation needs a clear subject (who), action (what) and, where relevant, time and standard (when, how well).

### Defined terms (convention, applying Style Manual word-choice principles)
- Define a term only if it is used more than once or has a specific meaning in the document.
- Define it once – in a definitions section or on first use – and capitalise it consistently if the agency convention is to do so (*the Department*, *Business Day*).
- Once defined, use the exact term every time. Do not swap in synonyms (*Supplier* / *Vendor* / *Contractor*) – in formal content a different word implies a different meaning.
- Do not define common words with their ordinary meaning.
- Order the definitions list alphabetically.

### Structure
- Headings start with keywords, are descriptive and use sentence case. Do not skip heading levels. Use no more than 4 levels.
- Use decimal numbering (1, 1.1, 1.1.1) for sections and clauses that readers will cite or cross-reference **(convention)**. Do not go deeper than 3 numbered levels; restructure instead.
- Cross-reference by number and heading: *see section 4.2 (Reporting)*. Check every cross-reference after edits **(convention)**.
- One topic per paragraph. Put the main point first.
- Typical order for a formal document (adapt to type and any template) **(convention)**:
  1. Title, version, date, owner and classification (if any)
  2. Purpose and scope (what the document covers and does not cover)
  3. Definitions and interpretation
  4. Main content in numbered sections
  5. Responsibilities or obligations, if not covered above
  6. Attachments or schedules (Attachment A, B, C…)
  7. Document control (version history, approvals), if required

### Lists
- Every list has a lead-in that makes sense on its own or with each item.
- Keep items grammatically parallel.
- Fragment items: lower case, no punctuation, full stop after the last item only.
- Full-sentence items: capital letter and full stop on each.
- Use numbered lists where order matters or items will be cited (*criterion 3*).
- Say whether items are cumulative or alternatives: *all of the following* or *one of the following* **(convention)**.

### Numbers, dates and money
- Numerals for 2 and above; *zero* and *one* in words.
- Dates: *16 October 2026* (no ordinals, no leading zero). Day and date together: *Friday 16 October 2026*.
- Times: include the time zone where readers may be in different zones (*2 pm AEDT*).
- State deadlines unambiguously: *by 2 pm AEDT on Friday 16 October 2026*. Say whether periods are calendar days or business days **(convention)**.
- Currency: *$1,500*; say whether amounts include GST where relevant **(convention)**.
- Do not repeat numbers in words and numerals (*ten (10)*) **(convention)**.

### Inclusive and accessible content
- Use *they/them* for an unspecified person – never *he/she* or *he or she*.
- Describe only characteristics that are relevant.
- Content must be usable by people with disability (*Disability Discrimination Act 1992*). Aim for WCAG 2.2 AA.
- Use real headings, real lists and accessible tables (header rows, no merged cells, no empty cells used for layout) – not manual formatting.

### Referencing legislation and other material
- Cite Acts in italics with year on first mention: *Public Governance, Performance and Accountability Act 2013*. Shorten consistently afterwards (*PGPA Act*).
- Cite sections as *section 15* in text, *s 15* in notes and tables.
- Reference other sources using the Style Manual author–date system, or the agency's preferred system if it has one.

### Spelling and conventions
- Australian English spelling (Macquarie Dictionary as the reference).
- Sentence case for headings and titles.
- Single quotation marks for quotes; double inside single.

---

## Agent QA Checklist
- ☐ No contractions, idioms, metaphors or slang?
- ☐ No legalese or archaic terms (*hereby*, *herein*, *pursuant to*, *shall*)?
- ☐ Average sentence length ≈15 words, none over 25?
- ☐ Active voice throughout – every obligation has a clear subject?
- ☐ *must / must not / should / may / will* used consistently and correctly?
- ☐ No *may not* or *and/or*?
- ☐ Every defined term defined once and used identically throughout?
- ☐ Acronyms expanded on first use?
- ☐ Headings descriptive, sentence case, no skipped levels, max 4 levels?
- ☐ Numbering and every cross-reference correct?
- ☐ Lists have lead-ins, parallel items, correct punctuation, and say *all* or *one of*?
- ☐ Dates, times, time zones, deadlines and amounts unambiguous?
- ☐ Inclusive language (*they/them*) applied?
- ☐ No opinion or unsupported evaluative language?
- ☐ Security classification marked (if required)?
- ☐ Australian English spellcheck done?

---

## Guardrails
- Never alter the user's facts, obligations, dates, amounts or policy position. If plain-language rewording could change the meaning of an obligation, show the original and the proposed wording and let the user decide.
- Keep mandated or legally settled wording unchanged unless the user approves – flag any Style Manual issues in it instead.
- If an obligation is ambiguous (unclear who, what or when), ask rather than guess.
- If the user asks for a standard or informal tone, note that this skill applies formal tone and offer `au-gov-email-letter` or `au-gov-report`.
- Do not present convention-based rules as Style Manual requirements.
- Always use Australian spelling and conventions.
- Never deliver a draft without the completed checklist.
