#!/usr/bin/env python3
"""Preregistered 2x2 structural ablation of exact v22.

The factors are the complete manual-guard layer and the complete hierarchy.
All arms retain the exact deck, validated fallback, episode reset, and hard
legality guard.  Native engine shuffles are unseeded, so W/L batches are
blocked independent trials rather than paired/common-random-number trials.
"""

from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import pathlib
import sys
import time
from dataclasses import dataclass
from typing import Any


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiments.live_v22_replay_audit import (  # noqa: E402
    DEFAULT_TEAM,
    _load_rows,
    parse_episode_source,
)
from experiments.v22_additive_wl_gate import (  # noqa: E402
    Leg,
    _run_blocked_match,
)
from experiments.v22_live_decision_surface import _semantic_signature  # noqa: E402
from scripts.candidate_h2h import (  # noqa: E402
    BASELINE as V22,
    CandidateAgent,
    assert_locked_baseline,
    sha256,
    tree_sha256,
)
from scripts.safe_json_output import reserve_json_output  # noqa: E402


MAIN_MODULE = "policies.v22.main"
MANUAL_MODULE = "policies.v22.manual_guards"
FALLBACK_MODULE = "policies.v22.validated_fallback_policy"
PREREG = ROOT / "reports" / "20260815_v22_structural_factorial_prereg.md"

LEGS = (
    Leg("v22", str(V22), 64, 0.45),
    Leg("router", str(ROOT / "candidates" / "lucario_advanced_router_v13"), 32, 0.15),
    Leg("alakazam", str(ROOT / "candidates" / "alakazam_codex_v22"), 16, 0.30),
    Leg("lucario", str(ROOT / "submission_baseline"), 32, 0.10),
)


@dataclass(frozen=True)
class Arm:
    label: str
    manual: bool
    hierarchy: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "manual": self.manual,
            "hierarchy": self.hierarchy,
        }


ARMS = (
    Arm("exact_v22", True, True),
    Arm("hierarchy_only", False, True),
    Arm("manual_only", True, False),
    Arm("fallback_only", False, False),
)


class StructuralV22Agent(CandidateAgent):
    """Exact-v22 runtime with process-local structural switches."""

    def __init__(self, source: pathlib.Path, arm: Arm):
        super().__init__(source)
        self.arm = arm
        main = self._private_modules.get(MAIN_MODULE)
        manual = self._private_modules.get(MANUAL_MODULE)
        fallback = self._private_modules.get(FALLBACK_MODULE)
        if any(module is None for module in (main, manual, fallback)):
            raise SystemExit("exact-v22 structural modules missing")
        assert main is not None
        assert manual is not None
        assert fallback is not None

        if not arm.manual:
            manual.GUARDS = ()
        if not arm.hierarchy:
            fallback_choose = fallback.choose

            def choose_without_hierarchy(
                state: dict[str, Any],
                options: list[dict[str, Any]],
                history: list[dict[str, Any]],
                _memory: Any = None,
            ) -> list[int]:
                return list(fallback_choose(state, options, history))

            # main.agent resolves ``choose`` from its module globals at call
            # time.  This bypasses every hierarchical planner while retaining
            # the exact validated fallback and main's hard legality guard.
            main.choose = choose_without_hierarchy


def _arm_by_label(label: str) -> Arm:
    for arm in ARMS:
        if arm.label == label:
            return arm
    raise ValueError(f"unknown arm: {label}")


def _replay_canary(
    sources: list[tuple[int, pathlib.Path]],
    replay_dir: pathlib.Path,
    team_name: str,
) -> dict[str, Any]:
    public, validation = _load_rows(sources)
    if len(public) != 82:
        raise SystemExit(f"frozen canary requires 82 PUBLIC episodes, got {len(public)}")

    exact_mismatches = 0
    exact_calls = 0
    divergent: dict[str, list[dict[str, Any]]] = {
        arm.label: [] for arm in ARMS if arm.label != "exact_v22"
    }
    exact = StructuralV22Agent(V22, _arm_by_label("exact_v22"))

    for row in public:
        episode_id = int(row["id"])
        replay_path = replay_dir / f"episode-{episode_id}-replay.json"
        replay = json.loads(replay_path.read_text(encoding="utf-8"))
        steps = replay.get("steps") or []
        seat = int(row["seat"])
        names = (replay.get("info") or {}).get("TeamNames") or []
        if len(names) != 2 or names[seat] != team_name:
            raise SystemExit(f"team/seat mismatch ep={episode_id}")

        variants = {
            arm.label: StructuralV22Agent(V22, arm)
            for arm in ARMS if arm.label != "exact_v22"
        }
        diverged: set[str] = set()
        for step_index in range(len(steps) - 1):
            record = steps[step_index][seat]
            if record.get("status") != "ACTIVE":
                continue
            obs = record.get("observation") or {}
            expected = steps[step_index + 1][seat].get("action")
            if not isinstance(expected, list):
                expected = []
            exact_action = exact(obs)
            exact_calls += 1
            if exact_action != expected:
                exact_mismatches += 1
            if not isinstance(obs.get("select"), dict):
                for label, variant in variants.items():
                    if label not in diverged:
                        variant(obs)
                continue

            main = exact._private_modules.get(MAIN_MODULE)
            if main is None:
                raise SystemExit("exact-v22 main module missing during canary")
            exact_sig = _semantic_signature(main, obs, exact_action)
            state = main._state(obs)
            for label, variant in variants.items():
                if label in diverged:
                    continue
                action = variant(obs)
                signature = _semantic_signature(main, obs, action)
                if signature == exact_sig:
                    continue
                diverged.add(label)
                divergent[label].append({
                    "episode": episode_id,
                    "ref": int(row["ref"]),
                    "reward": int(row["reward"]),
                    "seat": seat,
                    "step_index": step_index,
                    "turn": int(state.get("turn", 0) or 0),
                    "context": int(state.get("context", -1)),
                    "exact_action": exact_action,
                    "variant_action": action,
                })

    if exact_mismatches:
        raise SystemExit(
            f"exact-v22 replay mismatches={exact_mismatches}; refusing W/L"
        )
    summary = {}
    for arm in ARMS:
        if arm.label == "exact_v22":
            continue
        rows = divergent[arm.label]
        summary[arm.label] = {
            "divergent_episodes": len(rows),
            "by_ref": {
                str(ref): sum(int(row["ref"]) == ref for row in rows)
                for ref in (55499962, 55516725)
            },
            "by_reward": {
                "win": sum(int(row["reward"]) == 1 for row in rows),
                "loss": sum(int(row["reward"]) == -1 for row in rows),
            },
            "turn_le_4": sum(int(row["turn"]) <= 4 for row in rows),
            "first_divergences": rows,
        }
    return {
        "public_episodes": len(public),
        "validation_excluded": len(validation),
        "exact_active_calls": exact_calls,
        "exact_action_mismatches": exact_mismatches,
        "arms": summary,
    }


def _evaluate_task(task: dict[str, Any]) -> dict[str, Any]:
    arm = Arm(**task["arm"])
    candidate = StructuralV22Agent(V22, arm)
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
        **arm.as_dict(),
        "games": sum(result["games"] for result in results),
        "weighted_win_rate": round(weighted, 6),
        "candidate_faults": sum(result["candidate_faults"] for result in results),
        "opponent_faults": sum(result["opponent_faults"] for result in results),
        "elapsed_s": round(time.time() - started, 3),
        "results": results,
    }


def _run_tasks(tasks: list[dict[str, Any]], workers: int) -> list[dict[str, Any]]:
    if workers <= 1:
        return [_evaluate_task(task) for task in tasks]
    context = mp.get_context("spawn")
    with context.Pool(processes=min(workers, len(tasks))) as pool:
        return list(pool.map(_evaluate_task, tasks))


def _leg_map(row: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {result["opponent"]: result for result in row["results"]}


def _assessment(
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


def _task(arm: Arm, legs: tuple[Leg, ...], seed: int) -> dict[str, Any]:
    return {
        "arm": arm.as_dict(),
        "legs": [leg.__dict__ for leg in legs],
        "seed": seed,
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
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--seed", type=int, default=202608151230)
    parser.add_argument("--overwrite-output", action="store_true")
    args = parser.parse_args()
    if args.workers <= 0:
        raise SystemExit("--workers must be positive")

    assert_locked_baseline()
    if not PREREG.is_file():
        raise SystemExit(f"preregistration missing: {PREREG}")
    for leg in LEGS:
        if not pathlib.Path(leg.path).exists():
            raise SystemExit(f"opponent path missing: {leg.path}")
    reservation = reserve_json_output(args.out, overwrite=args.overwrite_output)
    replay_dir = pathlib.Path(args.replay_dir).expanduser().resolve()
    started = time.time()

    print("[canary] frozen 82 replay first-divergence audit", flush=True)
    canary = _replay_canary(args.episodes, replay_dir, args.team_name)
    for label, row in canary["arms"].items():
        print(
            f"  {label}: D={row['divergent_episodes']} "
            f"refs={row['by_ref']} turn<=4={row['turn_le_4']}",
            flush=True,
        )

    tasks = [
        _task(arm, LEGS, args.seed + index * 1_000_000)
        for index, arm in enumerate(ARMS)
    ]
    print("[four-leg] arms=4; 144 blocked-independent games each", flush=True)
    screen = _run_tasks(tasks, args.workers)
    by_label = {row["label"]: row for row in screen}
    incumbent = by_label["exact_v22"]
    assessments = {
        arm.label: _assessment(by_label[arm.label], incumbent)
        for arm in ARMS if arm.label != "exact_v22"
    }
    eligible = [
        arm for arm in ARMS
        if arm.label != "exact_v22"
        and assessments[arm.label]["eligible_for_n256"]
    ]
    selected = None
    if eligible:
        selected = max(
            eligible,
            key=lambda arm: (
                assessments[arm.label]["weighted_delta"],
                assessments[arm.label]["v22_win_rate"],
                arm.label,
            ),
        )

    main_gate = None
    winner = None
    if selected is not None:
        direct = (Leg("v22", str(V22), 256, 1.0),)
        direct_tasks = [
            _task(selected, direct, args.seed + 900_000_000),
            _task(_arm_by_label("exact_v22"), direct, args.seed + 901_000_000),
        ]
        print(f"[n256] selected={selected.label} + exact control", flush=True)
        rows = _run_tasks(direct_tasks, min(args.workers, 2))
        direct_by_label = {row["label"]: row for row in rows}
        candidate = direct_by_label[selected.label]
        control = direct_by_label["exact_v22"]
        candidate_wr = float(candidate["results"][0]["win_rate"] or 0.0)
        control_wr = float(control["results"][0]["win_rate"] or 0.0)
        delta = candidate_wr - control_wr
        passed = bool(
            candidate["candidate_faults"] == 0
            and candidate_wr >= 0.55
            and delta >= 0.03
        )
        main_gate = {
            "selected": selected.as_dict(),
            "candidate": candidate,
            "incumbent": control,
            "candidate_win_rate": round(candidate_wr, 6),
            "incumbent_win_rate": round(control_wr, 6),
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
        "method": "exact-v22-manual-x-hierarchy-factorial-v1",
        "preregistration": str(PREREG),
        "preregistration_sha256": sha256(PREREG),
        "candidate_source": str(V22),
        "candidate_tree_sha256": tree_sha256(V22),
        "candidate_main_sha256": sha256(V22 / "main.py"),
        "candidate_deck_sha256": sha256(V22 / "deck.csv"),
        "runner_sha256": sha256(pathlib.Path(__file__).resolve()),
        "module_isolation": "per-candidate-sys-modules-v1",
        "episode_reset": "select-none-before-every-game-v1",
        "native_shuffle": "unseeded; independent batches; not paired/CRN",
        "seat_schedule": "alternating-four-game-ABBA-BAAB",
        "arms": [arm.as_dict() for arm in ARMS],
        "replay_canary": canary,
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
    for arm in ARMS:
        row = by_label[arm.label]
        if arm.label == "exact_v22":
            print(
                f"  {arm.label}: weighted={row['weighted_win_rate']:.4f} control",
                flush=True,
            )
            continue
        assessment = assessments[arm.label]
        print(
            f"  {arm.label}: weighted={row['weighted_win_rate']:.4f} "
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
