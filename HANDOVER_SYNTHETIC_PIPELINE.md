# Enhanced Form handover

## What we're building

Enhanced Form is a richer way of explaining a team's recent form.

The aim is not prediction. The aim is to help users understand:

- whether results were actually representative of performances
- how difficult the opposition was
- what the widely accepted story of each match was

The core idea is to combine two different lenses:

- a **data-led view** based on match stats, rollups and opponent context
- a **consensus view** based on how the match was widely described in reports and coverage

This matters because stats do not always fully capture the context of a match. A team can lose while still being described as unlucky, depleted, disrupted by red cards, or affected by other mitigating circumstances. The intention was to use the internet's consensus reaction as a sense check on the statistical read, not as a replacement for it.

## Why the system is designed as a chain

The workflow was deliberately split into stages so that **facts, consensus and judgement** were not all blended together in one generation step.

Design goals:

- keep the reasoning inspectable and auditable
- reduce hallucination risk
- stop narrative consensus from being presented as statistical fact
- let stats remain the primary signal while still accounting for context
- minimise what the final writer sees so the output stays grounded

In practical terms, the design was:

1. Build the structured match and season data first.
2. Add a separate qualitative layer for match-report consensus.
3. Assess each match statistically, using the narrative layer as a sanity check for edge cases.
4. Convert the resulting analysis into user-facing copy.

A later claims-based approach was explored in prototype, but the intended production workflow can be understood more simply: prepare the data, generate match-level narrative summaries, assign statistical assessments, then write the final summaries using stats as the primary signal and narrative as a sense check.

## What this is

This repo currently contains a **synthetic-data prototype** for the Enhanced Form workflow, plus a separate prototype for **opposition strength ratings**.

For handover purposes, the **latest synthetic/local run is the source of truth**:

- `Output/local_run_2026-04-01_handover_rules/`

Current synthetic-pipeline note:

- opponent strength now uses a shaped `1-5` scale rather than `weak / average / strong`
- `1` = easiest opposition, `5` = hardest opposition
- tiers `1` and `5` are intentionally rare

## Where we got to

- We moved away from relying on the Chelsea real-data flow as the main working prototype.
- The maintained workflow now starts from **synthetic team JSON** and runs the downstream analysis locally.
- The latest pipeline produces:
  - match-level `statistical_assessment`
  - deterministic scope analysis
  - user-facing summaries for:
    - last 5 home matches
    - last 5 away matches
    - most recent 5 overall
- The latest output shape is visible in:
  - `Output/local_run_2026-04-01_handover_rules/north_london_red/`
  - `Output/local_run_2026-04-01_handover_rules/west_glamorgan_city/`

## Current pipeline

### 1. Generate synthetic fixture + team form JSON

Files:

- `Implementation/synthetic_fixture.py`
- `Implementation/README_synthetic_data.md`

What it does:

- generates two teams for one fixture
- creates `10` recent matches per team by default
- includes:
  - season context
  - rollups
  - shaped `1-5` opponent strength tier
  - synthetic narratives
  - placeholder `statistical_assessment`
- validates output shape and writes `fixture_meta.json`

Typical output:

- `Output/synthetic_<timestamp>/team_home.json`
- `Output/synthetic_<timestamp>/team_away.json`

### 2. Export stable per-team files

File:

- `Implementation/export_team_forms.py`

What it does:

- converts `team_home.json` / `team_away.json` into stable files like:
  - `form_north_london_red.json`
  - `form_west_glamorgan_city.json`

### 3. Run local workflow steps 2-4

File:

- `Implementation/run_steps_2_4_local.py`

What it does:

- **Step 2**: writes match assessments into `03_with_assessments.json`
- **Step 3**: builds deterministic scope analysis into `04_analysis.json`
- **Step 4**: renders summaries into `05_form_summary.json`
- also writes combined files:
  - `04_with_analysis.json`
  - `05_with_summary.json`

Important note:

- In the synthetic pipeline, **step 1 is effectively bypassed** because narratives are already created in the synthetic generator.

## Latest state of the output

The latest runs show the pipeline working end-to-end for synthetic teams.

What is working:

- 10-match form window generation
- 5 home / 5 away split
- rollup calculations
- per-match assessments
- simple intermediate form analysis
- final summary generation
- local inspection via viewer

Latest output files to inspect:

- `Output/local_run_2026-04-01_handover_rules/north_london_red/03_with_assessments.json`
- `Output/local_run_2026-04-01_handover_rules/north_london_red/04_analysis.json`
- `Output/local_run_2026-04-01_handover_rules/north_london_red/05_form_summary.json`
- `Output/local_run_2026-04-01_handover_rules/west_glamorgan_city/03_with_assessments.json`
- `Output/local_run_2026-04-01_handover_rules/west_glamorgan_city/04_analysis.json`
- `Output/local_run_2026-04-01_handover_rules/west_glamorgan_city/05_form_summary.json`

## Most recent product/logic change

The two main changes in the current maintained pipeline are:

- moving opponent strength to a shaped `1-5` scale
- simplifying the workflow back to:
  - data preparation
  - narrative summary layer
  - statistical assessment
  - final summary writing

Relevant files:

- `Implementation/synthetic_fixture.py`
- `Implementation/run_steps_2_4_local.py`
- `System_prompts/04_form_generator.md`

This is the clearest current direction of the prototype.

## Viewer

Files:

- `form_viewer.html`
- `run_form_viewer.py`
- `start_form_viewer.sh`

Purpose:

- local browser viewer for inspecting generated Enhanced Form outputs

## Opposition strength rating

This became a broader opportunity beyond Enhanced Form.

Potential product use:

- add a strength/difficulty indicator to fixture lists so users can quickly judge how tough upcoming games are
- similar to how FPL surfaces fixture difficulty
- useful both inside Enhanced Form and elsewhere in the product

Prototype status:

- standalone exploratory prototype exists in `ppg_strength_prototype/`
- it builds strength ratings from home/away PPG contexts
- it outputs JSON plus HTML dashboards

Useful files:

- `ppg_strength_prototype/build.py`
- `ppg_strength_prototype/data/`
- `ppg_strength_prototype/out/`

What it already demonstrates:

- venue-specific strength ratings
- multiple rating approaches:
  - percentile
  - z-score
  - shaped
- output suitable for UI exploration

What is not done:

- not integrated into the main Enhanced Form pipeline
- not wired into a fixture-list UI
- no final decision on which rating method to use
- some edge cases still exist for promoted teams / missing prior-season context, shown in:
  - `ppg_strength_prototype/out/_issues.json`

## What is not done

- no production data source integration
- no real end-to-end pipeline from live data to summary in the current maintained path
- no automated tests
- no packaging / service layer / deployment setup
- no final decision on whether the main product output should be:
  - per-team form only
  - fixture difficulty only
  - or both combined

## Recommended next steps

1. Decide whether the next milestone is:
  - improving Enhanced Form itself
  - or extracting opposition strength into a reusable platform component
2. If continuing Enhanced Form, keep the **synthetic pipeline** as the safe prototype harness and add a clean real-data ingestion layer separately.
3. If pursuing fixture difficulty, turn `ppg_strength_prototype/` into a smaller dedicated spec with:
  - chosen rating method
  - UI representation
  - handling for promoted teams / sparse data
4. Remove and rotate any real API secrets before wider sharing. `.env.example` should not contain a live key.

