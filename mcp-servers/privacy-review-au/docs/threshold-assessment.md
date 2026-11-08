# Threshold assessment

A privacy threshold assessment is the short, documented check a team does before (or instead of) a
full PIA. Does the project involve personal information, and does anything point to significant
privacy impact? For Australian Government agencies the answer has legal force. The Agencies APP Code
s 12 requires a PIA for every high privacy risk project.

Every review reports `threshold_readiness`: where the assessment would land on current evidence.
When the team is ready to complete one, `threshold_assessment` builds the draft record from the same
evidence. It returns the outcome with reasons, all 17 questions with their answer, basis and evidence,
the inventory, the critical and high findings as issues for the PIA, open questions, verified
citations, and `report_markdown` with a sign-off table.

## The questions

| Question | Weight | The scanner can look for it |
| --- | --- | --- |
| `handles_personal_information` | gate | yes |
| `new_or_changed_handling` | gate | no |
| `sensitive_information` | high | yes |
| `biometrics_or_surveillance` | high | yes |
| `automated_decisions` | high | yes |
| `vulnerable_individuals` | high | yes |
| `large_scale` | high | no |
| `data_matching_or_linkage` | high | yes |
| `indirect_collection` | high | yes |
| `digital_id_system` | high | yes |
| `tracking_and_profiling` | medium | yes |
| `government_identifiers` | medium | yes |
| `overseas_disclosure` | medium | yes |
| `third_party_disclosure` | medium | yes |
| `secondary_use` | medium | yes |
| `security_weaknesses` | medium | yes |
| `community_expectations` | medium | no |

Questions the scanner cannot look for can still be answered from documents and observations.
`list_threshold_questions` gives the full wording, guidance, the evidence that would settle each
question, and the observation kinds that record it.

## Answers

| Answer | Meaning |
| --- | --- |
| `yes` / `no` | Stated by the team, recorded as an observation (with its source), or (for `yes`) found in code. |
| `indicated` | Documents mention it, but nobody has confirmed it. |
| `not detected` | Code was examined and showed nothing. Treated as absent until the team confirms. |
| `unknown` | Nothing has answered it, or the material where the answer would show up was not examined. |

The team's answer takes precedence, then observations, then code, then document mentions. If the team
or an observation says "no" but the code shows evidence, the record flags the conflict (⚠) and asks
why the evidence does not apply.

## Outcomes

| Outcome | When |
| --- | --- |
| `pia_required` | Australian Government agency (`entity_type: agency`), the project looks like a high privacy risk project (Agencies APP Code s 12(2)), and handling is not stated to be unchanged. A PIA is mandatory (s 12(1)). |
| `pia_recommended` | Any high-weight factor, or two or more medium factors once personal information is confirmed. |
| `targeted_review` | One medium factor (for example overseas hosting). Deal with it directly and keep the record. |
| `undetermined` | Open questions could change the outcome. Also used when factors were found but personal information was not confirmed, for example a payment SDK in code that receives nothing visible. |
| `pia_not_indicated` | No factor found or stated. Keep the record and revisit it if the project changes. |

The outcome is a starting point for the team's judgement, not a substitute for it.

## Other Acts

- **Digital ID Act 2024.** If the project is part of, or relies on, the Australian Government Digital
  ID System, pass `digital_id_role` (`accredited_entity` or `relying_party`). The Act's privacy rules
  then link to findings, and the record raises the role-specific questions. The Accreditation Rules can
  require PIAs (s 28(2)(b)). The Digital ID Rules and Accreditation Rules themselves are not in the
  knowledge base.
- **Security of Critical Infrastructure Act 2018.** When `large_scale` is yes, the record asks whether
  the system stores or processes personal information about 20,000 or more people for a government
  body. Personal information about that many people is "business critical data" (s 5). A system that
  stores or processes it for a government body may be a critical infrastructure asset (s 12F), with
  cyber incident reporting within 12 or 72 hours.
- **State and territory law** is not assessed. For a state or territory body the questions are still a
  sound structure, but the legal basis must come from the relevant state Act.
