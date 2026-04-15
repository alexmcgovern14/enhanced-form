#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Literal


StrengthTier = Literal[1, 2, 3, 4, 5]

MIN_SYNTHETIC_PPG = 0.6
MAX_SYNTHETIC_PPG = 2.6
# Shaped percentile buckets: extremes are intentionally rare.
SHAPED_STRENGTH_BUCKETS: dict[StrengthTier, tuple[float, float]] = {
    1: (0.0, 0.1),
    2: (0.1, 0.35),
    3: (0.35, 0.65),
    4: (0.65, 0.9),
    5: (0.9, 1.0),
}


@dataclass(frozen=True)
class LeagueContext:
    competition: str
    league_ppg_average: float
    league_ppg_p25: float
    league_ppg_p75: float
    league_goals_for_per_game_avg: float
    league_goals_against_per_game_avg: float


def _read_club_names(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    names: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        line = re.sub(r"^\-\s*", "", line).strip()
        if line:
            names.append(line)
    deduped: list[str] = []
    seen = set()
    for name in names:
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(name)
    return deduped


def _stable_team_id(team_name: str) -> str:
    return hashlib.sha256(team_name.encode("utf-8")).hexdigest()[:8]


def _clamp_int(value: float, lo: int, hi: int) -> int:
    return max(lo, min(hi, int(round(value))))


def _round2(x: float) -> float:
    return float(f"{x:.2f}")


def _poisson(lam: float, rng: random.Random) -> int:
    if lam <= 0:
        return 0
    # Knuth algorithm; sufficient for small lam (typical football xG).
    l = math.exp(-lam)
    k = 0
    p = 1.0
    while p > l:
        k += 1
        p *= rng.random()
    return max(0, k - 1)


def _strength_tier(ppg: float, league: LeagueContext) -> StrengthTier:
    del league  # Synthetic tiering uses a fixed shaped percentile scale.
    normalized = (ppg - MIN_SYNTHETIC_PPG) / (MAX_SYNTHETIC_PPG - MIN_SYNTHETIC_PPG)
    normalized = max(0.0, min(1.0, normalized))
    if normalized >= SHAPED_STRENGTH_BUCKETS[5][0]:
        return 5
    if normalized >= SHAPED_STRENGTH_BUCKETS[4][0]:
        return 4
    if normalized >= SHAPED_STRENGTH_BUCKETS[3][0]:
        return 3
    if normalized >= SHAPED_STRENGTH_BUCKETS[2][0]:
        return 2
    return 1


def _opponent_ppg_for_tier(tier: StrengthTier, league: LeagueContext, rng: random.Random) -> float:
    del league  # Synthetic generation uses the shaped synthetic PPG scale below.
    low_pct, high_pct = SHAPED_STRENGTH_BUCKETS[tier]
    span = MAX_SYNTHETIC_PPG - MIN_SYNTHETIC_PPG
    low = MIN_SYNTHETIC_PPG + span * low_pct
    high = MIN_SYNTHETIC_PPG + span * high_pct
    if high_pct < 1.0:
        high -= 0.01
    return _round2(rng.uniform(low, high))


def _league_position_for_ppg(ppg: float, league: LeagueContext) -> int:
    del league
    normalized = (ppg - MIN_SYNTHETIC_PPG) / (MAX_SYNTHETIC_PPG - MIN_SYNTHETIC_PPG)
    normalized = max(0.0, min(1.0, normalized))
    return _clamp_int(20 - normalized * 19, 1, 20)


def _generate_match_xg(
    home_away: Literal["home", "away"],
    opponent_tier: StrengthTier,
    rng: random.Random,
) -> tuple[float, float]:
    base_for = 1.45 if home_away == "home" else 1.15
    base_against = 1.15 if home_away == "home" else 1.45

    xg_adjustments = {
        5: (-0.35, 0.35),
        4: (-0.18, 0.18),
        3: (0.0, 0.0),
        2: (0.18, -0.18),
        1: (0.35, -0.35),
    }
    for_adjust, against_adjust = xg_adjustments[opponent_tier]
    base_for += for_adjust
    base_against += against_adjust

    xg_for = max(0.2, rng.gauss(base_for, 0.45))
    xg_against = max(0.2, rng.gauss(base_against, 0.45))
    return (_round2(min(3.8, xg_for)), _round2(min(3.8, xg_against)))


def _match_narrative(
    team_name: str,
    opponent_name: str,
    home_away: Literal["home", "away"],
    goals_for: int,
    goals_against: int,
    xg_for: float,
    xg_against: float,
    red_for: int,
    red_against: int,
    rng: random.Random,
) -> str:
    venue = "at home" if home_away == "home" else "away"
    result_word = "drew" if goals_for == goals_against else ("beat" if goals_for > goals_against else "lost to")
    scoreline = f"{goals_for}-{goals_against}"

    chance_edge = xg_for - xg_against
    if chance_edge >= 0.6:
        balance = "created the clearer chances and were on top for long spells"
    elif chance_edge <= -0.6:
        balance = "were second best for much of the game and conceded the better chances"
    else:
        balance = "played a fairly even contest with both sides having spells"

    variance = goals_for - xg_for
    if variance >= 1.0:
        finishing = "made the most of their opportunities with clinical finishing"
    elif variance <= -1.0:
        finishing = "could have scored more, but wasteful finishing left them short"
    else:
        finishing = "turned their chances into a scoreline that broadly matched the chances created"

    incidents: list[str] = []

    # Discipline: incidents should feel like match-report consensus (VAR/penalty/late goal/etc.),
    # without pretending to cite real outlets.
    if red_for:
        incidents.append(f"{team_name} played a spell with ten men after a red card")
    if red_against:
        incidents.append(f"{opponent_name} were reduced to ten men after a red card")

    if not incidents:
        incident_pool: list[str] = []
        if abs(goals_for - goals_against) <= 1:
            incident_pool += [
                "a late goal swung the momentum",
                "a VAR decision played a part in a key moment",
                "a set-piece proved decisive",
            ]
        if variance <= -1.0:
            incident_pool += [
                "they missed a big chance that could have changed the game",
                "they had a goal ruled out after a tight VAR check",
                "a missed penalty was widely seen as a turning point",
            ]
        if variance >= 1.0:
            incident_pool += [
                "their first big chance went in and set the tone",
                "a keeper error helped open the door for the opener",
                "a quick double after the break settled the game",
            ]
        if incident_pool and rng.random() < 0.8:
            incidents.append(rng.choice(incident_pool))

    sentence_1 = f"{team_name} {result_word} {opponent_name} {scoreline} {venue}, and reports would likely say they {balance}."
    if incidents:
        incident_clause = ("Notably, " + "; ".join(incidents)) + "."
    else:
        incident_clause = ""
    sentence_2 = f"The result {('felt representative' if abs(chance_edge) < 0.6 else 'did not fully reflect the balance of play')}, and {team_name} {finishing}."

    if incident_clause:
        return f"{sentence_1} {incident_clause} {sentence_2}"
    return f"{sentence_1} {sentence_2}"


def _generate_recent_matches(
    team_name: str,
    club_pool: list[str],
    league: LeagueContext,
    window_size: int,
    fixture_date: date,
    rng: random.Random,
    forced_opponents: list[str] | None = None,
) -> list[dict[str, Any]]:
    opponents = [c for c in club_pool if c.casefold() != team_name.casefold()]
    if len(opponents) < window_size:
        raise ValueError(f"Need at least {window_size + 1} unique club names; got {len(club_pool)}")
    club_by_key = {c.casefold(): c for c in opponents}

    forced: list[str] = []
    if forced_opponents:
        seen_forced = set()
        for raw_name in forced_opponents:
            key = raw_name.strip().casefold()
            if not key:
                continue
            if key == team_name.casefold():
                raise ValueError(f"forced_opponents contains team name: {raw_name}")
            if key not in club_by_key:
                raise ValueError(f"forced_opponents contains unknown club: {raw_name}")
            if key in seen_forced:
                continue
            seen_forced.add(key)
            forced.append(club_by_key[key])

    if len(forced) > window_size:
        raise ValueError(f"forced_opponents length {len(forced)} exceeds window_size {window_size}")

    remaining = [c for c in opponents if c.casefold() not in {f.casefold() for f in forced}]
    rng.shuffle(remaining)
    opponents = forced + remaining

    home_away_sequence: list[Literal["home", "away"]] = (["home", "away"] * (window_size // 2)) + (
        ["home"] if window_size % 2 else []
    )
    home_away_sequence = home_away_sequence[:window_size]
    # Ensure exactly 5 home/5 away when window_size=10.
    if window_size == 10:
        home_away_sequence = ["home"] * 5 + ["away"] * 5
        rng.shuffle(home_away_sequence)

    matches: list[dict[str, Any]] = []
    for idx in range(window_size):
        match_date = fixture_date - timedelta(days=(idx + 1) * 7)
        home_away = home_away_sequence[idx]

        tier: StrengthTier = rng.choices([1, 2, 3, 4, 5], weights=[0.1, 0.25, 0.3, 0.25, 0.1], k=1)[0]  # type: ignore[assignment]
        opponent_ppg = _opponent_ppg_for_tier(tier, league, rng)
        opponent_position = _league_position_for_ppg(opponent_ppg, league)
        tier = _strength_tier(opponent_ppg, league)
        opponent_name = opponents[idx]
        opponent_slug = re.sub(r"\s+", "_", opponent_name.strip().lower())

        xg_for, xg_against = _generate_match_xg(home_away, tier, rng)
        goals_for = _poisson(max(0.15, xg_for), rng)
        goals_against = _poisson(max(0.15, xg_against), rng)
        goals_for = min(goals_for, 6)
        goals_against = min(goals_against, 6)

        shots_for = _clamp_int(xg_for * 8 + rng.gauss(4, 3), 4, 30)
        shots_against = _clamp_int(xg_against * 8 + rng.gauss(4, 3), 4, 30)
        sot_for = _clamp_int(shots_for * rng.uniform(0.28, 0.48), 1, shots_for)
        sot_against = _clamp_int(shots_against * rng.uniform(0.28, 0.48), 1, shots_against)

        red_for = 1 if rng.random() < 0.08 else 0
        red_against = 1 if rng.random() < 0.08 else 0

        narrative = _match_narrative(
            team_name=team_name,
            opponent_name=opponent_name,
            home_away=home_away,
            goals_for=goals_for,
            goals_against=goals_against,
            xg_for=xg_for,
            xg_against=xg_against,
            red_for=red_for,
            red_against=red_against,
            rng=rng,
        )

        matches.append(
            {
                "match_id": f"{match_date.isoformat()}_{opponent_slug}",
                "date": match_date.isoformat(),
                "competition": league.competition,
                "home_away": home_away,
                "opponent": {
                    "name": opponent_name,
                    "primary_domestic_competition": league.competition,
                    "ppg_at_time": opponent_ppg,
                    "league_position_at_time": opponent_position,
                    "strength_tier": tier,
                },
                "score": {"for": goals_for, "against": goals_against},
                "xg": {"for": xg_for, "against": xg_against},
                "shots": {"for": shots_for, "against": shots_against},
                "shots_on_target": {"for": sot_for, "against": sot_against},
                "red_cards": {"for": red_for, "against": red_against},
                "goals_minus_xg": {"for": _round2(goals_for - xg_for), "against": _round2(goals_against - xg_against)},
                "narrative_summary": narrative,
                "statistical_assessment": {
                    "label": "TBC",
                    "confidence": "TBC",
                    "primary_evidence": ["TBC", "TBC"],
                    "narrative_alignment": "TBC",
                },
            }
        )
    return matches


def _compute_form_window(recent_matches: list[dict[str, Any]]) -> dict[str, Any]:
    wins = draws = losses = 0
    gf = ga = 0
    xgf = xga = 0.0
    strength_counts = {str(i): 0 for i in range(1, 6)}

    for m in recent_matches:
        m_gf = int(m["score"]["for"])
        m_ga = int(m["score"]["against"])
        gf += m_gf
        ga += m_ga
        if m_gf > m_ga:
            wins += 1
        elif m_gf == m_ga:
            draws += 1
        else:
            losses += 1

        xgf += float(m["xg"]["for"])
        xga += float(m["xg"]["against"])

        tier = str(m["opponent"]["strength_tier"])
        if tier in strength_counts:
            strength_counts[tier] += 1

    n = max(1, len(recent_matches))
    goals_minus_xg_for = gf - xgf
    goals_minus_xg_against = ga - xga
    return {
        "rollup": {
            "record": {"wins": wins, "draws": draws, "losses": losses},
            "goals_for": gf,
            "goals_against": ga,
            "goals_for_per_game": _round2(gf / n),
            "goals_against_per_game": _round2(ga / n),
            "xg_for": _round2(xgf),
            "xg_against": _round2(xga),
            "xg_for_per_game": _round2(xgf / n),
            "xg_against_per_game": _round2(xga / n),
            "goals_minus_xg_for": _round2(goals_minus_xg_for),
            "goals_minus_xg_against": _round2(goals_minus_xg_against),
        },
        "opponent_strength_counts": strength_counts,
    }


def generate_team_form(
    team_name: str,
    opponent_in_upcoming_event: str,
    upcoming_home_away: Literal["home", "away"],
    club_pool: list[str],
    league: LeagueContext,
    window_size: int,
    fixture_date: date,
    rng: random.Random,
    forced_opponents: list[str] | None = None,
) -> dict[str, Any]:
    matches_played = rng.randint(18, 26)
    ppg = _round2(rng.uniform(1.0, 2.2))
    points = _clamp_int(ppg * matches_played, 0, 114)

    season_context = {
        "competition": league.competition,
        "matches_played": matches_played,
        "points": points,
        "ppg": ppg,
        "goals_for_per_game": _round2(rng.uniform(1.0, 2.2)),
        "goals_against_per_game": _round2(rng.uniform(0.9, 2.0)),
        "league_goals_for_per_game_avg": league.league_goals_for_per_game_avg,
        "league_goals_against_per_game_avg": league.league_goals_against_per_game_avg,
        "league_ppg_average": league.league_ppg_average,
        "league_ppg_p25": league.league_ppg_p25,
        "league_ppg_p75": league.league_ppg_p75,
    }

    recent_matches = _generate_recent_matches(
        team_name=team_name,
        club_pool=club_pool,
        league=league,
        window_size=window_size,
        fixture_date=fixture_date,
        rng=rng,
        forced_opponents=forced_opponents,
    )
    form_window = _compute_form_window(recent_matches)

    return {
        "form": {
            "entity": {
                "team_id": _stable_team_id(team_name),
                "team_name": team_name,
                "primary_domestic_competition": league.competition,
            },
            "upcoming_event": {
                "date": fixture_date.isoformat(),
                "competition": league.competition,
                "opponent": opponent_in_upcoming_event,
                "home_away": upcoming_home_away,
            },
            "season_context": season_context,
            "form_window": {
                "window_size": window_size,
                "competitions_included": "all",
                **form_window,
            },
            "recent_matches": recent_matches,
        }
    }


def _validate_team_form(data: dict[str, Any], expected_window_size: int) -> list[str]:
    errors: list[str] = []
    if "form" not in data:
        return ["Root missing key: form"]

    form = data["form"]
    for key in ("entity", "upcoming_event", "season_context", "form_window", "recent_matches"):
        if key not in form:
            errors.append(f"form missing key: {key}")

    recent = form.get("recent_matches", [])
    if not isinstance(recent, list):
        errors.append("form.recent_matches must be a list")
        return errors

    if len(recent) != expected_window_size:
        errors.append(f"Expected {expected_window_size} recent_matches, got {len(recent)}")

    ha_counts = {"home": 0, "away": 0}
    for idx, m in enumerate(recent):
        if not isinstance(m, dict):
            errors.append(f"recent_matches[{idx}] must be object")
            continue
        for key in ("match_id", "date", "competition", "home_away", "opponent", "score", "xg", "shots", "shots_on_target", "red_cards", "goals_minus_xg", "narrative_summary", "statistical_assessment"):
            if key not in m:
                errors.append(f"recent_matches[{idx}] missing key: {key}")
        ha = m.get("home_away")
        if ha in ha_counts:
            ha_counts[ha] += 1
        narrative = m.get("narrative_summary", "")
        if isinstance(narrative, str):
            sentence_count = len([s for s in re.split(r"(?<=[.!?])\\s+", narrative.strip()) if s])
            if sentence_count > 3:
                errors.append(f"recent_matches[{idx}] narrative_summary > 3 sentences")
        else:
            errors.append(f"recent_matches[{idx}] narrative_summary must be string")

        try:
            gf = int(m["score"]["for"])
            ga = int(m["score"]["against"])
            xgf = float(m["xg"]["for"])
            xga = float(m["xg"]["against"])
            gmx_for = float(m["goals_minus_xg"]["for"])
            gmx_against = float(m["goals_minus_xg"]["against"])
            if abs(gmx_for - (gf - xgf)) > 0.011:
                errors.append(f"recent_matches[{idx}] goals_minus_xg.for mismatch")
            if abs(gmx_against - (ga - xga)) > 0.011:
                errors.append(f"recent_matches[{idx}] goals_minus_xg.against mismatch")
        except Exception:
            errors.append(f"recent_matches[{idx}] numeric fields invalid")

    if expected_window_size == 10 and (ha_counts["home"] != 5 or ha_counts["away"] != 5):
        errors.append(f"Expected 5 home and 5 away, got home={ha_counts['home']} away={ha_counts['away']}")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate synthetic Enhanced Form JSON for a single fixture.")
    parser.add_argument("--home-team", required=False, help="Home team name (must be in club list).")
    parser.add_argument("--away-team", required=False, help="Away team name (must be in club list).")
    parser.add_argument("--fixture-date", default=date.today().isoformat(), help="Fixture date (YYYY-MM-DD).")
    parser.add_argument("--competition", default="Premier League", help="Competition name.")
    parser.add_argument("--window-size", type=int, default=10, choices=[5, 10], help="Number of recent matches.")
    parser.add_argument("--seed", type=int, default=7, help="Random seed for repeatability.")
    parser.add_argument(
        "--must-include-opponents",
        default="",
        help="Comma-separated list of opponent clubs that must appear in recent matches.",
    )
    parser.add_argument(
        "--club-list",
        default=str(Path("Primary context") / "List of club names to use.md"),
        help="Path to club names list (one per line).",
    )
    parser.add_argument(
        "--output-dir",
        default="",
        help="Directory to write outputs into (defaults to Output/synthetic_<timestamp>).",
    )
    args = parser.parse_args()

    club_list_path = Path(args.club_list)
    if not club_list_path.exists():
        raise SystemExit(f"Club list not found: {club_list_path}")
    clubs = _read_club_names(club_list_path)
    if len(clubs) < 3:
        raise SystemExit(f"Need at least 3 club names in {club_list_path}")

    rng = random.Random(args.seed)

    home_team = args.home_team or clubs[0]
    away_team = args.away_team or next((c for c in clubs if c.casefold() != home_team.casefold()), clubs[1])
    if home_team.casefold() == away_team.casefold():
        raise SystemExit("home-team and away-team must be different")

    fixture_date = date.fromisoformat(args.fixture_date)
    must_include = [s.strip() for s in args.must_include_opponents.split(",")] if args.must_include_opponents else []
    must_include = [s for s in must_include if s]

    league = LeagueContext(
        competition=args.competition,
        league_ppg_average=1.4,
        league_ppg_p25=1.05,
        league_ppg_p75=1.75,
        league_goals_for_per_game_avg=1.41,
        league_goals_against_per_game_avg=1.41,
    )

    out_dir = Path(args.output_dir) if args.output_dir else Path("Output") / f"synthetic_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}"
    out_dir.mkdir(parents=True, exist_ok=True)

    home_form = generate_team_form(
        team_name=home_team,
        opponent_in_upcoming_event=away_team,
        upcoming_home_away="home",
        club_pool=clubs,
        league=league,
        window_size=args.window_size,
        fixture_date=fixture_date,
        rng=rng,
        forced_opponents=must_include,
    )
    away_form = generate_team_form(
        team_name=away_team,
        opponent_in_upcoming_event=home_team,
        upcoming_home_away="away",
        club_pool=clubs,
        league=league,
        window_size=args.window_size,
        fixture_date=fixture_date,
        rng=rng,
        forced_opponents=must_include,
    )

    home_errors = _validate_team_form(home_form, expected_window_size=args.window_size)
    away_errors = _validate_team_form(away_form, expected_window_size=args.window_size)

    required_set = {s.strip().casefold() for s in must_include if s.strip()}
    if required_set:
        home_opps = {m["opponent"]["name"].casefold() for m in home_form["form"]["recent_matches"]}
        away_opps = {m["opponent"]["name"].casefold() for m in away_form["form"]["recent_matches"]}
        home_missing = sorted(required_set - home_opps)
        away_missing = sorted(required_set - away_opps)
        if home_missing:
            home_errors.append(f"Missing required opponents: {', '.join(home_missing)}")
        if away_missing:
            away_errors.append(f"Missing required opponents: {', '.join(away_missing)}")

    (out_dir / "fixture_meta.json").write_text(
        json.dumps(
            {
                "fixture_date": fixture_date.isoformat(),
                "competition": args.competition,
                "home_team": home_team,
                "away_team": away_team,
                "window_size": args.window_size,
                "seed": args.seed,
                "must_include": {
                    "requested": must_include,
                },
                "validation": {
                    "home_team_errors": home_errors,
                    "away_team_errors": away_errors,
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    (out_dir / "team_home.json").write_text(json.dumps(home_form, indent=2) + "\n", encoding="utf-8")
    (out_dir / "team_away.json").write_text(json.dumps(away_form, indent=2) + "\n", encoding="utf-8")

    if home_errors or away_errors:
        print(f"Wrote outputs to {out_dir} with validation errors; see fixture_meta.json")
        return 2

    print(f"Wrote outputs to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
