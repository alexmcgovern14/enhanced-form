#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", name.strip().lower())
    slug = re.sub(r"_+", "_", slug).strip("_")
    return slug


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def main() -> int:
    parser = argparse.ArgumentParser(description="Export per-team Enhanced Form JSON files with stable filenames.")
    parser.add_argument(
        "--input-dir",
        required=True,
        help="Folder containing team_home.json and team_away.json (from synthetic_fixture.py).",
    )
    parser.add_argument(
        "--output-dir",
        default=".",
        help="Where to write form_<team>.json files (default: repo root).",
    )
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    home_path = input_dir / "team_home.json"
    away_path = input_dir / "team_away.json"
    if not home_path.exists() or not away_path.exists():
        raise SystemExit(f"Expected {home_path} and {away_path}")

    for src in (home_path, away_path):
        data = _read_json(src)
        team_name = data["form"]["entity"]["team_name"]
        slug = _slugify(team_name)
        out_path = output_dir / f"form_{slug}.json"
        out_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
