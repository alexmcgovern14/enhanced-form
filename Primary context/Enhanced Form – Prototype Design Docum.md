# Enhanced Form – Prototype Design Document

## Product context

Enhanced Form is an initiative to improve the experience of **football bettors** and other users by providing a richer, more trustworthy representation of recent team form.

The current form experience (last 5 results) provides:
- Result
- Opposition
- Score
- Home/away

Enhanced Form aims to add:
- Was a result representative of the performance? A team winning 1-0 could be a lucky scrape or they could have deserved to win 5-0. We aim to articulate the underlying numbers.
- What was the strength of the opposition? Beating the team who is 1st in league is different to beating the team who is 20th and we aim to convey this. 

To achieve this, Enhanced Form combines:
- Match statistics
- Opponent context
- Popular consensus (match reports)
- Clear, explainable labels and trends

The goal is **trust, clarity, and retention**, not prediction.

---

## Project context

This prototype is designed to validate:
- Data completeness
- Feasibility of a multi-step LLM workflow
- Whether combining narrative + stats improves perceived quality of form analysis

We will use real fixtures. Data should be real data found on web. Slight inaccuracies are acceptable for prototype, but always use real data where possible and state if data is not real.

The prototype will be built in **Cursor**, using:
- Web search
- Lightweight calculations
- LLM reasoning where appropriate

---

## Core design principles

- Separate **facts**, **narrative**, and **judgement**
- Use LLMs where human consensus matters
- Keep intermediate outputs structured and auditable
- Minimise what the final generator sees

## Non-goals
- No predictions
- No betting advice
- No probabilities
- No player-level analysis

---

## Input data structure pre-work

**This section provides the necessary data for the workflow to start**.

- Sample_json_structure.json contains the structure of JSON per team and must not be changed.
- json_data_definition.md contains description of data within JSON

You will discover data for the json using web search.

- I will provide a team and you will use web search to discover and fill in all non-calculated fields.
- Then fill calculated fields per descriptions.
  - roll up data in form.form_window should be calculated from the data found per match
- do not fill in form.recent_matches.narrative_summary at this stage, it will be added in main workflow
- do not fill in form.recent_matches.assessment at this stage, it will be added in main workflow
- get PPG and league position for form.season_context and for each opponent in recent match by searching premier league table using current date. Note: On production  recent matches will use historical PPG and league position at time of fixture, but for prototype we'll just use today's data and assume it was the same at the time of kick off — Acceptable for Proof of concept.

---

## Prototype workflow design

**1. Narrative generation**  
An LLM uses web search to find multiple match reports for each of the team’s last five games.  
**Input:**  
- Match identifiers and basic match metadata in `form.recent_matches[]`  

**Output:**  
- A short, neutral narrative summary describing how each match was widely perceived  
- Written back to `form.recent_matches[].narrative_summary`

**Prompt:**
System_prompts/01_narrative_generation.md

---

**2. Match assessor**  
An LLM reviews each match’s statistical data and assigns a single outcome assessment (e.g. *deserved win*, *unlucky loss*). The model cross-checks this assessment against the narrative summary to ensure it does not contradict the commonly reported view of the match.  
**Input:**  
- Match statistics in `form.recent_matches[]`  
- Narrative summaries in `form.recent_matches[].narrative_summary`  

**Output:**  
- A single assessment label per match  
- Written back to `form.recent_matches[].statistical_assessment`  
**Prompt**

---

**3. Form analyst**  
An LLM reviews the complete form dataset to identify key patterns and themes across the last five matches, and determines which information is most relevant to explain the team’s recent form.  
**Input:**  
- The complete `form` JSON  

**Output:**  
- A reduced, structured analysis highlighting the most important insights  
- Passed to the generator (not written back to the main JSON)

---

**4. Form generator**  
An LLM receives the analyst’s reduced dataset and produces a clear, user-facing summary of the team’s form over the last five matches.  
**Input:**  
- Slimmed analysis output from the analyst  

**Output:**  
- Natural-language form summary for display to users
