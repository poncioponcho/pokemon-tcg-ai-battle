#!/usr/bin/env python3
"""First-divergence screen for the preregistered early-Dawn anomaly."""

from __future__ import annotations

import argparse
import pathlib
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


DAWN = 1231
PENALTIES = (100, 200, 300, 400, 600, 800, 1200)
PREREG = ROOT / "reports" / "20260815_v22_early_dawn_prereg.md"


@dataclass(frozen=True)
class DawnSpec:
    penalty: int

    @property
    def label(self) -> str:
        return f"early_dawn_penalty_{self.penalty}"

    def as_dict(self) -> dict[str, Any]:
        return {"label": self.label, "penalty": self.penalty}


class EarlyDawnAgent(CandidateAgent):
    """Exact v22 with one in-memory early-Dawn score penalty."""

    def __init__(self, source: pathlib.Path, spec: DawnSpec):
        if spec.penalty < 0:
            raise SystemExit("Dawn penalty must be non-negative")
        super().__init__(source)
        fallback = self._private_modules.get(FALLBACK_MODULE)
        if fallback is None:
            raise SystemExit("exact-v22 fallback scorer module missing")
        original = fallback.main_score
        penalty = int(spec.penalty)

        def early_dawn_score(st, option, history):
            score = original(st, option, history)
            is_early_dawn = (
                int(st.get("turn", 0) or 0) <= 4
                and int(option.get("type", -1)) == 7
                and int(option.get("source_id", 0) or 0) == DAWN
            )
            return score - penalty if is_early_dawn else score

        fallback.main_score = early_dawn_score


def _replacement_category(event: dict[str, Any]) -> str:
    rows = event.get("variant_semantics") or []
    if not rows:
        return "decline"
    first = rows[0]
    action_type = int(first.get("type", -1))
    source = int(first.get("source_id", 0) or 0)
    if action_type == 7:
        if source == 1182:
            return "early_boss"
        return f"play:{source}"
    if action_type == 8:
        return "attach"
    if action_type == 9:
        return "evolve"
    if action_type == 10:
        return "ability"
    if action_type == 12:
        return "retreat"
    if action_type == 13:
        return "attack"
    if action_type == 14:
        return "end_turn"
    return f"type:{action_type}"


def _gate(row: dict[str, Any]) -> dict[str, Any]:
    events = row["first_divergences"]
    count = len(events)
    refs = Counter(str(event["ref"]) for event in events)
    seats = Counter(str(event["seat"]) for event in events)
    outcomes = Counter("win" if event["reward"] == 1 else "loss" for event in events)
    replacements = Counter(_replacement_category(event) for event in events)
    unsafe = sum(replacements[name] for name in ("decline", "end_turn", "early_boss"))
    unsafe_fraction = unsafe / count if count else 0.0
    scope_ok = all(
        int(event["turn"]) <= 4 and int(event["context"]) == 0
        for event in events
    )

    if row["faults"]:
        status = "INVALID"
    elif count < 8:
        status = "TOO_SPARSE"
    elif count > 14:
        status = "TOO_BROAD"
    elif (
        len(refs) < 2
        or min(refs.values()) < 3
        or len(seats) < 2
        or min(seats.values()) < 1
        or outcomes.get("win", 0) < 2
        or outcomes.get("loss", 0) < 2
    ):
        status = "COVERAGE_FAIL"
    elif not scope_ok:
        status = "SCOPE_FAIL"
    elif unsafe_fraction > 0.25:
        status = "UNSAFE_REPLACEMENTS"
    else:
        status = "PASS"
    return {
        "status": status,
        "episodes_with_first_divergence": count,
        "by_ref": dict(sorted(refs.items())),
        "by_seat": dict(sorted(seats.items())),
        "by_original_outcome": dict(sorted(outcomes.items())),
        "replacement_categories": dict(sorted(replacements.items())),
        "unsafe_replacements": unsafe,
        "unsafe_replacement_fraction": round(unsafe_fraction, 6),
        "scope_ok": scope_ok,
        "rules": {
            "episode_count": "8 <= D <= 14",
            "ref_coverage": "each ref >= 3",
            "seat_coverage": "each seat >= 1",
            "outcome_coverage": "wins and losses each >= 2",
            "scope": "context=0 and turn<=4",
            "unsafe_fraction": "decline/end_turn/early_boss <= 25%",
        },
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
    if not PREREG.is_file():
        raise SystemExit(f"preregistration missing: {PREREG}")
    reservation = reserve_json_output(args.out, overwrite=args.overwrite_output)
    replay_dir = pathlib.Path(args.replay_dir).expanduser().resolve()
    public, validation = _load_rows(args.episodes)
    if len(public) != 82:
        raise SystemExit(f"frozen screen requires 82 PUBLIC episodes, got {len(public)}")

    specs = [DawnSpec(0)] + [DawnSpec(penalty) for penalty in PENALTIES]
    started = time.time()
    run = _run_pass(
        public,
        replay_dir,
        specs,
        team_name=args.team_name,
        include_controls=False,
        agent_class=EarlyDawnAgent,
    )
    control = run["results"][DawnSpec(0).label]
    if control["first_divergences"] or control["faults"]:
        raise SystemExit("penalty=0 control diverged or faulted")

    results = {}
    passing = []
    for penalty in PENALTIES:
        spec = DawnSpec(penalty)
        row = run["results"][spec.label]
        gate = _gate(row)
        results[spec.label] = {**spec.as_dict(), **row, "behavior_gate": gate}
        if gate["status"] == "PASS":
            passing.append(spec)
    selected = min(passing, key=lambda spec: spec.penalty) if passing else None

    report = {
        "created_unix": time.time(),
        "method": "exact-v22-early-dawn-first-divergence-v1",
        "interpretation": (
            "behavior exposure/safety only; recorded W/L is coverage metadata, "
            "not counterfactual reward"
        ),
        "preregistration": str(PREREG),
        "preregistration_sha256": sha256(PREREG),
        "candidate": str(V22),
        "candidate_tree_sha256": tree_sha256(V22),
        "candidate_main_sha256": sha256(V22 / "main.py"),
        "candidate_deck_sha256": sha256(V22 / "deck.csv"),
        "episode_sources": [
            {"ref": ref, "path": str(path), "sha256": sha256(path)}
            for ref, path in args.episodes
        ],
        "public_episodes": len(public),
        "validation_excluded": len(validation),
        "post_divergence_policy": "censor variant for episode suffix",
        "penalties": list(PENALTIES),
        "exact_replay": {
            "active_calls": run["active_calls_exact"],
            "decision_calls": run["decision_calls_exact"],
            "action_mismatches": 0,
        },
        "zero_control": control,
        "results": results,
        "selected_for_wl_preregistration": (
            None if selected is None else {
                **selected.as_dict(),
                "behavior_gate": results[selected.label]["behavior_gate"],
            }
        ),
        "materialized": False,
        "submitted": False,
        "elapsed_s": round(time.time() - started, 3),
    }
    reservation.write(report)
    print(
        f"[done] selected={report['selected_for_wl_preregistration']} "
        f"elapsed={report['elapsed_s']}s -> {args.out}",
        flush=True,
    )
    for penalty in PENALTIES:
        label = DawnSpec(penalty).label
        gate = results[label]["behavior_gate"]
        print(
            f"  penalty={penalty}: {gate['status']} "
            f"D={gate['episodes_with_first_divergence']} "
            f"replacements={gate['replacement_categories']}",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
