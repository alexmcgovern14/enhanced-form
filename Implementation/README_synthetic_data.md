# Synthetic data generation

Generate synthetic Enhanced Form JSON for a single fixture (two teams), where each team has:
- `10` recent matches (`5` home + `5` away)
- full match stats + a concise (≤3 sentence) narrative per match
- shaped `1-5` opponent strength tiers (`1` easiest, `5` hardest; extremes intentionally rare)
- the same key-structure as `Primary context/Sample_json_structure.json`

## Generate one fixture

From repo root:

```bash
python3 Implementation/synthetic_fixture.py --fixture-date 2026-02-01 --seed 42
```

This writes:
- `Output/synthetic_<timestamp>/team_home.json`
- `Output/synthetic_<timestamp>/team_away.json`
- `Output/synthetic_<timestamp>/fixture_meta.json` (includes validation results)

## Choose teams

Team names are read from `Primary context/List of club names to use.md`.

```bash
python3 Implementation/synthetic_fixture.py \\
  --home-team "North London" \\
  --away-team "Man Red" \\
  --fixture-date 2026-02-01 \\
  --seed 123
```

## Force specific opponents into recent matches

```bash
python3 Implementation/synthetic_fixture.py \\
  --home-team "West Glamorgan City" \\
  --away-team "North London Red" \\
  --fixture-date 2026-02-01 \\
  --must-include-opponents "Merseyside Red,Man Red,Tyneside,Yorkshire Whites,The Potteries,Pompy" \\
  --seed 42
```

## Run steps 2–4 (LLM match assessor)

Step 2 can be LLM-generated (stats + narrative), producing `03_with_assessments.json`, then step 3/4 outputs.

```bash
cp .env.example .env
# edit .env and set OPENAI_API_KEY
set -a && source .env && set +a
python3 Implementation/run_steps_2_4_local.py \\
  --step2 llm \\
  --step3 llm \\
  --step4 llm \\
  --model gpt-4.1-mini \\
  form_west_glamorgan_city.json form_north_london_red.json
```
