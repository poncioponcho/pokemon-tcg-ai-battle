#!/usr/bin/env python3
"""Evaluate trained and matched-random Route-A first overrides on live states."""

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

from experiments.live_v22_replay_audit import DEFAULT_TEAM, _load_rows, parse_episode_source  # noqa: E402
from experiments.routeA_policy import (  # noqa: E402
    FALLBACK_MODULE,
    MAIN_MODULE,
    LinearResponseModel,
    propose_safe_alternative,
)
from scripts.candidate_h2h import BASELINE as V22, CandidateAgent, assert_locked_baseline, sha256, tree_sha256  # noqa: E402
from scripts.safe_json_output import reserve_json_output  # noqa: E402


def _scan_episode(
    row: dict[str, Any],
    replay_path: pathlib.Path,
    team_name: str,
    trained: LinearResponseModel,
    random_control: LinearResponseModel,
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
        raise SystemExit("Route-A trained canary modules missing")
    opportunities = []
    mismatches = 0
    for step_index in range(len(steps) - 1):
        record = steps[step_index][seat]
        if record.get("status") != "ACTIVE":
            continue
        obs = record.get("observation") or {}
        expected = steps[step_index + 1][seat].get("action")
        if not isinstance(expected, list):
            expected = []
        select = obs.get("select")
        if isinstance(select, dict) and select.get("option"):
            manual_action = main.apply_manual_guards(obs)
            if manual_action is None:
                state = main._state(obs)
                options = [main._semantic(obs, option) for option in select.get("option") or []]
                proposal = propose_safe_alternative(
                    fallback, state, options, list(main._HISTORY), expected, 25.0
                )
                if proposal is not None:
                    opportunities.append({
                        "step_index": step_index,
                        "proposal": proposal.as_dict(),
                        "trained_advantage": trained.advantage(proposal.features),
                        "random_advantage": random_control.advantage(proposal.features),
                    })
        if agent(obs) != expected:
            mismatches += 1
    if mismatches:
        raise SystemExit(f"exact-v22 mismatch ep={row['id']} count={mismatches}")
    return {
        "episode_id": int(row["id"]),
        "ref": int(row["ref"]),
        "seat": seat,
        "reward": int(row.get("reward", 0) or 0),
        "opportunities": opportunities,
    }


def _first(rows: list[dict[str, Any]], key: str, threshold: float) -> list[dict[str, Any]]:
    divergent = []
    for row in rows:
        hit = next(
            (item for item in row["opportunities"] if float(item[key]) >= threshold),
            None,
        )
        if hit is not None:
            divergent.append({
                "episode_id": row["episode_id"],
                "ref": row["ref"],
                "seat": row["seat"],
                "reward": row["reward"],
                "step_index": hit["step_index"],
                "advantage": hit[key],
                "proposal": hit["proposal"],
            })
    return divergent


def _coverage(rows: list[dict[str, Any]], total: int) -> dict[str, Any]:
    return {
        "divergent_episodes": len(rows),
        "rate": round(len(rows) / total, 6),
        "refs": dict(Counter(str(row["ref"]) for row in rows)),
        "seats": dict(Counter(str(row["seat"]) for row in rows)),
        "rewards": dict(Counter(str(row["reward"]) for row in rows)),
        "buckets": dict(Counter(row["proposal"]["bucket"] for row in rows)),
        "rows": rows,
    }


def _match_random_threshold(
    rows: list[dict[str, Any]],
    target_count: int,
) -> float:
    values = sorted({
        float(item["random_advantage"])
        for row in rows for item in row["opportunities"]
    })
    if not values:
        raise SystemExit("Route-A random control has no live opportunities")
    candidates = [values[0] - 1e-12, values[-1] + 1e-12]
    candidates.extend(values)
    candidates.extend((left + right) / 2.0 for left, right in zip(values, values[1:]))
    return min(
        candidates,
        key=lambda threshold: (
            abs(len(_first(rows, "random_advantage", threshold)) - target_count),
            -threshold,
        ),
    )


def _model_dict(model: LinearResponseModel) -> dict[str, Any]:
    return {
        "intercept": model.intercept,
        "coefficients": list(model.coefficients),
        "decision_threshold": model.decision_threshold,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
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
    model_path = pathlib.Path(args.model).resolve()
    model_payload = json.loads(model_path.read_text(encoding="utf-8"))
    if model_payload.get("verdict") != "PASS_TO_LIVE_CANARY":
        raise SystemExit("Route-A model did not pass cross-fit gate")
    trained = LinearResponseModel.from_dict(model_payload["trained_model"])
    initial_random = LinearResponseModel.from_dict(model_payload["random_control_model"])
    public, validation = _load_rows(args.episodes)
    if len(public) != 82:
        raise SystemExit(f"Route-A trained canary requires 82 PUBLIC episodes, got {len(public)}")
    replay_dir = pathlib.Path(args.replay_dir).expanduser().resolve()
    started = time.time()
    scans = [
        _scan_episode(
            row,
            replay_dir / f"episode-{int(row['id'])}-replay.json",
            args.team_name,
            trained,
            initial_random,
        )
        for row in public
    ]
    trained_rows = _first(scans, "trained_advantage", trained.decision_threshold)
    random_threshold = _match_random_threshold(scans, len(trained_rows))
    random_control = LinearResponseModel(
        intercept=initial_random.intercept,
        coefficients=initial_random.coefficients,
        decision_threshold=random_threshold,
    )
    random_rows = _first(scans, "random_advantage", random_threshold)
    trained_coverage = _coverage(trained_rows, len(public))
    random_coverage = _coverage(random_rows, len(public))
    trained_pass = bool(
        8 <= len(trained_rows) <= 33
        and len(trained_coverage["refs"]) == 2
        and len(trained_coverage["seats"]) == 2
        and "1" in trained_coverage["rewards"]
        and "-1" in trained_coverage["rewards"]
    )
    rate_delta = abs(trained_coverage["rate"] - random_coverage["rate"])
    random_match_pass = rate_delta <= 0.02
    report = {
        "created_unix": time.time(),
        "method": "routeA-trained-live-first-override-canary-v1",
        "source_model": str(model_path),
        "source_model_sha256": sha256(model_path),
        "candidate_tree_sha256": tree_sha256(V22),
        "public_episodes": len(public),
        "validation_excluded": len(validation),
        "trained_model": _model_dict(trained),
        "random_control_model_live_matched": _model_dict(random_control),
        "trained": trained_coverage,
        "random_control": random_coverage,
        "rate_absolute_delta": round(rate_delta, 6),
        "rules": {
            "trained_divergent_min": 8,
            "trained_divergent_max": 33,
            "two_refs_seats_outcomes": True,
            "random_rate_delta_max": 0.02,
        },
        "trained_behavior_pass": trained_pass,
        "random_rate_match_pass": random_match_pass,
        "verdict": (
            "PASS_TO_WL_SCREEN"
            if trained_pass and random_match_pass
            else "BEHAVIOR_KILL"
        ),
        "exact_action_mismatches": 0,
        "elapsed_s": round(time.time() - started, 6),
    }
    reservation.write(report)
    print(
        f"Route-A trained canary verdict={report['verdict']} "
        f"trained={len(trained_rows)}/82 random={len(random_rows)}/82 "
        f"delta={rate_delta:.4f}",
        flush=True,
    )
    return 0 if report["verdict"] == "PASS_TO_WL_SCREEN" else 2


if __name__ == "__main__":
    raise SystemExit(main())
