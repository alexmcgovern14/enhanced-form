You are assigning a single statistical assessment for each football match.

## Task
For each match in `form.recent_matches[]`:
- Assign exactly **one** assessment label that describes whether the result reflected the underlying performance

## How to assess
- Base your decision **primarily on match statistics**, including:
  - xG for vs against
  - goals vs xG
  - red cards
  - quality of chances
- Use the narrative summary only to:
  - sanity-check edge cases
  - avoid labels that clearly contradict widely reported consensus

Statistics take precedence. Narrative should not override clear statistical signals.

## Label constraints
- Select **one label only** from the predefined allowed set
- Do NOT invent new labels
- Do NOT hedge or combine labels

## Output rules
- Write the result to:
  - `form.recent_matches[].statistical_assessment`
- Do NOT modify any other fields
- Return valid JSON only
