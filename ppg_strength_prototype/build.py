import json
import math
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
OUT_DIR = BASE_DIR / "out"
HTML_DIR = OUT_DIR / "html"

COLOR_SCALE = {
    1: "#2e7d32",
    2: "#81c784",
    3: "#fdd835",
    4: "#fb8c00",
    5: "#e53935",
}

NAME_NORMALISATION = {
    "Man City": "Manchester City",
    "Man United": "Manchester United",
    "Spurs": "Tottenham Hotspur",
    "Tottenham": "Tottenham Hotspur",
    "Newcastle": "Newcastle United",
    "Nottingham": "Nottingham Forest",
    "West Ham": "West Ham United",
    "Bournemouth": "AFC Bournemouth",
}

TEAM_FILE_ALIASES = {
    "Manchester City": "ManCity",
    "Newcastle United": "Newcastle",
    "Tottenham Hotspur": "Tottenham",
}

def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
        f.write("\n")


def normalise_name(name):
    return NAME_NORMALISATION.get(name, name)


def short_team_name(name):
    short_map = {
        "Manchester United": "Man Utd",
        "Manchester City": "Man City",
        "Nottingham Forest": "Forest",
        "Tottenham Hotspur": "Spurs",
        "Newcastle United": "Newcastle",
        "AFC Bournemouth": "Bournemouth",
        "West Ham United": "West Ham",
    }
    return short_map.get(name, name)


def build_ppg_contexts(home_table, away_table):
    contexts = []
    for row in home_table:
        team = normalise_name(row["team"])
        matches = row["matches_played"]
        points = row["points"]
        ppg = round(points / matches, 3)
        contexts.append({
            "team": team,
            "venue": "home",
            "matches": matches,
            "points": points,
            "ppg": ppg,
        })
    for row in away_table:
        team = normalise_name(row["team"])
        matches = row["matches_played"]
        points = row["points"]
        ppg = round(points / matches, 3)
        contexts.append({
            "team": team,
            "venue": "away",
            "matches": matches,
            "points": points,
            "ppg": ppg,
        })
    return contexts


def combine_contexts(current_contexts, last_home_table, last_away_table, issues):
    last_contexts = build_ppg_contexts(last_home_table, last_away_table)
    last_lookup = {(row["team"], row["venue"]): row for row in last_contexts}
    combined = []
    for row in current_contexts:
        key = (row["team"], row["venue"])
        last_row = last_lookup.get(key)
        if last_row is None:
            issues.append({
                "type": "missing_last_season",
                "team": row["team"],
                "venue": row["venue"],
            })
            combined.append({**row, "ppg": round(row["ppg"], 3)})
            continue
        matches = row["matches"] + last_row["matches"]
        points = row["points"] + last_row["points"]
        ppg = round(points / matches, 3)
        combined.append({
            **row,
            "matches": matches,
            "points": points,
            "ppg": ppg,
        })
    return combined


def boundary_thresholds(ppg_values, cutoffs):
    sorted_desc = sorted(ppg_values, reverse=True)
    thresholds = []
    n = len(sorted_desc)
    for cutoff in cutoffs:
        index = max(0, min(n - 1, math.ceil(n * cutoff) - 1))
        thresholds.append(sorted_desc[index])
    return thresholds


def assign_strength_percentile(contexts, cutoffs):
    ppg_values = [row["ppg"] for row in contexts]
    b5, b4, b3, b2 = boundary_thresholds(ppg_values, cutoffs)
    rated = []
    for row in contexts:
        ppg = row["ppg"]
        if ppg >= b5:
            strength = 5
        elif ppg >= b4:
            strength = 4
        elif ppg >= b3:
            strength = 3
        elif ppg >= b2:
            strength = 2
        else:
            strength = 1
        rated.append({**row, "strength": strength})
    return rated


def assign_strength_zscore(contexts):
    ppg_values = [row["ppg"] for row in contexts]
    mean = sum(ppg_values) / len(ppg_values)
    # Population standard deviation keeps distribution consistent for fixed 40-row set.
    variance = sum((v - mean) ** 2 for v in ppg_values) / len(ppg_values)
    std = math.sqrt(variance) if variance else 0.0
    rated = []
    for row in contexts:
        if std == 0:
            z = 0.0
        else:
            z = (row["ppg"] - mean) / std
        if z >= 1.5:
            strength = 5
        elif z >= 0.7:
            strength = 4
        elif z > -0.7:
            strength = 3
        elif z > -1.5:
            strength = 2
        else:
            strength = 1
        rated.append({**row, "strength": strength, "z": round(z, 3)})
    return rated


def strength_lookup(rated_contexts):
    lookup = {}
    for row in rated_contexts:
        key = (row["team"], row["venue"])
        lookup[key] = row["strength"]
    return lookup


def render_strength_table(title, contexts, path):
    rows = sorted(contexts, key=lambda r: (-r["strength"], -r["ppg"]))
    row_html = []
    for row in rows:
        strength = row["strength"]
        color = COLOR_SCALE[strength]
        row_html.append(
            "<tr>"
            f"<td>{row['team']}</td>"
            f"<td>{row['venue']}</td>"
            f"<td>{row['matches']}</td>"
            f"<td>{row['points']}</td>"
            f"<td>{row['ppg']:.3f}</td>"
            f"<td style=\"background:{color};font-weight:600;\">{strength}</td>"
            "</tr>"
        )
    html = f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <title>{title}</title>
  <style>
    body {{ font-family: Arial, sans-serif; padding: 24px; background: #f7f7f7; }}
    table {{ border-collapse: collapse; width: 100%; background: #fff; }}
    th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
    th {{ background: #111; color: #fff; }}
  </style>
</head>
<body>
  <h1>{title}</h1>
  <table>
    <thead>
      <tr>
        <th>Team</th>
        <th>Venue</th>
        <th>Matches</th>
        <th>Points</th>
        <th>PPG</th>
        <th>Strength</th>
      </tr>
    </thead>
    <tbody>
      {''.join(row_html)}
    </tbody>
  </table>
</body>
</html>
"""
    path.write_text(html, encoding="utf-8")


def render_form_widget(team, variant, matches, path):
    boxes = []
    for match in matches:
        strength = match.get("opponent_strength")
        color = COLOR_SCALE.get(strength, "#bdbdbd")
        strength_label = "?" if strength is None else str(strength)
        boxes.append(
            "<div class=\"box\">"
            f"<div class=\"score\">{match['score_for']}–{match['score_against']}</div>"
            f"<div class=\"opponent\">{match['opponent']}</div>"
            f"<div class=\"strength\" style=\"background:{color};\">{strength_label}</div>"
            "</div>"
        )
    html = f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <title>{team} Form ({variant})</title>
  <style>
    body {{ font-family: Arial, sans-serif; padding: 24px; background: #f7f7f7; }}
    .strip {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; }}
    .box {{ background: #fff; padding: 12px; border-radius: 8px; text-align: center; box-shadow: 0 1px 4px rgba(0,0,0,0.1); }}
    .score {{ font-size: 18px; font-weight: 700; margin-bottom: 6px; }}
    .opponent {{ font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 8px; }}
    .strength {{ font-weight: 700; color: #000; padding: 6px; border-radius: 4px; }}
  </style>
</head>
<body>
  <h1>{team} Form ({variant})</h1>
  <div class=\"strip\">{''.join(boxes)}</div>
</body>
</html>
"""
    path.write_text(html, encoding="utf-8")


def render_fixtures_page(team, variant, fixtures, avg_strength, path):
    rows = []
    for fixture in fixtures:
        strength = fixture.get("opponent_strength")
        color = COLOR_SCALE.get(strength, "#bdbdbd")
        strength_label = "?" if strength is None else str(strength)
        rows.append(
            "<tr>"
            f"<td>{fixture['opponent']}</td>"
            f"<td>{fixture['venue'].upper()}</td>"
            f"<td style=\"background:{color};font-weight:600;\">{strength_label}</td>"
            "</tr>"
        )
    avg_display = "?" if avg_strength is None else f"{avg_strength:.2f}"
    html = f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <title>{team} Fixtures ({variant})</title>
  <style>
    body {{ font-family: Arial, sans-serif; padding: 24px; background: #f7f7f7; }}
    table {{ border-collapse: collapse; width: 100%; background: #fff; margin-top: 12px; }}
    th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
    th {{ background: #111; color: #fff; }}
  </style>
</head>
<body>
  <h1>{team} Fixtures ({variant})</h1>
  <div>Avg difficulty: {avg_display}</div>
  <table>
    <thead>
      <tr>
        <th>Opponent</th>
        <th>Venue</th>
        <th>Opponent strength</th>
      </tr>
    </thead>
    <tbody>
      {''.join(rows)}
    </tbody>
  </table>
</body>
</html>
"""
    path.write_text(html, encoding="utf-8")


def render_table_block(table_id, contexts):
    rows = sorted(contexts, key=lambda r: (-r["strength"], -r["ppg"]))
    row_html = []
    for idx, row in enumerate(rows, start=1):
        strength = row["strength"]
        color = COLOR_SCALE[strength]
        row_html.append(
            "<tr data-venue=\"{venue}\">"
            "<td>{rank}</td>"
            "<td><span class=\"team-name\">{team}</span></td>"
            "<td>{venue}</td>"
            "<td>{matches}</td>"
            "<td>{points}</td>"
            "<td>{ppg:.3f}</td>"
            "<td style=\"background:{color};font-weight:600;\">{strength}</td>"
            "</tr>".format(
                rank=idx,
                team=row["team"],
                venue=row["venue"],
                matches=row["matches"],
                points=row["points"],
                ppg=row["ppg"],
                strength=strength,
                color=color,
            )
        )
    return (
        f"<div class=\"table-controls\">"
        f"<label><input type=\"radio\" name=\"{table_id}_view\" value=\"all\" checked>Combined</label>"
        f"<label><input type=\"radio\" name=\"{table_id}_view\" value=\"home\">Home</label>"
        f"<label><input type=\"radio\" name=\"{table_id}_view\" value=\"away\">Away</label>"
        f"</div>"
        f"<div class=\"table-wrapper\">"
        f"<table id=\"{table_id}\">"
        "<thead><tr>"
        "<th>#</th><th>Team</th><th>Venue</th><th>Matches</th><th>Points</th><th>PPG</th><th>Strength</th>"
        "</tr></thead>"
        f"<tbody>{''.join(row_html)}</tbody></table>"
        "</div>"
    )


def render_form_block(team, matches):
    boxes = []
    for match in matches:
        strength = match.get("opponent_strength")
        color = COLOR_SCALE.get(strength, "#bdbdbd")
        strength_label = "?" if strength is None else str(strength)
        boxes.append(
            "<div class=\"box\">"
            f"<div class=\"score\">{match['score_for']}–{match['score_against']}</div>"
            f"<div class=\"opponent\">{match['opponent']}</div>"
            f"<div class=\"strength\" style=\"background:{color};\">{strength_label}</div>"
            "</div>"
        )
    return (
        f"<div class=\"form-card\">"
        f"<div class=\"card-title\"><span class=\"team-name\">{team}</span></div>"
        f"<div class=\"strip\">{''.join(boxes)}</div>"
        "</div>"
    )


def render_fixtures_block(team, payload):
    rows = []
    strength_counts = {1: 0, 5: 0}
    for fixture in payload["fixtures"]:
        strength = fixture.get("opponent_strength")
        color = COLOR_SCALE.get(strength, "#bdbdbd")
        strength_label = "?" if strength is None else str(strength)
        if strength in strength_counts:
            strength_counts[strength] += 1
        rows.append(
            "<tr>"
            f"<td><span class=\"team-name\">{fixture['opponent']}</span></td>"
            f"<td>{fixture['venue'].upper()}</td>"
            f"<td style=\"background:{color};font-weight:600;\">{strength_label}</td>"
            "</tr>"
        )
    avg_display = "?" if payload["avg_strength"] is None else f"{payload['avg_strength']:.2f}"
    counts_display = f"<strong>1s: {strength_counts[1]}</strong> · 5s: {strength_counts[5]}"
    return (
        f"<div class=\"card\">"
        f"<div class=\"card-title\">{team} fixtures</div>"
        f"<div class=\"avg\">Avg difficulty: {avg_display} · {counts_display}</div>"
        f"<table class=\"fixtures-table\">"
        "<thead><tr><th>Opponent</th><th>Venue</th><th>Strength</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
        "</div>"
    )


def outcome_from_score(score_for, score_against):
    if score_for > score_against:
        return "win"
    if score_for < score_against:
        return "loss"
    return "draw"


def outcome_label(outcome):
    return {"win": "W", "draw": "D", "loss": "L"}[outcome]


def combined_label(outcome, strength, fairness):
    if outcome == "win" and fairness == "overperformed":
        return "Good win"
    if outcome == "win" and fairness == "fair":
        return "Expected win"
    if outcome == "win":
        return "Scrappy win"
    if outcome == "draw" and fairness == "overperformed":
        return "Good draw"
    if outcome == "draw" and fairness == "fair":
        return "Fair draw"
    if outcome == "draw":
        return "Lucky draw"
    if outcome == "loss" and fairness == "underperformed":
        return "Bad loss"
    if outcome == "loss" and fairness == "fair":
        return "Expected loss"
    return "Unlucky loss"


def render_form_exploration(form_payload):
    def tile_class(outcome):
        return f"tile outcome-{outcome}"

    def strength_badge(strength):
        label = "S?" if strength is None else f"S{strength}"
        return f"<span class=\"strength-badge\">{label}</span>"

    def fairness_glyph(fairness):
        return {"overperformed": "+", "fair": "≈", "underperformed": "–"}.get(fairness, "?")

    def tooltip_block(match):
        strength_label = "Unknown" if match["opponent_strength"] is None else f"{match['opponent_strength']} / 5"
        fairness_label = match["fairness"].capitalize()
        return (
            "<div class=\"tooltip\">"
            f"<div><strong>Strength</strong>: {strength_label} (opponent difficulty)</div>"
            f"<div><strong>Fairness</strong>: {fairness_label}</div>"
            "</div>"
        )

    def render_variant(title, renderer):
        blocks = []
        for team, matches in form_payload.items():
            tiles = "".join(renderer(match) for match in matches)
            blocks.append(
                "<div class=\"team-block\">"
                f"<div class=\"team-title\">{team}</div>"
                f"<div class=\"tile-row\">{tiles}</div>"
                "</div>"
            )
        return (
            "<div class=\"variant\">"
            f"<div class=\"variant-title\">{title}</div>"
            f"{''.join(blocks)}"
            "</div>"
        )

    def variant_one(match):
        outcome = match["outcome"]
        return (
            f"<div class=\"{tile_class(outcome)}\">"
            f"<div class=\"score\">{match['score_for']}–{match['score_against']}</div>"
            f"<div class=\"opponent\">{match['opponent_short']}</div>"
            f"{strength_badge(match['opponent_strength'])}"
            "</div>"
        )

    def variant_two(match):
        outcome = match["outcome"]
        return (
            f"<div class=\"{tile_class(outcome)}\">"
            f"<div class=\"score\">{match['score_for']}–{match['score_against']}"
            f"<span class=\"glyph\">{fairness_glyph(match['fairness'])}</span></div>"
            f"<div class=\"opponent\">{match['opponent_short']}</div>"
            f"{strength_badge(match['opponent_strength'])}"
            "</div>"
        )

    def variant_three(match):
        outcome = match["outcome"]
        return (
            f"<div class=\"{tile_class(outcome)} tooltip-wrap\">"
            f"<div class=\"score\">{match['score_for']}–{match['score_against']}</div>"
            f"<div class=\"opponent\">{match['opponent_short']}</div>"
            f"{tooltip_block(match)}"
            "</div>"
        )

    def variant_four(match):
        outcome = match["outcome"]
        return (
            f"<div class=\"result-tile {tile_class(outcome)}\">"
            f"{outcome_label(outcome)} {match['score_for']}–{match['score_against']}"
            "</div>"
        )

    def variant_four_context(match):
        return (
            "<div class=\"context-tile\">"
            f"{strength_badge(match['opponent_strength'])}"
            f"<span class=\"glyph\">{fairness_glyph(match['fairness'])}</span>"
            "</div>"
        )

    def variant_five(match):
        outcome = match["outcome"]
        label = combined_label(outcome, match["opponent_strength"], match["fairness"])
        return (
            f"<div class=\"{tile_class(outcome)}\">"
            f"<div class=\"score\">{match['score_for']}–{match['score_against']}</div>"
            f"<div class=\"opponent\">{match['opponent_short']}</div>"
            f"<div class=\"combined\">{label}</div>"
            f"{strength_badge(match['opponent_strength'])}"
            "</div>"
        )

    variant_one_block = render_variant("Variant 1 — Baseline Outcome + Strength", variant_one)
    variant_two_block = render_variant("Variant 2 — Outcome + Strength + Fairness Glyph", variant_two)
    variant_three_block = render_variant("Variant 3 — Tooltip-First Context", variant_three)

    # Variant 4 requires two rows per team.
    variant_four_blocks = []
    for team, matches in form_payload.items():
        result_tiles = "".join(variant_four(match) for match in matches)
        context_tiles = "".join(variant_four_context(match) for match in matches)
        variant_four_blocks.append(
            "<div class=\"team-block\">"
            f"<div class=\"team-title\">{team}</div>"
            f"<div class=\"tile-row\">{result_tiles}</div>"
            f"<div class=\"tile-row context-row\">{context_tiles}</div>"
            "</div>"
        )
    variant_four_block = (
        "<div class=\"variant\">"
        "<div class=\"variant-title\">Variant 4 — Split Result / Context Rows</div>"
        f"{''.join(variant_four_blocks)}"
        "</div>"
    )

    variant_five_block = render_variant("Variant 5 — Combined Interpretation Mode", variant_five)

    return (
        "<div class=\"form-exploration\">"
        "<h1>Form Interpretation Experiments</h1>"
        "<p>Below are several different ways of presenting recent form, opponent difficulty, and performance context. "
        "Each section uses the same data but different visual treatments.</p>"
        f"{variant_one_block}"
        f"{variant_two_block}"
        f"{variant_three_block}"
        f"{variant_four_block}"
        f"{variant_five_block}"
        "</div>"
    )


def select_last_five(matches, mode):
    if mode == "combined":
        filtered = matches
    else:
        filtered = [match for match in matches if match["venue"] == mode]
    if len(filtered) <= 5:
        return filtered
    return filtered[-5:]


def render_dashboard(variants_payload, form_exploration_payload, output_path):
    variant_explanations = {
        "percentile": (
            "Percentile buckets. Strength 5: 80–100%, Strength 4: 60–80%, "
            "Strength 3: 40–60%, Strength 2: 20–40%, Strength 1: 0–20%. "
            "Tie-aware boundaries by PPG.<br>"
            "ELI5: We line everyone up by points per game and split them into five equally sized groups."
        ),
        "zscore": (
            "Z-score buckets. Strength 5: z ≥ 1.5, Strength 4: 0.7 ≤ z < 1.5, "
            "Strength 3: -0.7 < z < 0.7, Strength 2: -1.5 < z ≤ -0.7, "
            "Strength 1: z ≤ -1.5. Population standard deviation.<br>"
            "ELI5: We compare each team’s points per game to the average and rate how far above or below it is."
        ),
        "shaped": (
            "Shaped percentiles. Strength 5: 90–100%, Strength 4: 65–90%, "
            "Strength 3: 35–65%, Strength 2: 10–35%, Strength 1: 0–10%. "
            "Tie-aware boundaries by PPG.<br>"
            "ELI5: We use smaller top and bottom groups so only the very best and worst get 5s and 1s."
        ),
    }
    tab_buttons = []
    tab_panels = []
    for idx, (variant, payload) in enumerate(variants_payload.items()):
        active_class = "active" if idx == 0 else ""
        tab_buttons.append(
            f"<button class=\"tab-button {active_class}\" data-tab=\"tab-{variant}\">{variant.title()}</button>"
        )
        explanation = variant_explanations.get(variant, "")
        panel_sections = []
        for view_key in ("current", "combined"):
            view_payload = payload[view_key]
            table_id = f"{variant}-{view_key}-table"
            table_block = render_table_block(table_id, view_payload["ratings"])
            form_pairs = []
            form_map = view_payload["form"]
            form_modes = ["combined", "home", "away"]
            for home_team, away_team in (("Arsenal", "Brentford"), ("Newcastle United", "Tottenham Hotspur")):
                if home_team in form_map and away_team in form_map:
                    mode_blocks = []
                    for mode in form_modes:
                        home_matches = select_last_five(form_map[home_team], "home" if mode == "home" else "combined" if mode == "combined" else "away")
                        away_matches = select_last_five(form_map[away_team], "away" if mode == "away" else "combined" if mode == "combined" else "home")
                        mode_blocks.append(
                            "<div class=\"form-mode\" data-form-mode=\"{mode}\">"
                            "{home}{away}"
                            "</div>".format(
                                mode=mode,
                                home=render_form_block(home_team, home_matches),
                                away=render_form_block(away_team, away_matches),
                            )
                        )
                    form_pairs.append(
                        "<div class=\"form-pair\">"
                        "<div class=\"form-controls\">"
                        "<label><input type=\"radio\" name=\"form_{pair}\" value=\"combined\" checked>Combined</label>"
                        "<label><input type=\"radio\" name=\"form_{pair}\" value=\"home\">Home</label>"
                        "<label><input type=\"radio\" name=\"form_{pair}\" value=\"away\">Away</label>"
                        "</div>"
                        "{modes}"
                        "</div>".format(
                            pair=f"{variant}-{view_key}-{home_team}",
                            modes="".join(mode_blocks),
                        )
                    )
            form_blocks = "".join(form_pairs)
            original_form_blocks = []
            for home_team, away_team in (("Arsenal", "Brentford"), ("Newcastle United", "Tottenham Hotspur")):
                if home_team in form_map and away_team in form_map:
                    original_form_blocks.append(
                        "<div class=\"form-pair\">"
                        f"{render_form_block(home_team, select_last_five(form_map[home_team], 'combined'))}"
                        f"{render_form_block(away_team, select_last_five(form_map[away_team], 'combined'))}"
                        "</div>"
                    )
            original_form_section = "".join(original_form_blocks)
            fixtures_blocks = "".join(
                render_fixtures_block(team, fixture_payload)
                for team, fixture_payload in view_payload["fixtures"].items()
            )
            label = "This season" if view_key == "current" else "This + last season"
            panel_sections.append(
                f"<div class=\"variant-panel\" data-view=\"{view_key}\">"
                f"<h2 class=\"section-title\">Table</h2>"
                f"<h3>{label}</h3>"
                f"{table_block}"
                f"<h2 class=\"section-title\">Remaining fixtures</h2>"
                f"<div class=\"section-grid\">{fixtures_blocks}</div>"
                f"<h2 class=\"section-title\">Last 5 form</h2>"
                f"<div class=\"form-grid\">{form_blocks}</div>"
                f"<h2 class=\"section-title\">Original form</h2>"
                f"<div class=\"form-grid\">{original_form_section}</div>"
                "</div>"
            )
        tab_panels.append(
            f"<div class=\"tab-panel {active_class}\" id=\"tab-{variant}\">"
            f"<div class=\"tab-explanation\">{explanation}</div>"
            f"<div class=\"panel-grid\">{''.join(panel_sections)}</div>"
            "</div>"
        )

    tab_buttons.append(
        "<button class=\"tab-button\" data-tab=\"tab-form\">Form exploration</button>"
    )
    tab_panels.append(
        f"<div class=\"tab-panel\" id=\"tab-form\">"
        f"{form_exploration_payload}"
        "</div>"
    )

    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>PPG Strength Dashboard</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
    body {{ font-family: 'Inter', sans-serif; margin: 0; background: #f6f7fb; color: #111; }}
    header {{ padding: 20px 24px; background: #0f1013; color: #fff; }}
    h1 {{ margin: 0 0 8px; font-size: 20px; }}
    .controls {{ display: flex; gap: 16px; align-items: center; }}
    .tabs {{ display: flex; gap: 8px; padding: 16px 24px 0; }}
    .tab-button {{ border: 1px solid #e3e6ed; background: #fff; padding: 10px 16px; border-radius: 999px; cursor: pointer; box-shadow: 0 1px 2px rgba(15,16,19,0.04); }}
    .tab-button.active {{ background: #0f1013; color: #fff; border-color: #0f1013; }}
    .tab-panel {{ display: none; padding: 16px 24px 32px; }}
    .tab-panel.active {{ display: block; }}
    .tab-explanation {{ margin-bottom: 12px; font-size: 13px; color: #444; }}
    .panel-grid {{ display: grid; grid-template-columns: 1fr; gap: 24px; }}
    .panel-grid.split {{ grid-template-columns: 1fr 1fr; }}
    .variant-panel {{ background: #fff; padding: 18px; border-radius: 12px; box-shadow: 0 12px 30px rgba(15,16,19,0.08); border: 1px solid #eef0f5; }}
    .table-controls {{ display: flex; gap: 12px; margin-bottom: 8px; font-size: 12px; }}
    .table-wrapper {{ width: 100%; overflow: hidden; border-radius: 12px; }}
    table {{ width: 100%; border-collapse: separate; border-spacing: 0; background: #fff; border: 1px solid #eef0f5; table-layout: fixed; }}
    th, td {{ border-bottom: 1px solid #eef0f5; padding: 8px; text-align: left; font-size: 12px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
    th {{ background: #f5f6fa; color: #111; font-weight: 600; }}
    tbody tr:last-child td {{ border-bottom: 0; }}
    .team-name {{ font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; display: inline-block; max-width: 160px; vertical-align: bottom; }}
    .section-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; margin-top: 16px; }}
    .section-header {{ margin-top: 16px; font-weight: 700; text-transform: uppercase; font-size: 12px; letter-spacing: 1px; }}
    .section-title {{ margin: 24px 0 12px; font-size: 36px; font-weight: 600; text-transform: none; }}
    .card {{ background: #fff; border: 1px solid #eef0f5; padding: 12px; border-radius: 10px; box-shadow: 0 8px 18px rgba(15,16,19,0.06); }}
    .card-title {{ font-weight: 700; margin-bottom: 8px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
    .form-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-top: 8px; }}
    .form-pair {{ display: grid; grid-template-columns: 1fr; gap: 12px; }}
    .form-controls {{ display: flex; gap: 10px; font-size: 12px; }}
    .form-mode {{ display: none; gap: 12px; grid-template-columns: 1fr; }}
    .form-mode.active {{ display: grid; }}
    .form-card {{ background: #fff; border: 1px solid #eef0f5; padding: 12px; border-radius: 10px; box-shadow: 0 8px 18px rgba(15,16,19,0.06); }}
    .strip {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 6px; }}
    .box {{ background: #fff; padding: 6px; border-radius: 8px; text-align: center; border: 1px solid #eef0f5; }}
    .score {{ font-weight: 700; font-size: 14px; }}
    .opponent {{ font-size: 10px; text-transform: uppercase; letter-spacing: 0.4px; margin-top: 2px; }}
    .strength {{ margin-top: 6px; font-weight: 700; padding: 4px; border-radius: 6px; }}
    .avg {{ font-size: 12px; margin-bottom: 6px; }}
    .fixtures-table th, .fixtures-table td {{ font-size: 11px; }}
    @media (max-width: 900px) {{
      .panel-grid.split {{ grid-template-columns: 1fr; }}
      .form-grid {{ grid-template-columns: 1fr; }}
    }}
    .panel-grid.split th, .panel-grid.split td {{ padding: 6px; font-size: 11px; }}
    .panel-grid.split .team-name {{ max-width: 110px; }}
    .panel-grid.split table th:nth-child(1),
    .panel-grid.split table td:nth-child(1) {{ width: 32px; }}
    .panel-grid.split table th:nth-child(2),
    .panel-grid.split table td:nth-child(2) {{ width: 140px; }}
    .panel-grid.split table th:nth-child(3),
    .panel-grid.split table td:nth-child(3) {{ width: 60px; }}
    .panel-grid.split table th:nth-child(4),
    .panel-grid.split table td:nth-child(4) {{ width: 60px; }}
    .panel-grid.split table th:nth-child(5),
    .panel-grid.split table td:nth-child(5) {{ width: 60px; }}
    .panel-grid.split table th:nth-child(6),
    .panel-grid.split table td:nth-child(6) {{ width: 70px; }}
    .panel-grid.split table th:nth-child(7),
    .panel-grid.split table td:nth-child(7) {{ width: 70px; }}
    .form-exploration {{ padding: 16px 24px 40px; }}
    .form-exploration h1 {{ font-size: 28px; margin: 0 0 8px; }}
    .form-exploration p {{ color: #444; margin: 0 0 20px; }}
    .variant {{ margin-bottom: 28px; padding: 16px; background: #fff; border: 1px solid #eef0f5; border-radius: 12px; box-shadow: 0 10px 24px rgba(15,16,19,0.06); }}
    .variant-title {{ font-weight: 700; margin-bottom: 12px; }}
    .team-block {{ margin-bottom: 16px; }}
    .team-title {{ font-weight: 600; margin-bottom: 8px; }}
    .tile-row {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 8px; }}
    .tile {{ border-radius: 10px; padding: 8px; color: #111; position: relative; min-height: 64px; }}
    .tile .score {{ font-weight: 700; font-size: 14px; }}
    .tile .opponent {{ font-size: 11px; text-transform: uppercase; letter-spacing: 0.4px; margin-top: 4px; }}
    .tile .combined {{ font-size: 11px; margin-top: 6px; }}
    .strength-badge {{ display: inline-block; margin-top: 6px; padding: 2px 6px; border-radius: 999px; background: #f0f2f7; font-size: 11px; }}
    .glyph {{ margin-left: 6px; font-size: 12px; }}
    .outcome-win {{ background: #c8e6c9; }}
    .outcome-draw {{ background: #e0e0e0; }}
    .outcome-loss {{ background: #ffcdd2; }}
    .tooltip-wrap {{ cursor: default; }}
    .tooltip {{ display: none; position: absolute; left: 8px; right: 8px; bottom: -64px; background: #111; color: #fff; padding: 8px; border-radius: 8px; font-size: 11px; }}
    .tooltip-wrap:hover .tooltip {{ display: block; }}
    .context-row {{ margin-top: 6px; }}
    .context-tile {{ background: #f4f6fb; border-radius: 10px; padding: 6px; display: flex; align-items: center; gap: 6px; }}
    .result-tile {{ border-radius: 10px; padding: 8px; font-weight: 700; }}
    @media (max-width: 900px) {{
      .tile-row {{ grid-template-columns: repeat(2, 1fr); }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>PPG Strength Dashboard</h1>
    <div class="controls">
      <label><input type="checkbox" id="splitToggle"> Split view (this season vs combined)</label>
    </div>
  </header>
  <div class="tabs">
    {''.join(tab_buttons)}
  </div>
  {''.join(tab_panels)}
  <script>
    const splitToggle = document.getElementById('splitToggle');
    const tabButtons = document.querySelectorAll('.tab-button');
    const tabPanels = document.querySelectorAll('.tab-panel');

    function updateSplit() {{
      tabPanels.forEach(panel => {{
        const grid = panel.querySelector('.panel-grid');
        const combinedPanel = panel.querySelector('[data-view=\"combined\"]');
        if (splitToggle.checked) {{
          grid.classList.add('split');
          combinedPanel.style.display = 'block';
        }} else {{
          grid.classList.remove('split');
          combinedPanel.style.display = 'none';
        }}
      }});
    }}

    function initFormSelectors() {{
      document.querySelectorAll('.form-pair').forEach(pair => {{
        const controls = pair.querySelectorAll('input[type=\"radio\"]');
        const modes = pair.querySelectorAll('.form-mode');
        const setMode = (value) => {{
          modes.forEach(mode => {{
            mode.classList.toggle('active', mode.dataset.formMode === value);
          }});
        }};
        controls.forEach(control => {{
          control.addEventListener('change', () => setMode(control.value));
        }});
        setMode('combined');
      }});
    }}

    function applyVenueFilter(tableId, view) {{
      const table = document.getElementById(tableId);
      if (!table) return;
      table.querySelectorAll('tbody tr').forEach(row => {{
        if (view === 'all') {{
          row.style.display = '';
        }} else {{
          row.style.display = row.dataset.venue === view ? '' : 'none';
        }}
      }});
    }}

    document.querySelectorAll('.table-controls').forEach(control => {{
      const name = control.querySelector('input').name;
      const tableId = name.replace('_view', '');
      control.addEventListener('change', (event) => {{
        applyVenueFilter(tableId, event.target.value);
      }});
    }});

    tabButtons.forEach(button => {{
      button.addEventListener('click', () => {{
        tabButtons.forEach(btn => btn.classList.remove('active'));
        tabPanels.forEach(panel => panel.classList.remove('active'));
        button.classList.add('active');
        document.getElementById(button.dataset.tab).classList.add('active');
      }});
    }});

    splitToggle.addEventListener('change', updateSplit);
    updateSplit();
    initFormSelectors();
  </script>
</body>
</html>
"""
    output_path.write_text(html, encoding="utf-8")


def team_file_key(team):
    return TEAM_FILE_ALIASES.get(team, team)


def annotate_form(recent_form, strength_map, issues):
    annotated = {}
    for team, matches in recent_form.items():
        annotated_matches = []
        for match in matches:
            opponent = normalise_name(match["opponent"])
            if match["venue"] == "home":
                opponent_context = "away"
            else:
                opponent_context = "home"
            strength = strength_map.get((opponent, opponent_context))
            if strength is None:
                issues.append({
                    "type": "missing_strength",
                    "team": team,
                    "opponent": opponent,
                    "context": opponent_context,
                })
            annotated_matches.append({
                **match,
                "opponent": opponent,
                "opponent_strength": strength,
                "opponent_venue_context_used": opponent_context,
            })
        annotated[team] = annotated_matches
    return annotated


def annotate_fixtures(fixtures, strength_map, issues):
    annotated = {}
    for team, items in fixtures.items():
        annotated_items = []
        strengths = []
        for fixture in items:
            opponent = normalise_name(fixture["opponent"])
            if fixture["venue"] == "home":
                opponent_context = "away"
            else:
                opponent_context = "home"
            strength = strength_map.get((opponent, opponent_context))
            if strength is None:
                issues.append({
                    "type": "missing_strength",
                    "team": team,
                    "opponent": opponent,
                    "context": opponent_context,
                })
            else:
                strengths.append(strength)
            annotated_items.append({
                **fixture,
                "opponent": opponent,
                "opponent_strength": strength,
                "opponent_venue_context_used": opponent_context,
            })
        avg_strength = round(sum(strengths) / len(strengths), 2) if strengths else None
        annotated[team] = {
            "avg_strength": avg_strength,
            "fixtures": annotated_items,
        }
    return annotated


def main():
    home_table = load_json(DATA_DIR / "pl_home_table.json")
    away_table = load_json(DATA_DIR / "pl_away_table.json")
    last_home_table = load_json(DATA_DIR / "pl_last_home_table.json")
    last_away_table = load_json(DATA_DIR / "pl_last_away_table.json")
    recent_form = load_json(DATA_DIR / "recent_form.json")
    upcoming_fixtures = load_json(DATA_DIR / "upcoming_fixtures.json")

    contexts = build_ppg_contexts(home_table, away_table)
    write_json(DATA_DIR / "ppg_contexts.json", contexts)

    all_issues = []
    combined_contexts = combine_contexts(contexts, last_home_table, last_away_table, all_issues)
    write_json(DATA_DIR / "ppg_contexts_combined.json", combined_contexts)

    percentile_ratings = assign_strength_percentile(contexts, [0.2, 0.4, 0.6, 0.8])
    zscore_ratings = assign_strength_zscore(contexts)
    shaped_ratings = assign_strength_percentile(contexts, [0.1, 0.35, 0.65, 0.9])

    percentile_combined = assign_strength_percentile(combined_contexts, [0.2, 0.4, 0.6, 0.8])
    zscore_combined = assign_strength_zscore(combined_contexts)
    shaped_combined = assign_strength_percentile(combined_contexts, [0.1, 0.35, 0.65, 0.9])

    write_json(DATA_DIR / "strength_ratings_percentile.json", percentile_ratings)
    write_json(DATA_DIR / "strength_ratings_zscore.json", zscore_ratings)
    write_json(DATA_DIR / "strength_ratings_shaped.json", shaped_ratings)
    write_json(DATA_DIR / "strength_ratings_percentile_combined.json", percentile_combined)
    write_json(DATA_DIR / "strength_ratings_zscore_combined.json", zscore_combined)
    write_json(DATA_DIR / "strength_ratings_shaped_combined.json", shaped_combined)

    HTML_DIR.mkdir(parents=True, exist_ok=True)
    # Clean up legacy fixture filenames that used full team names with spaces.
    for legacy_team in TEAM_FILE_ALIASES.keys():
        for legacy_path in HTML_DIR.glob(f"fixtures_{legacy_team}_*.html"):
            legacy_path.unlink(missing_ok=True)
    render_strength_table(
        "Strength Ratings - Percentile Buckets",
        percentile_ratings,
        HTML_DIR / "strength_percentile.html",
    )
    render_strength_table(
        "Strength Ratings - Z-score Buckets",
        zscore_ratings,
        HTML_DIR / "strength_zscore.html",
    )
    render_strength_table(
        "Strength Ratings - Shaped Percentiles",
        shaped_ratings,
        HTML_DIR / "strength_shaped.html",
    )

    variants = {
        "percentile": {"current": percentile_ratings, "combined": percentile_combined},
        "zscore": {"current": zscore_ratings, "combined": zscore_combined},
        "shaped": {"current": shaped_ratings, "combined": shaped_combined},
    }

    dashboard_payload = {}
    for variant, ratings in variants.items():
        dashboard_payload[variant] = {}
        for view_key, view_ratings in ratings.items():
            strength_map = strength_lookup(view_ratings)
            annotated_form = annotate_form(recent_form, strength_map, all_issues)
            annotated_fixtures = annotate_fixtures(upcoming_fixtures, strength_map, all_issues)

            suffix = "" if view_key == "current" else "_combined"
            write_json(OUT_DIR / f"form_annotated_{variant}{suffix}.json", annotated_form)
            write_json(OUT_DIR / f"fixtures_annotated_{variant}{suffix}.json", annotated_fixtures)

            if view_key == "current":
                for team, matches in annotated_form.items():
                    render_form_widget(
                        team,
                        variant,
                        matches,
                        HTML_DIR / f"form_{team}_{variant}.html",
                    )

                for team, payload in annotated_fixtures.items():
                    render_fixtures_page(
                        team,
                        variant,
                        payload["fixtures"],
                        payload["avg_strength"],
                        HTML_DIR / f"fixtures_{team_file_key(team)}_{variant}.html",
                    )

            dashboard_payload[variant][view_key] = {
                "ratings": view_ratings,
                "form": annotated_form,
                "fixtures": annotated_fixtures,
            }

    shaped_strength_map = strength_lookup(shaped_ratings)
    shaped_form = annotate_form(recent_form, shaped_strength_map, all_issues)
    fairness_map = {
        "Arsenal": ["fair", "fair", "underperformed", "fair", "overperformed"],
        "Brentford": ["fair", "fair", "underperformed", "overperformed", "fair"],
    }
    form_exploration_payload = {}
    for team in ("Arsenal", "Brentford"):
        matches = select_last_five(shaped_form.get(team, []), "combined")
        fairness_labels = fairness_map.get(team, [])
        enriched = []
        for idx, match in enumerate(matches):
            enriched.append({
                **match,
                "opponent_short": short_team_name(match["opponent"]),
                "outcome": outcome_from_score(match["score_for"], match["score_against"]),
                "fairness": fairness_labels[idx] if idx < len(fairness_labels) else "fair",
            })
        form_exploration_payload[team] = enriched

    lovable_payload = {
        "variants": dashboard_payload,
        "form_exploration": form_exploration_payload,
    }
    write_json(OUT_DIR / "lovable_payload.json", lovable_payload)

    render_dashboard(
        dashboard_payload,
        render_form_exploration(form_exploration_payload),
        HTML_DIR / "strength_dashboard.html",
    )

    if all_issues:
        write_json(OUT_DIR / "_issues.json", all_issues)


if __name__ == "__main__":
    main()
