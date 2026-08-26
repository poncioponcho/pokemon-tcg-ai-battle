#!/usr/bin/env python3
"""Opponent-strength-corrected readout for one live Alakazam submission.

Episode rows contain outcomes and opponent team names; a leaderboard snapshot
supplies one noisy current rating per opponent.  The script reports raw WR and
solves the usual Elo expectation equation for an implicit rating ``mu_star``.
The snapshot is not time-aligned to every game, so the corrected value is a
comparative diagnostic, not a reconstruction of Kaggle's Glicko state.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import pathlib
import statistics
import sys
import time
from typing import Any


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.candidate_h2h import sha256  # noqa: E402
from scripts.safe_json_output import reserve_json_output  # noqa: E402


def normalize_name(value: Any) -> str:
    return " ".join(str(value or "").split()).casefold()


def wilson(wins: int, total: int, z: float = 1.96) -> list[float] | None:
    if total <= 0:
        return None
    p = wins / total
    denom = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denom
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * total)) / total) / denom
    return [round(max(0.0, center - margin), 6), round(min(1.0, center + margin), 6)]


def expected(mu: float, opponent: float) -> float:
    return 1.0 / (1.0 + 10.0 ** ((opponent - mu) / 400.0))


def implicit_rating(opponents: list[float], wins: int) -> float | None:
    if not opponents or wins <= 0 or wins >= len(opponents):
        return None
    lo, hi = -1000.0, 2500.0
    for _ in range(100):
        mid = (lo + hi) / 2
        if sum(expected(mid, opponent) for opponent in opponents) < wins:
            lo = mid
        else:
            hi = mid
    return round((lo + hi) / 2, 2)


def summarize(rows: list[dict[str, Any]], scores: dict[str, float]) -> dict[str, Any]:
    decisive = [row for row in rows if row.get("reward") in (-1, 1)]
    wins = sum(int(row["reward"]) == 1 for row in decisive)
    matched = [
        (row, scores[normalize_name(row.get("opp"))])
        for row in decisive
        if normalize_name(row.get("opp")) in scores
    ]
    matched_wins = sum(int(row["reward"]) == 1 for row, _ in matched)
    opponent_scores = [score for _, score in matched]
    return {
        "games": len(decisive),
        "wins": wins,
        "losses": len(decisive) - wins,
        "win_rate": round(wins / len(decisive), 6) if decisive else None,
        "wilson95": wilson(wins, len(decisive)),
        "matched_opponents": len(matched),
        "matched_wins": matched_wins,
        "matched_win_rate": round(matched_wins / len(matched), 6) if matched else None,
        "opponent_score_mean": round(statistics.mean(opponent_scores), 2) if opponent_scores else None,
        "opponent_score_median": round(statistics.median(opponent_scores), 2) if opponent_scores else None,
        "implicit_mu_star": implicit_rating(opponent_scores, matched_wins),
        "newest_end": decisive[0].get("end") if decisive else None,
        "oldest_end": decisive[-1].get("end") if decisive else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episodes", required=True)
    parser.add_argument("--leaderboard", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--overwrite-output", action="store_true")
    args = parser.parse_args()

    episode_path = pathlib.Path(args.episodes).expanduser().resolve()
    leaderboard_path = pathlib.Path(args.leaderboard).expanduser().resolve()
    rows = json.loads(episode_path.read_text(encoding="utf-8"))
    public = [
        row for row in rows
        if row.get("is_public", row.get("opp_sub") is not None)
        and row.get("reward") in (-1, 1)
    ]
    public.sort(key=lambda row: row.get("end") or "", reverse=True)

    with leaderboard_path.open(encoding="utf-8-sig", newline="") as stream:
        leaderboard_rows = list(csv.DictReader(stream))
    scores: dict[str, float] = {}
    duplicate_names: set[str] = set()
    for row in leaderboard_rows:
        name = normalize_name(row.get("TeamName"))
        if not name:
            continue
        try:
            score = float(row["Score"])
        except (KeyError, TypeError, ValueError):
            continue
        if name in scores and scores[name] != score:
            duplicate_names.add(name)
            continue
        scores[name] = score
    for name in duplicate_names:
        scores.pop(name, None)

    windows = {}
    for size in (32, 50, 80, 160, len(public)):
        if size <= len(public):
            windows[str(size)] = summarize(public[:size], scores)

    report = {
        "created_unix": time.time(),
        "method": "elo-opponent-strength-correction-v1",
        "caveat": (
            "opponent scores come from one later snapshot; mu_star is a "
            "comparative bias correction, not Kaggle Glicko reconstruction"
        ),
        "episodes": str(episode_path),
        "episodes_sha256": sha256(episode_path),
        "leaderboard": str(leaderboard_path),
        "leaderboard_sha256": sha256(leaderboard_path),
        "public_games": len(public),
        "leaderboard_teams": len(leaderboard_rows),
        "ambiguous_team_names_excluded": len(duplicate_names),
        "windows_newest_first": windows,
    }
    reserve_json_output(args.out, overwrite=args.overwrite_output).write(report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
