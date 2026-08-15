#!/usr/bin/env python3
"""Blocked-independent W/L screen and n=256 gate for Route-A models."""

from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import pathlib
import random
import statistics
import sys
import time
from typing import Any


ROOT = pathlib.Path(__file__).resolve().parents[1]
ENGINE = ROOT / "inference/comp_data/sample_submission/sample_submission"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ENGINE))

from experiments import arena_runner as arena  # noqa: E402
from experiments.routeA_policy import LinearResponseModel, RouteAAgent  # noqa: E402
from scripts.candidate_h2h import BASELINE as V22, CandidateAgent, assert_locked_baseline, sha256, tree_sha256  # noqa: E402
from scripts.safe_json_output import reserve_json_output  # noqa: E402


LEGS = (
    ("v22", V22, 64, 0.45),
    ("router", ROOT / "candidates" / "lucario_advanced_router_v13", 32, 0.15),
    ("alakazam", ROOT / "candidates" / "alakazam_codex_v22", 16, 0.30),
    ("lucario", ROOT / "submission_baseline", 32, 0.10),
)


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int((len(ordered) - 1) * percentile))]


def _agent(arm: str, model_payload: dict[str, Any] | None) -> CandidateAgent:
    if arm == "incumbent":
        return CandidateAgent(V22)
    if model_payload is None:
        raise ValueError(f"Route-A arm {arm} missing model")
    return RouteAAgent(
        V22,
        max_score_gap=25.0,
        mode="trained",
        model=LinearResponseModel.from_dict(model_payload),
    )


def _run(task: dict[str, Any]) -> dict[str, Any]:
    arm = str(task["arm"])
    leg = str(task["leg"])
    opponent_path = pathlib.Path(task["opponent"])
    games = int(task["games"])
    seed = int(task["seed"])
    candidate = _agent(arm, task.get("model"))
    opponent = CandidateAgent(opponent_path)
    candidate_deck = candidate.deck()
    opponent_deck = opponent.deck()
    wins = losses = draws = candidate_faults = opponent_faults = 0
    interventions = internal_error_games = 0
    latencies: list[float] = []
    steps: list[int] = []
    started = time.time()
    for game in range(games):
        if candidate.deck() != candidate_deck or opponent.deck() != opponent_deck:
            raise RuntimeError("Route-A gate deck changed between episodes")
        # ABBA/BAAB: balance seat and coarse time blocks without claiming CRN.
        candidate_seat = (0, 1, 1, 0, 1, 0, 0, 1)[game % 8]
        agents = (candidate, opponent) if candidate_seat == 0 else (opponent, candidate)
        decks = (
            (candidate_deck, opponent_deck)
            if candidate_seat == 0 else (opponent_deck, candidate_deck)
        )
        random.seed(seed + game)
        result = arena.play(agents, decks)
        steps.append(int(result.get("steps", 0) or 0))
        winner = int(result["winner"])
        if winner == -1:
            draws += 1
        elif winner == candidate_seat:
            wins += 1
        else:
            losses += 1
        fault = result.get("fault")
        if fault is not None:
            if int(fault) == candidate_seat:
                candidate_faults += 1
            else:
                opponent_faults += 1
        if isinstance(candidate, RouteAAgent):
            interventions += int(candidate.controller.intervened)
            internal_error_games += int(bool(candidate.controller.internal_errors))
            latencies.extend(candidate.controller.latencies_s)
    decisive = wins + losses
    return {
        "arm": arm,
        "leg": leg,
        "games": games,
        "wins": wins,
        "losses": losses,
        "draws": draws,
        "win_rate": round(wins / decisive, 6) if decisive else None,
        "candidate_faults": candidate_faults,
        "opponent_faults": opponent_faults,
        "internal_error_games": internal_error_games,
        "interventions": interventions,
        "intervention_rate": round(interventions / games, 6),
        "override_latency_p99_ms": (
            round(float(_percentile(latencies, 0.99)) * 1000.0, 6)
            if latencies else None
        ),
        "avg_steps": round(statistics.mean(steps), 2) if steps else None,
        "elapsed_s": round(time.time() - started, 6),
    }


def _weighted(rows: list[dict[str, Any]], weights: dict[str, float]) -> float:
    total = sum(weights[row["leg"]] for row in rows)
    return sum(weights[row["leg"]] * float(row["win_rate"] or 0.0) for row in rows) / total


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--canary", required=True)
    parser.add_argument("--stage", choices=("screen", "main"), required=True)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--seed", type=int, default=202608151328)
    parser.add_argument("--out", required=True)
    parser.add_argument("--overwrite-output", action="store_true")
    args = parser.parse_args()

    assert_locked_baseline()
    reservation = reserve_json_output(args.out, overwrite=args.overwrite_output)
    canary_path = pathlib.Path(args.canary).resolve()
    canary = json.loads(canary_path.read_text(encoding="utf-8"))
    if canary.get("verdict") != "PASS_TO_WL_SCREEN":
        raise SystemExit("Route-A live canary did not pass")
    models = {
        "trained": canary["trained_model"],
        "random": canary["random_control_model_live_matched"],
        "incumbent": None,
    }
    if args.stage == "screen":
        legs = LEGS
        arms = ("trained", "random", "incumbent")
    else:
        legs = (("v22", V22, 256, 1.0),)
        arms = ("trained", "incumbent")
    tasks = []
    for arm_index, arm in enumerate(arms):
        for leg_index, (leg, opponent, games, _weight) in enumerate(legs):
            tasks.append({
                "arm": arm,
                "model": models[arm],
                "leg": leg,
                "opponent": str(opponent),
                "games": games,
                "seed": args.seed + arm_index * 10_000_000 + leg_index * 1_000_000,
            })
    started = time.time()
    if args.workers == 1:
        rows = [_run(task) for task in tasks]
    else:
        context = mp.get_context("spawn")
        with context.Pool(processes=min(args.workers, len(tasks))) as pool:
            rows = list(pool.imap_unordered(_run, tasks, chunksize=1))
    rows.sort(key=lambda row: (row["arm"], row["leg"]))
    by_arm = {arm: [row for row in rows if row["arm"] == arm] for arm in arms}
    verdict = "KILL"
    assessment: dict[str, Any]
    if args.stage == "screen":
        weights = {name: weight for name, _path, _games, weight in legs}
        weighted = {arm: _weighted(by_arm[arm], weights) for arm in arms}
        trained_by_leg = {row["leg"]: row for row in by_arm["trained"]}
        incumbent_by_leg = {row["leg"]: row for row in by_arm["incumbent"]}
        deltas = {
            leg: float(trained_by_leg[leg]["win_rate"] or 0.0)
            - float(incumbent_by_leg[leg]["win_rate"] or 0.0)
            for leg in weights
        }
        candidate_clean = all(
            row["candidate_faults"] == 0 and row["internal_error_games"] == 0
            for row in by_arm["trained"] + by_arm["random"]
        )
        passed = bool(
            weighted["trained"] - weighted["incumbent"] >= 0.03
            and float(trained_by_leg["v22"]["win_rate"] or 0.0) >= 0.53
            and min(deltas.values()) >= -0.10
            and weighted["trained"] - weighted["random"] >= 0.03
            and candidate_clean
        )
        verdict = "PASS_TO_MAIN_GATE" if passed else "SCREEN_KILL"
        assessment = {
            "weighted_win_rates": {key: round(value, 6) for key, value in weighted.items()},
            "trained_delta_vs_incumbent": round(weighted["trained"] - weighted["incumbent"], 6),
            "trained_delta_vs_random": round(weighted["trained"] - weighted["random"], 6),
            "trained_per_leg_delta_vs_incumbent": {key: round(value, 6) for key, value in deltas.items()},
            "trained_v22_win_rate": trained_by_leg["v22"]["win_rate"],
            "candidate_clean": candidate_clean,
            "passed": passed,
        }
    else:
        trained = by_arm["trained"][0]
        incumbent = by_arm["incumbent"][0]
        trained_wr = float(trained["win_rate"] or 0.0)
        incumbent_wr = float(incumbent["win_rate"] or 0.0)
        delta = trained_wr - incumbent_wr
        passed = bool(
            trained_wr >= 0.55
            and delta >= 0.03
            and trained["candidate_faults"] == 0
            and trained["internal_error_games"] == 0
        )
        verdict = "PASS_TO_ARCHIVE" if passed else "MAIN_GATE_KILL"
        assessment = {
            "trained_win_rate": trained_wr,
            "incumbent_win_rate": incumbent_wr,
            "delta": round(delta, 6),
            "passed": passed,
        }
    report = {
        "created_unix": time.time(),
        "method": f"routeA-blocked-independent-{args.stage}-v1",
        "stage": args.stage,
        "source_canary": str(canary_path),
        "source_canary_sha256": sha256(canary_path),
        "candidate_tree_sha256": tree_sha256(V22),
        "native_shuffle": "unseeded independent batches; ABBA/BAAB seat/time balance only",
        "episode_reset": "select-none-before-every-game-v1",
        "rows": rows,
        "assessment": assessment,
        "verdict": verdict,
        "materialized": False,
        "submitted": False,
        "elapsed_s": round(time.time() - started, 6),
    }
    reservation.write(report)
    print(f"Route-A {args.stage} verdict={verdict} assessment={assessment}", flush=True)
    return 0 if assessment["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
