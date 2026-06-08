---
name: gtm-adoption-assumptions
description: >
  Rapidly develop go-to-market and adoption assumptions for a product or service. 
  Identify the critical assumptions that need testing to gauge market adoption. 
  Produces a first-pass GTM strategy, backed by a structured set of assumptions 
  for lean, evidence-informed adoption.
---

# GTM Adoption Assumptions

A critical-thinking exercise that produces a first-pass Go-To-Market strategy, reveals market-risk flaws early, and defines the assumptions that must be tested to prove viability. The AI takes a concise product/service description, then performs iterative web research and chain-of-thought reasoning to build the GTM. The user supplies the initial brief and validates critical unknowns.

**What this skill does:**
- Draft a first-pass GTM strategy quickly.
- Surface flaws in the market logic of the GTM as fast as possible.
- Deliver a clear, testable assumptions list with an actions tracker.

**What this skill does NOT do:**
- Define new sales or marketing channels (separate activity).
- Address execution details of service delivery or product fulfilment.

> “Internal bias about the GTM you want to build is the biggest risk to success.”

## Process

### Step 1: Receive Product/Service Description
The user must provide a brief that meets these **minimum criteria**:

1. **Problem or opportunity** – What problem are you solving or what opportunity are you creating? (1–2 sentences)
2. **Paying customers** – Who will pay money for it?  
   - *B2B:* Name the roles (e.g., “Head of HR at mid-size tech companies”) and briefly explain why they’d care.  
   - *B2C:* Give 3–5 proto-personas, each with 3 demographic bullet points (age, income, location, etc.) and 3 behavioural bullet points (habits, buying triggers, etc.).  
   - *B2B2C/Hybrid:* Define both the end-user (who uses it) and the economic buyer (who pays for it).
3. **Substitutes** – What would they pay for if your solution isn’t available? (Current alternatives)
4. **Key “milk-aisle” value** – The 1–2 things an extremely satisfied customer would say when briefly describing why they like it. (No detailed review – just what they’d blurt out before paying for milk.)

If the description is incomplete, the AI will ask for clarification before proceeding.  
**Once received, the AI will acknowledge the brief and begin its own work; the user will only be interrupted when a stop/go decision requires human input or when a critical piece of data cannot be found.**

### Steps 2–6: AI Research & Chain-of-Thought
The AI now moves through the remaining GTM steps **iteratively**, using web searches and internal reasoning.

#### Research Sprints (what the AI searches for)
- **Revenue heuristic data:** Market size indicators, typical conversion rates for similar products/services, average order values or revenue-per-sale benchmarks.
- **Cost structure:** Typical partnership models and cost ranges, people/technology/legal/premises/supply costs for similar offerings.
- **Value & needs:** Customer reviews, pain-point reports, retention data for adjacent offerings.
- **Positioning & competition:** Competitor products, price points, common criticisms (weaknesses), frame-of-reference brands, and market reports.

#### Chain-of-Thought Reasoning
The AI will think step by step through the logic of the original GTM Sprint, using the researched data to:

- **Step 2 – Revenue Heuristic:** Compute (available opportunities × conversion rate × mean revenue per sale).  
  *Stop/go:* If the number is **not exciting**, the AI must output `[STOP: Awaiting User Input]` and explain why, along with what assumptions would need to change. It will not proceed further until the user adjusts the brief or accepts a flag.

- **Step 3 – Execution Enablers:** List partners and costs, compare total costs to the revenue heuristic.  
  *Stop/go:* If costs aren’t favourable, the AI must identify any testable assumptions that could improve cost/revenue over time. If none exist, it will output `[STOP: Awaiting User Input]` and halt, explaining the gap.

- **Step 4 – Define Value:** Using the brief and research, articulate the specific value customers get, the needs satisfied, why they’d keep buying, and how the value is obvious to them.

- **Step 5 – Clarify Positioning:** Map a 4-point price-range comparison for the same outcome, identify competitors, explain why customers would choose this offer, list the unacceptable weaknesses in the category, name the best frame-of-reference competitors, and extract lessons from them.

- **Step 6 – Assumptions:** From the above reasoning, the AI will derive **at least 10 testable assumptions**, each with a suggested action to test it. These are output in the assumption tracker (table with Assumption, Actions, Outcome + Notes).

**The AI will present its work as a single, structured Markdown draft** (using headers, bullet points, and tables) — not as a live walkthrough.  
If a web search fails to yield a needed benchmark, the AI will use transparent, conservative placeholders and ask the user to confirm or provide a better figure.  
The AI will never invent precise data without disclosure.

### Step 7: Testing Plan
The AI will recommend the fastest, cheapest ways to test the top-priority assumptions, prioritizing data sources or interview topics.  
If interviews are suggested, the AI will provide a Mom Test-style question sequence (focused on past behaviours and facts, not hypothetical future promises), but the user will later execute the tests.

## Deliverable
At the end of the sprint, the user receives:
- A one-page GTM summary (Steps 1–5 outputs, revenue heuristic, cost/reality comparison)
- An assumption tracker (minimum 10 assumptions with test actions, outcome column initially blank)
- A testing plan with first actions (data checks, interview guides)

All deliverables are formatted in clear, structured Markdown for readability.

## Guardrails
- **Stop/go enforcement:** The AI must halt at Step 2 and Step 3 gates by outputting `[STOP: Awaiting User Input]` and waiting for user confirmation.
- **No channel/execution scope creep:** If the user asks for channel design or service-fulfilment details, the AI will note it for a separate activity and steer back.
- **Bias challenge:** The AI will gently pressure-test the “internal bias” — if the research hints the market logic is weak, it will say so clearly.
- **Minimal user interruptions:** The user provides the brief once, then interacts only when the AI hits a data dead-end or a stop/go gate. The heavy lifting is done by AI web searches and reasoning.
- **Transparency:** Whenever data is synthetic or estimated, the AI flags it. Ask for user corrections where feasible.