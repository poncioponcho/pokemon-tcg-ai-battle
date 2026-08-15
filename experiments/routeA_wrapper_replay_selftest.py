#!/usr/bin/env python3
"""Prove the dormant Route-A hook reproduces exact v22 on all live calls."""

from __future__ import annotations

import argparse
import json
import pathlib
import statistics
import sys
import time
from typing import Any


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiments.live_v22_replay_audit import DEFAULT_TEAM, _load_rows, parse_episode_source  # noqa: E402
from experiments.routeA_policy import RouteAAgent  # noqa: E402
from scripts.candidate_h2h import BASELINE as V22, assert_locked_baseline, sha256, tree_sha256  # noqa: E402
from scripts.safe_json_output import reserve_json_output  # noqa: E402


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
        raise SystemExit(f"Route-A wrapper selftest requires 82 PUBLIC episodes, got {len(public)}")
    replay_dir = pathlib.Path(args.replay_dir).expanduser().resolve()
    agent = RouteAAgent(V22, max_score_gap=25.0, mode="exact")
    active_calls = mismatches = internal_errors = 0
    latency_values: list[float] = []
    started = time.time()
    for row in public:
        agent.deck()
        replay = json.loads(
            (replay_dir / f"episode-{int(row['id'])}-replay.json").read_text(encoding="utf-8")
        )
        steps = replay.get("steps") or []
        seat = int(row["seat"])
        names = (replay.get("info") or {}).get("TeamNames") or []
        if len(names) != 2 or names[seat] != args.team_name:
            raise SystemExit(f"team/seat mismatch ep={row['id']}")
        for step_index in range(len(steps) - 1):
            record = steps[step_index][seat]
            if record.get("status") != "ACTIVE":
                continue
            expected = steps[step_index + 1][seat].get("action")
            if not isinstance(expected, list):
                expected = []
            actual = agent(record.get("observation") or {})
            active_calls += 1
            mismatches += int(actual != expected)
        internal_errors += len(agent.controller.internal_errors)
        latency_values.extend(agent.controller.latencies_s)
    latency_values.sort()
    p99 = latency_values[int((len(latency_values) - 1) * 0.99)] if latency_values else None
    report: dict[str, Any] = {
        "created_unix": time.time(),
        "method": "routeA-dormant-wrapper-exact-reproduction-v1",
        "candidate_tree_sha256": tree_sha256(V22),
        "candidate_main_sha256": sha256(V22 / "main.py"),
        "candidate_deck_sha256": sha256(V22 / "deck.csv"),
        "public_episodes": len(public),
        "validation_excluded": len(validation),
        "active_calls": active_calls,
        "exact_action_mismatches": mismatches,
        "internal_errors": internal_errors,
        "wrapper_calls": len(latency_values),
        "wrapper_latency_mean_ms": (
            round(statistics.mean(latency_values) * 1000.0, 6)
            if latency_values else None
        ),
        "wrapper_latency_p99_ms": round(p99 * 1000.0, 6) if p99 is not None else None,
        "verdict": "PASS" if mismatches == 0 and internal_errors == 0 else "KILL",
        "elapsed_s": round(time.time() - started, 6),
    }
    reservation.write(report)
    print(
        f"Route-A wrapper selftest verdict={report['verdict']} "
        f"calls={active_calls} mismatches={mismatches} p99_ms={report['wrapper_latency_p99_ms']}",
        flush=True,
    )
    return 0 if report["verdict"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
