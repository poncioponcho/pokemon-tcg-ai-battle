#!/usr/bin/env python3
"""Compare materialized pure-Python Route-A runtime to the gated in-memory head."""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiments.live_v22_replay_audit import DEFAULT_TEAM, _load_rows, parse_episode_source  # noqa: E402
from experiments.routeA_policy import LinearResponseModel, RouteAAgent  # noqa: E402
from scripts.candidate_h2h import BASELINE as V22, CandidateAgent, assert_locked_baseline, sha256, tree_sha256  # noqa: E402
from scripts.safe_json_output import reserve_json_output  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--canary", required=True)
    parser.add_argument(
        "--episodes", action="append", type=parse_episode_source, required=True,
        metavar="REF=PATH",
    )
    parser.add_argument("--replay-dir", required=True)
    parser.add_argument("--team-name", default=DEFAULT_TEAM)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    assert_locked_baseline()
    reservation = reserve_json_output(args.out)
    candidate_path = pathlib.Path(args.candidate).resolve()
    canary_path = pathlib.Path(args.canary).resolve()
    canary = json.loads(canary_path.read_text(encoding="utf-8"))
    if canary.get("verdict") != "PASS_TO_WL_SCREEN":
        raise SystemExit("Route-A canary not promotable")
    model = LinearResponseModel.from_dict(canary["trained_model"])
    reference = RouteAAgent(V22, max_score_gap=25.0, mode="trained", model=model)
    archive = CandidateAgent(candidate_path)
    public, validation = _load_rows(args.episodes)
    replay_dir = pathlib.Path(args.replay_dir).expanduser().resolve()
    calls = mismatches = 0
    samples = []
    started = time.time()
    for row in public:
        if reference.deck() != archive.deck():
            raise SystemExit("Route-A archive/reference deck mismatch")
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
            obs = record.get("observation") or {}
            expected = reference(obs)
            actual = archive(obs)
            calls += 1
            if actual != expected:
                mismatches += 1
                if len(samples) < 10:
                    samples.append({
                        "episode_id": int(row["id"]),
                        "step_index": step_index,
                        "reference": expected,
                        "archive": actual,
                    })
    report = {
        "created_unix": time.time(),
        "method": "routeA-materialized-runtime-equivalence-v1",
        "candidate": str(candidate_path),
        "candidate_tree_sha256": tree_sha256(candidate_path),
        "candidate_main_sha256": sha256(candidate_path / "main.py"),
        "source_canary": str(canary_path),
        "source_canary_sha256": sha256(canary_path),
        "public_episodes": len(public),
        "validation_excluded": len(validation),
        "active_calls": calls,
        "action_mismatches": mismatches,
        "mismatch_samples": samples,
        "verdict": "PASS" if mismatches == 0 else "KILL",
        "elapsed_s": round(time.time() - started, 6),
    }
    reservation.write(report)
    print(
        f"Route-A archive equivalence verdict={report['verdict']} "
        f"calls={calls} mismatches={mismatches}",
        flush=True,
    )
    return 0 if mismatches == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
