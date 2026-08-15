#!/usr/bin/env python3
"""Calibrate the preregistered Route-A safe-alternative behavior threshold."""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time
from collections import Counter
from typing import Any


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiments.live_v22_replay_audit import (  # noqa: E402
    DEFAULT_TEAM,
    _load_rows,
    parse_episode_source,
)
from experiments.routeA_policy import (  # noqa: E402
    FALLBACK_MODULE,
    MAIN_MODULE,
    PROPOSER_THRESHOLDS,
    propose_safe_alternative,
)
from scripts.candidate_h2h import (  # noqa: E402
    BASELINE as V22,
    CandidateAgent,
    assert_locked_baseline,
    sha256,
    tree_sha256,
)
from scripts.safe_json_output import reserve_json_output  # noqa: E402


OLD_REF = 55499962
NEW_REF = 55516725


def _scan_episode(
    row: dict[str, Any],
    replay_path: pathlib.Path,
    team_name: str,
) -> dict[str, Any]:
    replay = json.loads(replay_path.read_text(encoding="utf-8"))
    steps = replay.get("steps") or []
    seat = int(row["seat"])
    names = (replay.get("info") or {}).get("TeamNames") or []
    if len(names) != 2 or names[seat] != team_name:
        raise SystemExit(f"team/seat mismatch ep={row['id']}")
    agent = CandidateAgent(V22)
    main = agent._private_modules.get(MAIN_MODULE)
    fallback = agent._private_modules.get(FALLBACK_MODULE)
    if main is None or fallback is None:
        raise SystemExit("Route-A canary modules missing")

    first_by_threshold: dict[int, dict[str, Any]] = {}
    active_calls = mismatches = 0
    for step_index in range(len(steps) - 1):
        record = steps[step_index][seat]
        if record.get("status") != "ACTIVE":
            continue
        obs = record.get("observation") or {}
        expected = steps[step_index + 1][seat].get("action")
        if not isinstance(expected, list):
            expected = []
        active_calls += 1
        select = obs.get("select")
        if isinstance(select, dict) and select.get("option"):
            # The choose hook is reached only if manual guards decline.  Probe
            # this before advancing the exact agent's history/memory.
            manual_action = main.apply_manual_guards(obs)
            if manual_action is None:
                state = main._state(obs)
                options = [main._semantic(obs, option) for option in select.get("option") or []]
                history = list(main._HISTORY)
                for threshold in PROPOSER_THRESHOLDS:
                    if threshold in first_by_threshold:
                        continue
                    proposal = propose_safe_alternative(
                        fallback, state, options, history, expected, threshold
                    )
                    if proposal is not None:
                        first_by_threshold[threshold] = {
                            "step_index": step_index,
                            **proposal.as_dict(),
                        }
        actual = agent(obs)
        if actual != expected:
            mismatches += 1
    if mismatches:
        raise SystemExit(f"exact-v22 mismatch ep={row['id']} count={mismatches}")
    return {
        "episode_id": int(row["id"]),
        "ref": int(row.get("ref", row.get("submission_id", 0)) or 0),
        "seat": seat,
        "reward": int(row.get("reward", 0) or 0),
        "active_calls": active_calls,
        "first_by_threshold": {str(k): v for k, v in first_by_threshold.items()},
    }


def _coverage(rows: list[dict[str, Any]], threshold: int) -> dict[str, Any]:
    eligible = [row for row in rows if str(threshold) in row["first_by_threshold"]]
    return {
        "episodes": len(rows),
        "eligible": len(eligible),
        "rate": round(len(eligible) / len(rows), 6) if rows else None,
        "refs": dict(Counter(str(row["ref"]) for row in eligible)),
        "seats": dict(Counter(str(row["seat"]) for row in eligible)),
        "rewards": dict(Counter(str(row["reward"]) for row in eligible)),
        "buckets": dict(Counter(
            row["first_by_threshold"][str(threshold)]["bucket"] for row in eligible
        )),
        "episode_ids": [row["episode_id"] for row in eligible],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--episodes", action="append", type=parse_episode_source, required=True,
        metavar="REF=PATH",
    )
    parser.add_argument("--replay-dir", required=True)
    parser.add_argument("--team-name", default=DEFAULT_TEAM)
    parser.add_argument("--out", required=True)
    parser.add_argument("--overwrite-output", action="store_true")
    args = parser.parse_args()

    assert_locked_baseline()
    reservation = reserve_json_output(args.out, overwrite=args.overwrite_output)
    public, validation = _load_rows(args.episodes)
    if len(public) != 82:
        raise SystemExit(f"frozen Route-A canary requires 82 PUBLIC episodes, got {len(public)}")
    replay_dir = pathlib.Path(args.replay_dir).expanduser().resolve()
    started = time.time()
    scans = [
        _scan_episode(
            row,
            replay_dir / f"episode-{int(row['id'])}-replay.json",
            args.team_name,
        )
        for row in public
    ]
    # _load_rows retains the source ref in its normalized rows; enforce the
    # preregistered 50/32 design/holdout split explicitly.
    by_ref = Counter(row["ref"] for row in scans)
    if by_ref != Counter({OLD_REF: 50, NEW_REF: 32}):
        raise SystemExit(f"unexpected ref split: {dict(by_ref)}")

    thresholds: dict[str, Any] = {}
    selected: int | None = None
    for threshold in PROPOSER_THRESHOLDS:
        old_rows = [row for row in scans if row["ref"] == OLD_REF]
        new_rows = [row for row in scans if row["ref"] == NEW_REF]
        old = _coverage(old_rows, threshold)
        new = _coverage(new_rows, threshold)
        combined = _coverage(scans, threshold)
        design_pass = 8 <= old["eligible"] <= 33
        holdout_pass = 3 <= new["eligible"] <= 13
        combined_pass = 8 <= combined["eligible"] <= 33
        thresholds[str(threshold)] = {
            "old_design": old,
            "new_holdout": new,
            "combined": combined,
            "design_pass": design_pass,
            "holdout_pass": holdout_pass,
            "combined_pass": combined_pass,
        }
        if selected is None and design_pass and holdout_pass and combined_pass:
            selected = threshold

    selected_coverage = None if selected is None else thresholds[str(selected)]
    report = {
        "created_unix": time.time(),
        "method": "routeA-safe-runner-up-live-canary-v1",
        "preregistration": str(ROOT / "reports" / "20260815_routeA_prereg.md"),
        "candidate_tree_sha256": tree_sha256(V22),
        "candidate_main_sha256": sha256(V22 / "main.py"),
        "candidate_deck_sha256": sha256(V22 / "deck.csv"),
        "public_episodes": len(public),
        "validation_excluded": len(validation),
        "ref_split": {str(key): value for key, value in sorted(by_ref.items())},
        "threshold_grid": list(PROPOSER_THRESHOLDS),
        "thresholds": thresholds,
        "selected_max_score_gap": selected,
        "selected_coverage": selected_coverage,
        "verdict": "PASS" if selected is not None else "BEHAVIOR_KILL",
        "exact_action_mismatches": 0,
        "scans": scans,
        "elapsed_s": round(time.time() - started, 3),
    }
    reservation.write(report)
    print(
        f"Route-A behavior canary verdict={report['verdict']} "
        f"selected={selected} elapsed={report['elapsed_s']}s",
        flush=True,
    )
    for threshold in PROPOSER_THRESHOLDS:
        row = thresholds[str(threshold)]
        print(
            f"  gap<={threshold:4}: old={row['old_design']['eligible']:2}/50 "
            f"new={row['new_holdout']['eligible']:2}/32 "
            f"all={row['combined']['eligible']:2}/82",
            flush=True,
        )
    return 0 if selected is not None else 2


if __name__ == "__main__":
    raise SystemExit(main())
