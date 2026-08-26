#!/usr/bin/env python3
"""Split-sample live replay screen for bounded additive v22 score offsets.

Rules are frozen in reports/20260815_v22_additive_residual_prereg.md.  The old
exact-v22 submission is the design set; only offsets selected there are run on
the newer submission holdout.  Recorded outcomes are coverage labels, never
counterfactual rewards.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import statistics
import sys
import time
from collections import Counter
from dataclasses import dataclass
from typing import Any


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiments.live_v22_replay_audit import (  # noqa: E402
    DEFAULT_TEAM,
    _load_rows,
    parse_episode_source,
)
from experiments.v22_live_param_exposure import (  # noqa: E402
    FALLBACK_MODULE,
    _gate,
    _run_pass,
)
from scripts.candidate_h2h import (  # noqa: E402
    BASELINE as V22,
    CandidateAgent,
    assert_locked_baseline,
    sha256,
    tree_sha256,
)
from scripts.safe_json_output import reserve_json_output  # noqa: E402


DESIGN_REF = 55499962
HOLDOUT_REF = 55516725
FAMILIES = ("resource_timing_offset", "attachment_timing_offset")
GRID = (-100, -50, -25, -10, 10, 25, 50, 100)


@dataclass(frozen=True)
class AdditiveSpec:
    family: str
    offset: int

    @property
    def label(self) -> str:
        return f"{self.family}_{self.offset:+d}"

    def as_dict(self) -> dict[str, Any]:
        return {"label": self.label, "family": self.family, "offset": self.offset}


class AdditiveParamAgent(CandidateAgent):
    """An exact-v22 instance with one process-local additive score offset."""

    def __init__(self, source: pathlib.Path, spec: AdditiveSpec):
        if spec.family not in FAMILIES:
            raise SystemExit(f"unknown additive family: {spec.family}")
        super().__init__(source)
        fallback = self._private_modules.get(FALLBACK_MODULE)
        if fallback is None:
            raise SystemExit("exact-v22 fallback scorer module missing")
        original = fallback.main_score
        offset = int(spec.offset)

        if spec.family == "resource_timing_offset":
            resource_ids = {
                fallback.NIGHT,
                fallback.PAD,
                fallback.POFFIN,
                fallback.CANDY,
                fallback.STAMP,
                fallback.GEAR,
                fallback.GYM,
                fallback.LILLIE,
                fallback.PETREL,
                fallback.DAWN,
            }

            def additive_main_score(st, option, history):
                score = original(st, option, history)
                action_type = int(option.get("type", -1))
                source_id = int(option.get("source_id", 0) or 0)
                is_gym_ability = (
                    action_type == 10
                    and source_id == 0
                    and int(option.get("area", 0) or 0) == 7
                )
                is_resource_trainer = action_type == 7 and source_id in resource_ids
                return score + offset if is_gym_ability or is_resource_trainer else score

        else:
            def additive_main_score(st, option, history):
                score = original(st, option, history)
                is_manual_dark_attach = (
                    int(option.get("type", -1)) == 8
                    and int(option.get("source_id", 0) or 0) == fallback.DARK
                )
                return score + offset if is_manual_dark_attach else score

        fallback.main_score = additive_main_score


def _split_gate(
    result: dict[str, Any],
    *,
    total: int,
    minimum: int,
    maximum: int,
) -> dict[str, Any]:
    events = result["first_divergences"]
    faults = result["faults"]
    count = len(events)
    seats = Counter(str(event["seat"]) for event in events)
    outcomes = Counter("win" if event["reward"] == 1 else "loss" for event in events)
    early = sum(int(event["turn"]) <= 2 for event in events)
    early_fraction = early / count if count else 0.0
    ordinals = [int(event["decision_ordinal"]) for event in events]
    median_ordinal = statistics.median(ordinals) if ordinals else None

    if faults:
        status = "INVALID"
    elif count < minimum:
        status = "TOO_SPARSE"
    elif count > maximum or early_fraction > 0.25:
        status = "TOO_BROAD"
    elif (
        len(seats) < 2
        or min(seats.values()) < 1
        or outcomes.get("win", 0) < 1
        or outcomes.get("loss", 0) < 1
    ):
        status = "COVERAGE_FAIL"
    elif median_ordinal is None or median_ordinal < 10:
        status = "TOO_EARLY"
    else:
        status = "PASS"
    return {
        "status": status,
        "episodes_with_first_divergence": count,
        "episode_rate": round(count / total, 6),
        "by_seat": dict(sorted(seats.items())),
        "by_original_outcome": dict(sorted(outcomes.items())),
        "turn_le_2": early,
        "turn_le_2_fraction": round(early_fraction, 6),
        "decision_ordinal_median": median_ordinal,
        "required_episode_range": [minimum, maximum],
    }


def _choose_design(
    specs: list[AdditiveSpec],
    results: dict[str, dict[str, Any]],
) -> list[AdditiveSpec]:
    selected = []
    for family in FAMILIES:
        for direction in (-1, 1):
            passing = [
                spec for spec in specs
                if spec.family == family
                and spec.offset * direction > 0
                and results[spec.label]["design_gate"]["status"] == "PASS"
            ]
            if passing:
                selected.append(min(passing, key=lambda spec: abs(spec.offset)))
    return selected


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--episodes",
        action="append",
        type=parse_episode_source,
        required=True,
        metavar="REF=PATH",
    )
    parser.add_argument("--replay-dir", required=True)
    parser.add_argument("--team-name", default=DEFAULT_TEAM)
    parser.add_argument("--out", required=True)
    parser.add_argument("--overwrite-output", action="store_true")
    args = parser.parse_args()

    assert_locked_baseline()
    reservation = reserve_json_output(args.out, overwrite=args.overwrite_output)
    replay_dir = pathlib.Path(args.replay_dir).expanduser().resolve()
    if not replay_dir.is_dir():
        raise SystemExit(f"replay directory missing: {replay_dir}")
    public, validation = _load_rows(args.episodes)
    design_rows = [row for row in public if int(row["ref"]) == DESIGN_REF]
    holdout_rows = [row for row in public if int(row["ref"]) == HOLDOUT_REF]
    if len(design_rows) != 50 or len(holdout_rows) != 32:
        raise SystemExit(
            f"frozen split mismatch: design={len(design_rows)} holdout={len(holdout_rows)}"
        )

    started = time.time()
    grid_specs = [AdditiveSpec(family, offset) for family in FAMILIES for offset in GRID]
    design_controls = [AdditiveSpec(family, 0) for family in FAMILIES]
    design_pass = _run_pass(
        design_rows,
        replay_dir,
        grid_specs + design_controls,
        team_name=args.team_name,
        include_controls=False,
        agent_class=AdditiveParamAgent,
    )
    for spec in design_controls:
        row = design_pass["results"][spec.label]
        if row["first_divergences"] or row["faults"]:
            raise SystemExit(f"offset=0 design control failed: {spec.family}")

    design_results = {}
    for spec in grid_specs:
        row = design_pass["results"][spec.label]
        design_results[spec.label] = {
            **spec.as_dict(),
            **row,
            "design_gate": _split_gate(row, total=50, minimum=5, maximum=20),
        }
    selected_specs = _choose_design(grid_specs, design_results)

    holdout_controls = [AdditiveSpec(family, 0) for family in FAMILIES]
    holdout_pass = _run_pass(
        holdout_rows,
        replay_dir,
        selected_specs + holdout_controls,
        team_name=args.team_name,
        include_controls=False,
        agent_class=AdditiveParamAgent,
    )
    for spec in holdout_controls:
        row = holdout_pass["results"][spec.label]
        if row["first_divergences"] or row["faults"]:
            raise SystemExit(f"offset=0 holdout control failed: {spec.family}")

    validation_results = {}
    promote = []
    for spec in selected_specs:
        design_row = design_results[spec.label]
        holdout_row = holdout_pass["results"][spec.label]
        holdout_gate = _split_gate(holdout_row, total=32, minimum=3, maximum=13)
        combined_events = (
            design_row["first_divergences"] + holdout_row["first_divergences"]
        )
        combined_gate = _gate(combined_events, 82)
        combined_faults = design_row["faults"] + holdout_row["faults"]
        if combined_faults:
            combined_gate = {**combined_gate, "status": "INVALID"}
        row = {
            **spec.as_dict(),
            "design_gate": design_row["design_gate"],
            "holdout_gate": holdout_gate,
            "combined_gate": combined_gate,
            "holdout": holdout_row,
        }
        validation_results[spec.label] = row
        if (
            row["design_gate"]["status"] == "PASS"
            and row["holdout_gate"]["status"] == "PASS"
            and row["combined_gate"]["status"] == "PASS"
        ):
            promote.append({
                **spec.as_dict(),
                "design_gate": row["design_gate"],
                "holdout_gate": row["holdout_gate"],
                "combined_gate": row["combined_gate"],
            })

    report = {
        "created_unix": time.time(),
        "method": "split-sample-live-replay-additive-first-divergence-v1",
        "preregistration": str(
            ROOT / "reports" / "20260815_v22_additive_residual_prereg.md"
        ),
        "candidate": str(V22),
        "candidate_tree_sha256": tree_sha256(V22),
        "candidate_main_sha256": sha256(V22 / "main.py"),
        "candidate_deck_sha256": sha256(V22 / "deck.csv"),
        "episode_sources": [
            {"ref": ref, "path": str(path), "sha256": sha256(path)}
            for ref, path in args.episodes
        ],
        "replay_dir": str(replay_dir),
        "validation_excluded": len(validation),
        "split": {
            "design": {"ref": DESIGN_REF, "episodes": len(design_rows)},
            "holdout": {"ref": HOLDOUT_REF, "episodes": len(holdout_rows)},
        },
        "grid": list(GRID),
        "post_divergence_policy": "censor variant for episode suffix",
        "recorded_wl_use": "coverage labels only; not counterfactual reward",
        "design_exact_replay": {
            "active_calls": design_pass["active_calls_exact"],
            "decision_calls": design_pass["decision_calls_exact"],
            "mismatches": 0,
        },
        "holdout_exact_replay": {
            "active_calls": holdout_pass["active_calls_exact"],
            "decision_calls": holdout_pass["decision_calls_exact"],
            "mismatches": 0,
        },
        "controls": {
            "design": {
                spec.family: design_pass["results"][spec.label]
                for spec in design_controls
            },
            "holdout": {
                spec.family: holdout_pass["results"][spec.label]
                for spec in holdout_controls
            },
        },
        "design_results": design_results,
        "selected_from_design": [spec.as_dict() for spec in selected_specs],
        "holdout_results": validation_results,
        "selected_for_blocked_independent_wl": promote,
        "native_rng_note": (
            "later W/L must be blocked independent trials; native shuffle is unseeded"
        ),
        "elapsed_s": round(time.time() - started, 3),
    }
    reservation.write(report)
    print(
        f"[done] design_candidates={len(grid_specs)} selected={len(selected_specs)} "
        f"promote={len(promote)} elapsed={report['elapsed_s']}s -> {args.out}",
        flush=True,
    )
    for spec in grid_specs:
        gate = design_results[spec.label]["design_gate"]
        print(
            f"  design {spec.label}: {gate['status']} "
            f"D={gate['episodes_with_first_divergence']}/50",
            flush=True,
        )
    for label, row in validation_results.items():
        print(
            f"  holdout {label}: {row['holdout_gate']['status']} "
            f"D={row['holdout_gate']['episodes_with_first_divergence']}/32 "
            f"combined={row['combined_gate']['status']}",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
