---
name: product-feature-interpreter
description: >
  Produces a brand-agnostic, buyer-focused analysis of an enterprise software product. Separates table-stakes from novel capabilities, surfaces possible costs and organizational change needs, and identifies top risks with concrete causes. Output is a structured, neutral report that abstracts features from brand and marketing.
---

Enterprise Software Product Evaluation Skill

Purpose

To evaluate an enterprise software product independently of its brand and marketing. Given product documentation, sales collateral, or web search results, this skill produces a structured, neutral analysis that helps a potential buyer understand:

· What the product actually does (table‑stakes vs. potentially novel capabilities)
· What it will cost beyond the licence fee
· What organisational changes are required
· What the most likely risks are, and why

The analysis is written for procurement teams, enterprise architects, and business case authors who need vendor‑neutral insight. This skill evaluates a single product; for multi-product comparisons, run the skill separately for each and then synthesise.

When to Use

· Evaluating a new platform (e.g., control tower, governance, AI ops, observability)
· Comparing multiple products in the same category
· Preparing a business case or procurement recommendation
· Auditing an existing vendor relationship for hidden exposure

Analysis Workflow

Follow these steps in order. Each step produces material that feeds the final output.

Step 1: Extract Advertised Features

From source materials, list every claimed feature or benefit. Do not filter, group, or brand‑name at this stage. Keep verbatim phrasing when useful.

Step 2: Abstract into Product Requirements

Rewrite each feature as a single, generic product requirement. Remove all brand names, proper nouns, and marketing adjectives. Use plain, imperative language (e.g., “Discover assets across public clouds” not “Acme’s patented SmartDiscovery engine”). If the source describes a benefit rather than a function, infer the underlying functional requirement.

Step 3: Group into Major Capabilities

Cluster the abstracted requirements into 4–8 cohesive capability areas (e.g., “Asset Discovery & Inventory”, “Policy Automation & Remediation”, “Cost Governance”). Give each area a concise, descriptive name. These groupings will become the sections of the final analysis.

Step 4: Separate Common vs. Novel

Classify each capability according to how it compares with the known competitive landscape.

Source of competitive knowledge:

· If the user has provided competitor materials or a landscape brief, use that as the primary reference.
· If no competitive data has been supplied, rely on general industry knowledge of the product category and note that classification is provisional – to be verified.
· In either case, flag the source basis (e.g., “based on provided competitor data” or “based on typical category benchmarks”).
· If the product category is unfamiliar or a reliable comparison cannot be made, classify all capabilities as “Likely common (unverified)” and state that a competitive benchmark could not be established.

Classification labels:

· Common (table stakes): The capability is widely present in at least two other competing products. Losing this would make the product non‑viable.
· Likely common: Without direct competitor data, the capability appears to be standard in the category.
· Possibly novel: The capability seems ahead of the typical market offering but may exist in niche competitors.
· Novel (differentiator): The capability is not yet standard and represents a genuine differentiator. Note if it appears unique.

Novelty assessment is based on advertised capabilities; realised uniqueness may differ post‑deployment.

Step 5: Identify Hidden Costs of Purchase

List undocumented or easily overlooked costs that go beyond the obvious licence or subscription fee. For each, describe the trigger or unit (e.g., per API call, per 1,000 assets) when available.

Typical areas to examine:

· Consumption‑based fees (API calls, AI assists, transactions, data volume)
· Mandatory annual escalators and true‑up clauses
· Required premium connectors or modules (e.g., SAP, Salesforce)
· Implementation and professional services (rate card or fixed price indications)
· Training, certification, and internal upskilling fees
· Additional infrastructure or third‑party licences needed (CMDB, log storage, observability backend)

If no cost information is available, list category‑typical cost triggers (e.g., “API‑based consumption fees are common in this space”) and mark each as “to be confirmed during procurement”.

Step 6: Extract Organizational Change Needs

Derive from the complexity, deployment model, and integration surface of the capabilities. Be concrete.

For each needed change, specify:

· What new or evolved role is required (e.g., “Cloud Governance Lead”, “AI Assurance Analyst”)
· Which existing team is disrupted (e.g., “Platform Engineering”, “IT Service Desk”)
· What new skill or process gap must be closed (e.g., “FinOps tagging discipline”, “Incident triage for AI-generated alerts”)
· Approximate effort or headcount implication if inferable (e.g., “part-time role for first year”, “at least 2 FTE from Security Operations”)

Also note any required process re‑engineering, steering committees, or formal change management program (champions, communication, training rollout). If source materials lack detail, infer typical impacted enterprise functions (Platform Engineering, Security Operations, FinOps, IAM, Service Desk) from the capability areas.

Step 7: Predict Top 3 Risks

Synthesize risks from Steps 4–6. Do not give generic project‑failure warnings. Instead, tie each risk to a specific, earlier finding.

For each risk, provide:

· Risk description (one line)
· Why it’s likely – reference a novel capability, a hidden cost, or an organisational gap identified above
· Consequence – what materialises if the risk isn’t mitigated

Example linkage: “Risk of vendor lock‑in” connects to a novel, non‑standard API surfaced in Step 4; “Risk of TCO overrun” links to a consumption‑based fee in Step 5 whose metering is opaque.

Step 8: Write Capability Descriptions (Blended Nuance)

For each capability from Step 3, write a single, lean paragraph that combines “what it does” with practical limitations, constraints, or edge cases. Do not use separate “What it does” / “Nuance” sub‑headings; blend the nuance directly into the description.

Critical rule for constraints:
Add one realistic, category‑typical limitation that a well‑informed buyer should anticipate. Phrase it as “Expect…”, “Typically…”, or “In practice…”. Never present a limitation as verified for this specific product unless the source material explicitly confirms it. The aim is to reflect industry behaviour, not to fabricate product‑specific flaws.

For illustration, a blended description might read: “Asset Discovery typically scans multi‑cloud inventory via agentless APIs, but expect coverage gaps in restricted network environments unless a dedicated collector is deployed.”

Step 9: Produce Product Category Description

Write a one‑sentence classification of the product category (e.g., “Cloud governance platform”, “AI observability tool”). Follow with a 2–3 sentence summary of the product’s intended role, drawn from the abstracted requirements and capabilities. This will open the final report.

Step 10: Format Final Output

Assemble the analysis in the order below using markdown heading level 2 (##) for each section title. Use bullet lists for capabilities, hidden costs, and organizational change needs.

1. Product Category Description – as per Step 9
2. Core Capabilities (Table Stakes) – bullet list; each item a blended capability description from Step 8 that was classified Common or Likely Common
3. Differentiating Capabilities (Novel) – bullet list; each item a blended capability description from Step 8 that was classified Possibly Novel or Novel, with the classification label in parentheses and a note on the knowledge source. If no capabilities meet the “Possibly novel” threshold, state that the product appears to compete on execution, integration, or pricing rather than feature uniqueness.
4. Hidden Costs – concise list from Step 5
5. Organizational Change Needs – concise list from Step 6
6. Top 3 Risks – numbered list, each containing “Why it’s likely” and “Consequence” as per Step 7

Quality Checks

Before finalising, verify the following:

· No brand names or brand‑like attributes appear in requirements, capability names, or descriptions.
· Every capability description includes at least one category‑typical constraint (using “Expect…”, “Typically…”, etc.).
· The common/novel classification clearly states its knowledge basis (provided data or general industry knowledge). If no competitive benchmark was possible, that is explicitly noted.
· Hidden costs go beyond the obvious licence fee and are described with their trigger or unit where possible; any category‑typical costs are marked as “to be confirmed” if unsupported.
· Organisational change needs name actual roles, disrupted teams, and skill gaps – not just vague “change management”.
· Each risk explicitly references a specific capability, hidden cost, or change need identified earlier, with no generic project‑failure statements.
· The product category description is neutral and does not repeat marketing superlatives.