---
name: au-gov-report
description: >
  Draft or review internal reports in Australian Government style.
  If no structure is given, generates a compliant one automatically.
  Applies plain language, accessibility, and compliance rules.
  Returns a polished draft and a completed quality checklist.
---

# AU Government Reports

**What this skill does:**
- Draft or review the structure and content of internal government reports.
- When the user gives only the subject, purpose, and audience, the skill builds a full, compliant structure from the writing standards below – no template needed.
- Always output the final draft together with a filled‑in “Before Finalising” checklist.

**What this skill does NOT do:**
- Build final PDF, HTML or printed layouts.
- Provide legal, policy, or subject‑matter content (the user supplies facts).
- Handle visual design, branding, or template creation.

---

## Process

### Step 1: Receive the report brief
Ask only for what’s missing:
- Report type (annual, research, review, board paper, commissioned, etc.)
- Purpose and audience
- Tabling requirement? (Yes/No)
- Any key content points the user wants to include
- Deadline, if applicable

If the user has a specific structure or template in mind, they may provide it here – otherwise the AI will construct one.

### Step 2: Build structure and draft
1. **Construct the structure**  
   Use the **Writing Standards** below to determine every required section. For example:
   - A commissioned report will automatically include a letter of transmittal.
   - All reports get a landing page, contents, summary, chapters, and endmatter unless the brief clearly excludes them.
   - Annual reports follow Department of Finance requirements.

   If the user didn’t supply a template, the AI presents the outline (headings only) for a quick yes/no before proceeding. If the user has already given full sign-off or wants speed, skip to drafting.

2. **Draft the content**  
   Write each section in plain language, following tone, voice, and accessibility rules. Use the user’s key points to populate the structure. Keep sentences short, language active, and all conventions intact.

### Step 3: Quality check
Run the **Before Finalising – Checklist** internally. Fix every issue.  
Return the final draft, followed by the completed checklist.

---

## Writing Standards

### Format & accessibility
- Content must be usable by people with disability (Disability Discrimination Act 1992). Aim for WCAG 2.0 AA.

### Tone, voice & plain language
Same foundation as all government writing:
- **Tone:** Standard (contractions allowed, no idioms/slang/jargon).  
- **Voice:** respectful, clear, direct, objective, impartial.  
- **Plain language:** everyday words, sentences avg. 15 words (never >25), active voice, personal pronouns (*we, you*).  
- Inclusive language: *they/them*, no unnecessary descriptors.  
- Australian English spelling.

### Report structure (default – adapt to type)
1. **Landing page or cover**  
   Title, subtitle, author/editor, date, publisher, short summary.

2. **Preliminary content** (numbered i, ii, iii…)  
   - Title page  
   - Reverse title page (copyright, publisher, ISBN/ISSN, edition)  
   - Letter of transmittal (if report was commissioned or must be formally submitted)  
   - Foreword, preface, or introduction (rarely all three)  
   - Contents (max 3 levels of headings)  
   - Lists of figures, tables, maps (if any)  
   - Acknowledgements  
   - Summary – label as ‘Summary’ or ‘Recommendations’, never ‘Executive summary’.

3. **Main body**  
   - Organise into chapters; use Parts only for very long reports.  
   - Number chapters consecutively; continue numbering across Parts.  
   - Use descriptive headings, bullet lists, and boxed case studies where helpful.

4. **Endmatter** (page numbering continues from main body)  
   - Appendices (Appendix A, B, C…)  
   - List of shortened forms (if many)  
   - Glossary (alphabetical)  
   - Reference list / bibliography  
   - Index (for long or print‑first reports)

### Tabling & compliance
- **Tabled in Parliament:** follow Tabling guidelines; electronic version must match printed version exactly and be accessible.  
- **Annual reports:** meet Department of Finance content requirements and publish via Transparency Portal.  
- **Information management:** classify per PSPF; manage as a record under the Archives Act 1983.  
- **Copyright:** use open access licence (e.g., Creative Commons) for government material; fulfil legal deposit.

---

## Before Finalising – Checklist
- ☐ PDF links tagged with size and format?  
- ☐ Landing page/cover has title, author, date, summary?  
- ☐ All preliminary parts present and ordered correctly?  
- ☐ Summary named ‘Summary’ or ‘Recommendations’?  
- ☐ Main body structured into chapters/parts with clear headings?  
- ☐ Figures, tables, maps listed and accessible?  
- ☐ Endmatter correctly ordered?  
- ☐ Plain language and inclusive language throughout?  
- ☐ Tabling/compliance requirements met (if applicable)?  
- ☐ Security classification marked (if required)?  
- ☐ Australian English spellcheck done?  
- ☐ Walked away and re‑read?

---

## Guardrails
- Never alter the user’s facts, policy, or recommendations.   
- When a mandatory section (e.g., letter of transmittal) is unclear, quickly confirm with the user before drafting.  
- For tabled or annual reports, verify the user is aware of parliamentary printing and Transparency Portal rules.  
- Always use Australian spelling and conventions.  
- Never deliver a draft without the completed checklist.
