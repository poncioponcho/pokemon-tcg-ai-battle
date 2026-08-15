#!/usr/bin/env python3
"""Generate randomized one-intervention Route-A episodes with terminal W/L."""

from __future__ import annotations

import argparse
import multiprocessing as mp
import pathlib
import random
import statistics
import sys
import time
from collections import Counter
from typing import Any


ROOT = pathlib.Path(__file__).resolve().parents[1]
ENGINE = ROOT / "inference/comp_data/sample_submission/sample_submission"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ENGINE))

from experiments import arena_runner as arena  # noqa: E402
from experiments.routeA_policy import (  # noqa: E402
    FEATURE_NAMES,
    TURN_BUCKETS,
    RouteAAgent,
)
from scripts.candidate_h2h import (  # noqa: E402
    BASELINE as V22,
    CandidateAgent,
    assert_locked_baseline,
    sha256,
    tree_sha256,
)
from scripts.safe_json_output import reserve_json_output  # noqa: E402


PREREG = ROOT / "reports" / "20260815_routeA_prereg.md"
AMENDMENT = ROOT / "reports" / "20260815_routeA_prereg_amendment1.md"
DEFAULT_LEGS = {
    "v22": V22,
    "router": ROOT / "candidates" / "lucario_advanced_router_v13",
    "alakazam": ROOT / "candidates" / "alakazam_codex_v22",
    "lucario": ROOT / "submission_baseline",
}


def _assignment_schedule() -> tuple[tuple[str, int, int], ...]:
    rows = [
        (bucket, treatment, seat)
        for bucket in TURN_BUCKETS
        for treatment in (0, 1)
        for seat in (0, 1)
    ]
    random.Random(202608151328).shuffle(rows)
    return tuple(rows)


ASSIGNMENTS = _assignment_schedule()


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int((len(ordered) - 1) * percentile)))
    return ordered[index]


def _run_chunk(task: dict[str, Any]) -> dict[str, Any]:
    leg = str(task["leg"])
    opponent_path = pathlib.Path(task["opponent"])
    indices = [int(value) for value in task["indices"]]
    max_score_gap = float(task["max_score_gap"])
    seed = int(task["seed"])
    candidate = RouteAAgent(
        V22,
        max_score_gap=max_score_gap,
        mode="randomized",
    )
    opponent = CandidateAgent(opponent_path)
    candidate_deck = candidate.deck()
    opponent_deck = opponent.deck()
    rows = []
    started = time.time()

    for game_index in indices:
        if candidate.deck() != candidate_deck:
            raise RuntimeError("Route-A candidate deck changed between episodes")
        if opponent.deck() != opponent_deck:
            raise RuntimeError("Route-A opponent deck changed between episodes")
        bucket, treatment, candidate_seat = ASSIGNMENTS[game_index % len(ASSIGNMENTS)]
        candidate.configure_randomized_episode(bucket, treatment)
        agents = (
            (candidate, opponent) if candidate_seat == 0 else (opponent, candidate)
        )
        decks = (
            (candidate_deck, opponent_deck)
            if candidate_seat == 0
            else (opponent_deck, candidate_deck)
        )
        random.seed(seed + game_index)
        result = arena.play(agents, decks)
        winner = int(result["winner"])
        if winner == -1:
            outcome = 0.5
        else:
            outcome = float(winner == candidate_seat)
        fault = result.get("fault")
        candidate_fault = bool(fault is not None and int(fault) == candidate_seat)
        opponent_fault = bool(fault is not None and int(fault) != candidate_seat)
        record = candidate.episode_record()
        episode_latencies = list(candidate.controller.latencies_s)
        rows.append({
            "leg": leg,
            "game_index": game_index,
            "target_bucket": bucket,
            "assigned_treatment": treatment,
            "candidate_seat": candidate_seat,
            "eligible": record is not None,
            "intervened": bool(record and record.get("treatment") == 1),
            "outcome": outcome,
            "winner": winner,
            "steps": int(result.get("steps", 0) or 0),
            "candidate_fault": candidate_fault,
            "opponent_fault": opponent_fault,
            "fault_error": result.get("err") if fault is not None else None,
            "internal_errors": list(candidate.controller.internal_errors),
            "override_calls": len(episode_latencies),
            "override_latency_sum_s": sum(episode_latencies),
            "override_latency_p99_s": _percentile(episode_latencies, 0.99),
            "record": record,
        })
    return {
        "leg": leg,
        "indices": indices,
        "rows": rows,
        "elapsed_s": round(time.time() - started, 6),
    }


def _summarize(rows: list[dict[str, Any]], elapsed_s: float) -> dict[str, Any]:
    eligible = [row for row in rows if row["eligible"]]
    latency_p99s = [
        float(row["override_latency_p99_s"])
        for row in rows if row.get("override_latency_p99_s") is not None
    ]
    override_calls = sum(int(row.get("override_calls", 0)) for row in rows)
    latency_sum_s = sum(float(row.get("override_latency_sum_s", 0.0)) for row in rows)
    decisive = [row for row in rows if row["outcome"] != 0.5]
    return {
        "games": len(rows),
        "elapsed_s": round(elapsed_s, 6),
        "throughput_games_s": round(len(rows) / elapsed_s, 6) if elapsed_s else None,
        "eligible_games": len(eligible),
        "eligible_rate": round(len(eligible) / len(rows), 6) if rows else None,
        "intervened_games": sum(row["intervened"] for row in rows),
        "assigned_treatment": dict(Counter(str(row["assigned_treatment"]) for row in rows)),
        "target_buckets": dict(Counter(row["target_bucket"] for row in rows)),
        "candidate_seats": dict(Counter(str(row["candidate_seat"]) for row in rows)),
        "eligible_treatment": dict(Counter(str(row["assigned_treatment"]) for row in eligible)),
        "eligible_buckets": dict(Counter(row["target_bucket"] for row in eligible)),
        "legs": dict(Counter(row["leg"] for row in rows)),
        "wins": sum(row["outcome"] == 1.0 for row in decisive),
        "losses": sum(row["outcome"] == 0.0 for row in decisive),
        "draws": sum(row["outcome"] == 0.5 for row in rows),
        "candidate_faults": sum(row["candidate_fault"] for row in rows),
        "opponent_faults": sum(row["opponent_fault"] for row in rows),
        "internal_error_games": sum(bool(row["internal_errors"]) for row in rows),
        "max_interventions_per_game": max(
            (int(row["intervened"]) for row in rows), default=0
        ),
        "override_calls": override_calls,
        "override_latency_mean_ms": (
            round(latency_sum_s / override_calls * 1000.0, 6)
            if override_calls else None
        ),
        "override_latency_p99_ms": (
            round(float(_percentile(latency_p99s, 0.99)) * 1000.0, 6)
            if latency_p99s else None
        ),
        "feature_widths": dict(Counter(
            str(len(row["record"]["features"]))
            for row in eligible
            if row.get("record")
        )),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games-per-leg", type=int, required=True)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--chunk-size", type=int, default=16)
    parser.add_argument("--max-score-gap", type=float, default=25.0)
    parser.add_argument("--seed", type=int, default=202608151328)
    parser.add_argument("--out", required=True)
    parser.add_argument("--overwrite-output", action="store_true")
    args = parser.parse_args()
    if args.games_per_leg <= 0 or args.workers <= 0 or args.chunk_size <= 0:
        raise SystemExit("games-per-leg/workers/chunk-size must be positive")
    if args.max_score_gap != 25.0:
        raise SystemExit("Route-A amendment freezes --max-score-gap=25")

    assert_locked_baseline()
    reservation = reserve_json_output(args.out, overwrite=args.overwrite_output)
    for name, path in DEFAULT_LEGS.items():
        if not path.is_dir():
            raise SystemExit(f"Route-A leg missing: {name}={path}")
    tasks = []
    for leg_index, (leg, opponent) in enumerate(DEFAULT_LEGS.items()):
        for start in range(0, args.games_per_leg, args.chunk_size):
            stop = min(args.games_per_leg, start + args.chunk_size)
            tasks.append({
                "leg": leg,
                "opponent": str(opponent),
                "indices": list(range(start, stop)),
                "max_score_gap": args.max_score_gap,
                "seed": args.seed + leg_index * 10_000_000,
            })
    started = time.time()
    if args.workers == 1:
        chunks = [_run_chunk(task) for task in tasks]
    else:
        context = mp.get_context("spawn")
        with context.Pool(processes=args.workers) as pool:
            chunks = list(pool.imap_unordered(_run_chunk, tasks, chunksize=1))
    rows = [row for chunk in chunks for row in chunk["rows"]]
    rows.sort(key=lambda row: (row["leg"], row["game_index"]))
    elapsed_s = time.time() - started
    summary = _summarize(rows, elapsed_s)
    report = {
        "created_unix": time.time(),
        "method": "routeA-randomized-single-intervention-collection-v1",
        "preregistration": str(PREREG),
        "preregistration_sha256": sha256(PREREG),
        "amendment": str(AMENDMENT),
        "amendment_sha256": sha256(AMENDMENT),
        "candidate_source": str(V22),
        "candidate_tree_sha256": tree_sha256(V22),
        "candidate_main_sha256": sha256(V22 / "main.py"),
        "candidate_deck_sha256": sha256(V22 / "deck.csv"),
        "feature_names": list(FEATURE_NAMES),
        "assignment_schedule": [list(row) for row in ASSIGNMENTS],
        "max_score_gap": args.max_score_gap,
        "games_per_leg": args.games_per_leg,
        "workers": args.workers,
        "chunk_size": args.chunk_size,
        "native_shuffle": "unseeded; independent episodes; Python seed is agent-only",
        "episode_reset": "select-none-before-every-game-v1",
        "summary": summary,
        "rows": rows,
    }
    reservation.write(report)
    print(
        f"Route-A collect games={summary['games']} eligible={summary['eligible_games']} "
        f"throughput={summary['throughput_games_s']} faults="
        f"{summary['candidate_faults']}/{summary['opponent_faults']} "
        f"internal_errors={summary['internal_error_games']} "
        f"p99_ms={summary['override_latency_p99_ms']}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
