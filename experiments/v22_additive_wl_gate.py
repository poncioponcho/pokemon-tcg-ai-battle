#!/usr/bin/env python3
"""Blocked-independent W/L gate for live-calibrated additive v22 residuals.

The candidate set and thresholds are frozen in
reports/20260815_v22_additive_residual_prereg.md.  Native cg shuffles cannot be
seeded; ABBA/BAAB here balances seat and coarse time blocks only and must not
be interpreted as paired/common-random-number evaluation.
"""

from __future__ import annotations

import argparse
import multiprocessing as mp
import pathlib
import random
import statistics
import sys
import time
from dataclasses import dataclass
from typing import Any


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiments import arena_runner as arena  # noqa: E402
from experiments.v22_live_additive_screen import (  # noqa: E402
    AdditiveParamAgent,
    AdditiveSpec,
)
from scripts.candidate_h2h import (  # noqa: E402
    BASELINE as V22,
    CandidateAgent,
    assert_locked_baseline,
    sha256,
    tree_sha256,
)
from scripts.safe_json_output import reserve_json_output  # noqa: E402


@dataclass(frozen=True)
class Leg:
    name: str
    path: str
    games: int
    weight: float


LEGS = (
    Leg("v22", str(V22), 64, 0.45),
    Leg("router", str(ROOT / "candidates" / "lucario_advanced_router_v13"), 32, 0.15),
    Leg("alakazam", str(ROOT / "candidates" / "alakazam_codex_v22"), 16, 0.30),
    Leg("lucario", str(ROOT / "submission_baseline"), 32, 0.10),
)
CANDIDATES = (
    AdditiveSpec("resource_timing_offset", 25),
    AdditiveSpec("attachment_timing_offset", 50),
)
SEAT_PATTERNS = (
    (False, True, True, False),   # ABBA: candidate seats 0,1,1,0
    (True, False, False, True),   # BAAB: candidate seats 1,0,0,1
)


def _run_blocked_match(
    candidate: CandidateAgent,
    opponent: CandidateAgent,
    n: int,
    seed: int,
) -> dict[str, Any]:
    if n <= 0 or n % 4:
        raise ValueError("blocked match n must be a positive multiple of four")
    candidate_deck = candidate.deck()
    opponent_deck = opponent.deck()
    wins = losses = draws = candidate_faults = opponent_faults = 0
    steps: list[int] = []
    seat_counts = {"0": 0, "1": 0}
    fault_samples: list[dict[str, Any]] = []
    started = time.time()

    for game in range(n):
        if candidate.deck() != candidate_deck:
            raise SystemExit("candidate deck changed between episodes")
        if opponent.deck() != opponent_deck:
            raise SystemExit("opponent deck changed between episodes")
        block = game // 4
        swap = SEAT_PATTERNS[block % 2][game % 4]
        candidate_seat = 1 if swap else 0
        seat_counts[str(candidate_seat)] += 1
        agents = (candidate, opponent) if not swap else (opponent, candidate)
        decks = (
            (candidate_deck, opponent_deck)
            if not swap
            else (opponent_deck, candidate_deck)
        )
        # Python-side agents only.  Native shuffle remains unseeded.
        random.seed(seed + game)
        result = arena.play(agents, decks)
        steps.append(int(result["steps"]))
        fault = result.get("fault")
        if fault is not None:
            if fault == candidate_seat:
                candidate_faults += 1
                who = "candidate"
            else:
                opponent_faults += 1
                who = "opponent"
            if len(fault_samples) < 10:
                fault_samples.append({
                    "game": game,
                    "candidate_seat": candidate_seat,
                    "who": who,
                    "error": result.get("err"),
                })
        winner = int(result["winner"])
        if winner == -1:
            draws += 1
        elif winner == candidate_seat:
            wins += 1
        else:
            losses += 1

    decisive = wins + losses
    return {
        "games": n,
        "wins": wins,
        "losses": losses,
        "draws": draws,
        "win_rate": round(wins / decisive, 6) if decisive else None,
        "candidate_faults": candidate_faults,
        "opponent_faults": opponent_faults,
        "candidate_seat_counts": seat_counts,
        "seat_schedule": "alternating-four-game-ABBA-BAAB",
        "avg_steps": round(statistics.mean(steps), 2),
        "elapsed_s": round(time.time() - started, 3),
        "fault_samples": fault_samples,
    }


def _make_agent(raw: dict[str, Any]) -> CandidateAgent:
    if raw["kind"] == "incumbent":
        return CandidateAgent(V22)
    spec = AdditiveSpec(str(raw["family"]), int(raw["offset"]))
    return AdditiveParamAgent(V22, spec)


def _evaluate_task(task: dict[str, Any]) -> dict[str, Any]:
    candidate = _make_agent(task)
    legs = [Leg(**row) for row in task["legs"]]
    results = []
    started = time.time()
    for index, leg in enumerate(legs):
        opponent = CandidateAgent(pathlib.Path(leg.path))
        result = _run_blocked_match(
            candidate,
            opponent,
            leg.games,
            int(task["seed"]) + index * 100_000,
        )
        result.update({"opponent": leg.name, "weight": leg.weight})
        results.append(result)
    weighted = sum(
        leg.weight * float(result["win_rate"] or 0.0)
        for leg, result in zip(legs, results)
    ) / sum(leg.weight for leg in legs)
    return {
        "label": task["label"],
        "kind": task["kind"],
        "family": task.get("family"),
        "offset": task.get("offset"),
        "games": sum(result["games"] for result in results),
        "weighted_win_rate": round(weighted, 6),
        "candidate_faults": sum(result["candidate_faults"] for result in results),
        "opponent_faults": sum(result["opponent_faults"] for result in results),
        "elapsed_s": round(time.time() - started, 3),
        "results": results,
    }


def _task_for_spec(
    spec: AdditiveSpec | None,
    *,
    legs: tuple[Leg, ...],
    seed: int,
) -> dict[str, Any]:
    if spec is None:
        return {
            "label": "incumbent",
            "kind": "incumbent",
            "family": None,
            "offset": None,
            "legs": [leg.__dict__ for leg in legs],
            "seed": seed,
        }
    return {
        "label": spec.label,
        "kind": "additive",
        "family": spec.family,
        "offset": spec.offset,
        "legs": [leg.__dict__ for leg in legs],
        "seed": seed,
    }


def _run_tasks(tasks: list[dict[str, Any]], workers: int) -> list[dict[str, Any]]:
    if workers <= 1:
        return [_evaluate_task(task) for task in tasks]
    context = mp.get_context("spawn")
    with context.Pool(processes=min(workers, len(tasks))) as pool:
        return list(pool.map(_evaluate_task, tasks))


def _leg_map(row: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {result["opponent"]: result for result in row["results"]}


def _screen_assessment(
    candidate: dict[str, Any], incumbent: dict[str, Any]
) -> dict[str, Any]:
    cand_legs = _leg_map(candidate)
    inc_legs = _leg_map(incumbent)
    deltas = {
        name: round(
            float(cand_legs[name]["win_rate"] or 0.0)
            - float(inc_legs[name]["win_rate"] or 0.0),
            6,
        )
        for name in cand_legs
    }
    weighted_delta = (
        float(candidate["weighted_win_rate"])
        - float(incumbent["weighted_win_rate"])
    )
    crossmeta_ok = all(deltas[name] >= -0.10 for name in deltas if name != "v22")
    eligible = bool(
        candidate["candidate_faults"] == 0
        and float(cand_legs["v22"]["win_rate"] or 0.0) >= 0.53
        and weighted_delta >= 0.03
        and crossmeta_ok
    )
    return {
        "eligible_for_n256": eligible,
        "zero_candidate_faults": candidate["candidate_faults"] == 0,
        "v22_win_rate": cand_legs["v22"]["win_rate"],
        "v22_floor_ok": float(cand_legs["v22"]["win_rate"] or 0.0) >= 0.53,
        "weighted_delta": round(weighted_delta, 6),
        "weighted_delta_ok": weighted_delta >= 0.03,
        "per_leg_delta": deltas,
        "crossmeta_floor_ok": crossmeta_ok,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--seed", type=int, default=202608151122)
    parser.add_argument("--overwrite-output", action="store_true")
    args = parser.parse_args()
    if args.workers <= 0:
        raise SystemExit("--workers must be positive")

    assert_locked_baseline()
    for leg in LEGS:
        if not pathlib.Path(leg.path).exists():
            raise SystemExit(f"opponent path missing: {leg.path}")
    reservation = reserve_json_output(args.out, overwrite=args.overwrite_output)
    started = time.time()

    screen_tasks = [
        _task_for_spec(spec, legs=LEGS, seed=args.seed + index * 1_000_000)
        for index, spec in enumerate((*CANDIDATES, None))
    ]
    print("[four-leg] candidates=2 + incumbent; 144 games each", flush=True)
    screen = _run_tasks(screen_tasks, args.workers)
    by_label = {row["label"]: row for row in screen}
    incumbent = by_label["incumbent"]
    assessments = {
        spec.label: _screen_assessment(by_label[spec.label], incumbent)
        for spec in CANDIDATES
    }
    eligible_specs = [
        spec for spec in CANDIDATES
        if assessments[spec.label]["eligible_for_n256"]
    ]
    selected = None
    if eligible_specs:
        selected = max(
            eligible_specs,
            key=lambda spec: (
                assessments[spec.label]["weighted_delta"],
                assessments[spec.label]["v22_win_rate"],
            ),
        )

    main_gate = None
    winner = None
    if selected is not None:
        direct_leg = (Leg("v22", str(V22), 256, 1.0),)
        direct_tasks = [
            _task_for_spec(selected, legs=direct_leg, seed=args.seed + 900_000_000),
            _task_for_spec(None, legs=direct_leg, seed=args.seed + 901_000_000),
        ]
        print(f"[n256] selected={selected.label} + incumbent control", flush=True)
        direct = _run_tasks(direct_tasks, min(args.workers, 2))
        direct_by_label = {row["label"]: row for row in direct}
        cand = direct_by_label[selected.label]
        inc = direct_by_label["incumbent"]
        cand_wr = float(cand["results"][0]["win_rate"] or 0.0)
        inc_wr = float(inc["results"][0]["win_rate"] or 0.0)
        delta = cand_wr - inc_wr
        passed = bool(
            cand["candidate_faults"] == 0
            and cand_wr >= 0.55
            and delta >= 0.03
        )
        main_gate = {
            "selected": selected.as_dict(),
            "candidate": cand,
            "incumbent": inc,
            "candidate_win_rate": round(cand_wr, 6),
            "incumbent_win_rate": round(inc_wr, 6),
            "delta": round(delta, 6),
            "rules": {
                "candidate_win_rate_min": 0.55,
                "delta_vs_independent_incumbent_min": 0.03,
                "candidate_faults": 0,
            },
            "passed": passed,
        }
        if passed:
            winner = selected.as_dict()

    report: dict[str, Any] = {
        "created_unix": time.time(),
        "method": "blocked-independent-additive-residual-wl-v1",
        "preregistration": str(
            ROOT / "reports" / "20260815_v22_additive_residual_prereg.md"
        ),
        "candidate_source": str(V22),
        "candidate_tree_sha256": tree_sha256(V22),
        "candidate_main_sha256": sha256(V22 / "main.py"),
        "candidate_deck_sha256": sha256(V22 / "deck.csv"),
        "runner_sha256": sha256(pathlib.Path(__file__).resolve()),
        "module_isolation": "per-candidate-sys-modules-v1",
        "episode_reset": "select-none-before-every-game-v1",
        "seat_schedule": "alternating-four-game-ABBA-BAAB",
        "native_shuffle": "unseeded; independent batches; not paired/CRN",
        "candidates": [spec.as_dict() for spec in CANDIDATES],
        "four_leg": {
            "legs": [leg.__dict__ for leg in LEGS],
            "results": screen,
            "assessments": assessments,
            "selected_for_n256": None if selected is None else selected.as_dict(),
        },
        "main_gate": main_gate,
        "winner": winner,
        "materialized": False,
        "submitted": False,
        "elapsed_s": round(time.time() - started, 3),
    }
    reservation.write(report)
    print(
        f"[done] selected={report['four_leg']['selected_for_n256']} "
        f"winner={winner} elapsed={report['elapsed_s']}s -> {args.out}",
        flush=True,
    )
    for spec in CANDIDATES:
        row = by_label[spec.label]
        assessment = assessments[spec.label]
        print(
            f"  {spec.label}: weighted={row['weighted_win_rate']:.4f} "
            f"delta={assessment['weighted_delta']:+.4f} "
            f"v22={assessment['v22_win_rate']:.4f} "
            f"eligible={assessment['eligible_for_n256']}",
            flush=True,
        )
    if main_gate is not None:
        print(
            f"  n256: candidate={main_gate['candidate_win_rate']:.4f} "
            f"incumbent={main_gate['incumbent_win_rate']:.4f} "
            f"delta={main_gate['delta']:+.4f} pass={main_gate['passed']}",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
