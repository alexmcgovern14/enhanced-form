#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

try:
    from openai_responses_client import OpenAIError, extract_output_text, load_config, responses_create
except ModuleNotFoundError:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from openai_responses_client import OpenAIError, extract_output_text, load_config, responses_create


Label = Literal[
    "deserved win",
    "lucky win",
    "fair draw",
    "unfair draw",
    "unlucky loss",
    "deserved loss",
]


@dataclass(frozen=True)
class SplitStats:
    matches: int
    wins: int
    draws: int
    losses: int
    goals_for: int
    goals_against: int
    xg_for: float
    xg_against: float
    goals_minus_xg_for: float
    goals_minus_xg_against: float
    opponent_strength: dict[str, int]


def _round2(x: float) -> float:
    return float(f"{x:.2f}")


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", name.strip().lower())
    slug = re.sub(r"_+", "_", slug).strip("_")
    if not slug:
        slug = "team"
    return slug


def _result(score_for: int, score_against: int) -> Literal["win", "draw", "loss"]:
    if score_for > score_against:
        return "win"
    if score_for < score_against:
        return "loss"
    return "draw"


def _sentence_flags(narrative: str) -> dict[str, bool]:
    s = narrative.casefold()
    return {
        "representative": ("felt representative" in s) or ("broadly matched" in s),
        "not_reflect": ("did not fully reflect" in s) or ("harsh" in s) or ("unfortunate" in s),
        "dominant": ("on top" in s) or ("dominant" in s) or ("clearer chances" in s),
    }


def assess_match(match: dict[str, Any]) -> dict[str, Any]:
    gf = int(match["score"]["for"])
    ga = int(match["score"]["against"])
    xgf = float(match["xg"]["for"])
    xga = float(match["xg"]["against"])
    red_for = int(match["red_cards"]["for"])
    red_against = int(match["red_cards"]["against"])

    xg_diff = xgf - xga
    goal_diff = gf - ga
    res = _result(gf, ga)

    evidence: list[str] = []
    confidence: Literal["low", "medium", "high"] = "medium"

    if abs(xg_diff) >= 0.9:
        confidence = "high"
    elif abs(xg_diff) <= 0.25:
        confidence = "low"

    if xg_diff >= 0.35:
        evidence.append("xg_advantage")
    elif xg_diff <= -0.35:
        evidence.append("xg_deficit")
    else:
        evidence.append("xg_even")

    finishing_delta = (gf - xgf) - (ga - xga)
    if finishing_delta >= 1.0:
        evidence.append("clinical_finishing")
    elif finishing_delta <= -1.0:
        evidence.append("poor_finishing")
    else:
        evidence.append("finishing_near_xg")

    if red_for or red_against:
        evidence = [evidence[0], "red_card_impact"]
        confidence = "medium" if confidence == "high" else confidence

    label: Label
    if res == "win":
        if xg_diff >= 0.35:
            label = "deserved win"
        elif xg_diff <= -0.35:
            label = "lucky win"
        else:
            label = "deserved win"
            confidence = "low"
    elif res == "loss":
        if xg_diff >= 0.35:
            label = "unlucky loss"
        elif xg_diff <= -0.35:
            label = "deserved loss"
        else:
            label = "deserved loss"
            confidence = "low"
    else:  # draw
        if xg_diff >= 0.35:
            label = "unfair draw"
        else:
            label = "fair draw"
            if xg_diff <= -0.6:
                confidence = "low"

    flags = _sentence_flags(str(match.get("narrative_summary", "")))
    if flags["not_reflect"] and label in ("lucky win", "unlucky loss", "unfair draw"):
        narrative_alignment = "supports"
    elif flags["representative"] and label in ("deserved win", "deserved loss", "fair draw"):
        narrative_alignment = "supports"
    elif flags["representative"] and label in ("lucky win", "unlucky loss", "unfair draw"):
        narrative_alignment = "contradicts"
    elif flags["not_reflect"] and label in ("deserved win", "deserved loss", "fair draw"):
        narrative_alignment = "contradicts"
    else:
        narrative_alignment = "aligned"

    # Keep output aligned with Sample_json_structure.json fields.
    return {
        "label": label,
        "confidence": confidence,
        "primary_evidence": evidence[:2],
        "narrative_alignment": narrative_alignment,
    }


def assess_match_llm(
    model: str,
    team_form: dict[str, Any],
    match_index: int,
) -> dict[str, Any]:
    config = load_config(model)
    if not config:
        raise OpenAIError("OPENAI_API_KEY is not set")

    match = team_form["form"]["recent_matches"][match_index]
    context = {
        "team": team_form["form"]["entity"]["team_name"],
        "season_context": {
            "competition": team_form["form"]["season_context"]["competition"],
            "league_ppg_p25": team_form["form"]["season_context"]["league_ppg_p25"],
            "league_ppg_p75": team_form["form"]["season_context"]["league_ppg_p75"],
        },
        "match": match,
        "allowed_labels": [
            "deserved win",
            "lucky win",
            "fair draw",
            "unfair draw",
            "unlucky loss",
            "deserved loss",
        ],
        "allowed_confidence": ["low", "medium", "high"],
        "allowed_narrative_alignment": ["supports", "contradicts", "aligned"],
    }

    system_prompt = Path("System_prompts/02_match_assessor.md").read_text(encoding="utf-8").strip()

    schema = {
        "name": "statistical_assessment",
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "label": {"type": "string", "enum": list(context["allowed_labels"])},
                "confidence": {"type": "string", "enum": list(context["allowed_confidence"])},
                "primary_evidence": {"type": "array", "items": {"type": "string"}, "minItems": 2, "maxItems": 2},
                "narrative_alignment": {"type": "string", "enum": list(context["allowed_narrative_alignment"])},
            },
            "required": ["label", "confidence", "primary_evidence", "narrative_alignment"],
        },
        "strict": True,
    }

    payload = {
        "model": config.model,
        "input": [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": "Return ONLY the statistical_assessment object for the match at form.recent_matches[match_index].\n\n"
                + json.dumps({"match_index": match_index, **context}, ensure_ascii=False),
            },
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": schema["name"],
                "schema": schema["schema"],
                "strict": True,
            }
        },
    }

    resp = responses_create(config, payload)
    text = extract_output_text(resp)
    if not text:
        raise OpenAIError("Empty response text")
    return json.loads(text)


def _split_stats(matches: list[dict[str, Any]]) -> SplitStats:
    wins = draws = losses = 0
    gf = ga = 0
    xgf = xga = 0.0
    strength = {str(i): 0 for i in range(1, 6)}

    for m in matches:
        m_gf = int(m["score"]["for"])
        m_ga = int(m["score"]["against"])
        gf += m_gf
        ga += m_ga
        res = _result(m_gf, m_ga)
        if res == "win":
            wins += 1
        elif res == "draw":
            draws += 1
        else:
            losses += 1

        xgf += float(m["xg"]["for"])
        xga += float(m["xg"]["against"])

        raw_tier = m["opponent"].get("strength_tier", 3)
        if isinstance(raw_tier, str):
            legacy_map = {"weak": "1", "average": "3", "strong": "5"}
            tier = legacy_map.get(raw_tier.casefold(), raw_tier)
        else:
            tier = str(raw_tier)
        if tier in strength:
            strength[tier] += 1

    return SplitStats(
        matches=len(matches),
        wins=wins,
        draws=draws,
        losses=losses,
        goals_for=gf,
        goals_against=ga,
        xg_for=_round2(xgf),
        xg_against=_round2(xga),
        goals_minus_xg_for=_round2(gf - xgf),
        goals_minus_xg_against=_round2(ga - xga),
        opponent_strength=strength,
    )


def _match_rows(matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for m in matches:
        gf = int(m["score"]["for"])
        ga = int(m["score"]["against"])
        rows.append(
            {
                "date": m["date"],
                "home_away": m["home_away"],
                "opponent": m["opponent"]["name"],
                "result": _result(gf, ga),
                "score": {"for": gf, "against": ga},
                "xg": {"for": float(m["xg"]["for"]), "against": float(m["xg"]["against"])},
                "assessment": m.get("statistical_assessment", {}).get("label", "TBC"),
            }
        )
    return rows


def analyze_form(team_form: dict[str, Any]) -> dict[str, Any]:
    matches: list[dict[str, Any]] = list(team_form["form"]["recent_matches"])
    matches_sorted = sorted(matches, key=lambda m: m["date"], reverse=True)

    home = [m for m in matches_sorted if m["home_away"] == "home"]
    away = [m for m in matches_sorted if m["home_away"] == "away"]
    recent5 = matches_sorted[:5]

    home_stats = _split_stats(home)
    away_stats = _split_stats(away)
    recent5_stats = _split_stats(recent5)

    def trends(stats: SplitStats) -> dict[str, Any]:
        finishing = "underperforming xG" if stats.goals_minus_xg_for <= -1.0 else ("overperforming xG" if stats.goals_minus_xg_for >= 1.0 else "finishing near xG")
        defending = "conceding more than xG" if stats.goals_minus_xg_against >= 1.0 else ("conceding fewer than xG" if stats.goals_minus_xg_against <= -1.0 else "conceding near xG")
        return {"finishing_efficiency": finishing, "defensive_efficiency": defending}

    def section(name: str, ms: list[dict[str, Any]], stats: SplitStats) -> dict[str, Any]:
        return {
            "scope": name,
            "record": {"wins": stats.wins, "draws": stats.draws, "losses": stats.losses},
            "goals_vs_xg": {
                "goals_for": stats.goals_for,
                "xg_for": stats.xg_for,
                "goals_minus_xg_for": stats.goals_minus_xg_for,
                "goals_against": stats.goals_against,
                "xg_against": stats.xg_against,
                "goals_minus_xg_against": stats.goals_minus_xg_against,
            },
            "opponent_strength": stats.opponent_strength,
            "trends": trends(stats),
            "matches": _match_rows(ms),
        }

    return {
        "home_form": section("home", home, home_stats),
        "away_form": section("away", away, away_stats),
        "combined_recent_5": section("combined_recent_5", recent5, recent5_stats),
    }


def _scope_matches(team_form: dict[str, Any], scope: str) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = list(team_form["form"]["recent_matches"])
    matches_sorted = sorted(matches, key=lambda m: m["date"], reverse=True)
    if scope == "home_form":
        return [m for m in matches_sorted if m["home_away"] == "home"][:5]
    if scope == "away_form":
        return [m for m in matches_sorted if m["home_away"] == "away"][:5]
    return matches_sorted[:5]


def generate_summary_llm_for_scope(model: str, scope: str, analysis: dict[str, Any], team_form: dict[str, Any]) -> str:
    config = load_config(model)
    if not config:
        raise OpenAIError("OPENAI_API_KEY is not set")

    system_prompt = Path("System_prompts/04_form_generator.md").read_text(encoding="utf-8").strip()

    schema = {
        "name": "form_summary",
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "text": {"type": "string"},
            },
            "required": ["text"],
        },
        "strict": True,
    }

    scope_labels = {
        "home_form": "last five home matches",
        "away_form": "last five away matches",
        "combined_recent_5": "most recent five matches overall",
    }
    scope_analysis = analysis[scope]
    matches_in_scope = _scope_matches(team_form, scope)

    filtered = {
        "scope": scope,
        "scope_label": scope_labels[scope],
        "team": team_form["form"]["entity"]["team_name"],
        "season_context": team_form["form"]["season_context"],
        "analysis": scope_analysis,
        "matches": [
            {
                "match_id": m.get("match_id"),
                "date": m.get("date"),
                "home_away": m.get("home_away"),
                "opponent": (m.get("opponent") or {}).get("name"),
                "score": m.get("score"),
                "statistical_assessment": (m.get("statistical_assessment") or {}).get("label"),
                "narrative_summary": m.get("narrative_summary", ""),
            }
            for m in matches_in_scope
        ],
    }

    payload = {
        "model": config.model,
        "input": [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": "Using the input below, return ONLY the summary object.\n\n" + json.dumps(filtered, ensure_ascii=False),
            },
        ],
        "temperature": 0,
        "text": {
            "format": {
                "type": "json_schema",
                "name": schema["name"],
                "schema": schema["schema"],
                "strict": True,
            }
        },
    }

    resp = responses_create(config, payload)
    text = extract_output_text(resp)
    if not text:
        raise OpenAIError("Empty response text")
    data = json.loads(text)
    return str(data["text"])

def _summary_for_scope(team: str, scope_label: str, scope: dict[str, Any]) -> str:
    rec = scope["record"]
    goals = scope["goals_vs_xg"]
    finishing = scope["trends"]["finishing_efficiency"]
    defending = scope["trends"]["defensive_efficiency"]
    return (
        f"{team}'s {scope_label} reads {rec['wins']}W-{rec['draws']}D-{rec['losses']}L, "
        f"with {goals['goals_for']} scored and {goals['goals_against']} conceded. "
        f"In chance quality they generated {goals['xg_for']} xG and allowed {goals['xg_against']} xG, "
        f"{finishing} and {defending}."
    )


def generate_summaries(analysis: dict[str, Any], team_form: dict[str, Any]) -> dict[str, str]:
    team = team_form["form"]["entity"]["team_name"]
    return {
        "home_text": _summary_for_scope(team, "home form (last five home matches)", analysis["home_form"]),
        "away_text": _summary_for_scope(team, "away form (last five away matches)", analysis["away_form"]),
        "combined_recent_5_text": _summary_for_scope(team, "last five matches (home+away)", analysis["combined_recent_5"]),
    }


def run_for_file(
    input_path: Path,
    out_dir: Path,
    step2: Literal["rules", "llm", "auto"],
    step3: Literal["rules", "llm", "auto"],
    step4: Literal["rules", "llm", "auto"],
    model: str,
) -> None:
    team_form = json.loads(input_path.read_text(encoding="utf-8"))
    team_name = team_form["form"]["entity"]["team_name"]
    team_slug = _slugify(team_name)
    team_out = out_dir / team_slug
    team_out.mkdir(parents=True, exist_ok=True)

    # Step 2: match assessor (populate statistical_assessment)
    use_llm = step2 == "llm" or (step2 == "auto" and load_config(model) is not None)

    for idx, m in enumerate(team_form["form"]["recent_matches"]):
        if use_llm:
            try:
                m["statistical_assessment"] = assess_match_llm(model, team_form, idx)
            except OpenAIError as e:
                raise OpenAIError(f"LLM step 2 failed for {team_name} match_index={idx}: {e}") from e
        else:
            m["statistical_assessment"] = assess_match(m)

    (team_out / "03_with_assessments.json").write_text(json.dumps(team_form, indent=2) + "\n", encoding="utf-8")

    # Step 3: deterministic form analysis (home/away/combined recent 5)
    analysis = analyze_form(team_form)
    team_form.setdefault("form", {}).setdefault("workflow_rollup", {})["analysis"] = analysis
    (team_out / "04_analysis.json").write_text(json.dumps(analysis, indent=2) + "\n", encoding="utf-8")
    (team_out / "04_with_analysis.json").write_text(json.dumps(team_form, indent=2) + "\n", encoding="utf-8")

    # Step 4: final summary generation
    use_llm4 = step4 == "llm" or (step4 == "auto" and load_config(model) is not None)
    if use_llm4:
        summaries = {
            "home_text": generate_summary_llm_for_scope(model, "home_form", analysis, team_form),
            "away_text": generate_summary_llm_for_scope(model, "away_form", analysis, team_form),
            "combined_recent_5_text": generate_summary_llm_for_scope(model, "combined_recent_5", analysis, team_form),
        }
    else:
        summaries = generate_summaries(analysis, team_form)
    # Prominent location: alongside other form-window rollups.
    team_form.setdefault("form", {}).setdefault("form_window", {}).setdefault("summaries", {}).update(summaries)
    # Keep workflow_rollup as well for traceability/back-compat.
    team_form.setdefault("form", {}).setdefault("workflow_rollup", {}).setdefault("summary", {}).update(summaries)
    (team_out / "05_form_summary.txt").write_text(
        summaries["combined_recent_5_text"] + "\n",
        encoding="utf-8",
    )
    (team_out / "05_form_summary.json").write_text(
        json.dumps({"team_name": team_name, **summaries}, indent=2) + "\n",
        encoding="utf-8",
    )
    (team_out / "05_with_summary.json").write_text(json.dumps(team_form, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Enhanced Form post-generation workflow locally on prepared team JSON files.")
    parser.add_argument(
        "inputs",
        nargs="+",
        help="Input team JSON file(s), e.g. form_west_glamorgan_city.json form_north_london_red.json",
    )
    parser.add_argument("--output-dir", default="", help="Output directory (default: Output/local_run_<timestamp>)")
    parser.add_argument(
        "--step2",
        choices=["auto", "rules", "llm"],
        default="auto",
        help="How to produce statistical_assessment (auto=LLM if OPENAI_API_KEY set, else rules).",
    )
    parser.add_argument(
        "--step3",
        choices=["auto", "rules", "llm"],
        default="auto",
        help="Reserved intermediate analysis stage; currently uses deterministic analysis regardless of setting.",
    )
    parser.add_argument(
        "--step4",
        choices=["auto", "rules", "llm"],
        default="auto",
        help="How to produce summaries (auto=LLM if OPENAI_API_KEY set, else rules).",
    )
    parser.add_argument("--model", default="gpt-4.1-mini", help="Model to use when --step2=llm")
    args = parser.parse_args()

    out_dir = Path(args.output_dir) if args.output_dir else Path("Output") / f"local_run_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}"
    out_dir.mkdir(parents=True, exist_ok=True)

    for inp in args.inputs:
        run_for_file(
            Path(inp),
            out_dir,
            step2=args.step2,
            step3=args.step3,
            step4=args.step4,
            model=args.model,
        )

    print(f"Wrote results to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
