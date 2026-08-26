#!/usr/bin/env python3
"""Screen dense v22 score perturbations on exact live replay states.

This is an *exposure* gate, not an outcome estimator.  Each variant follows
the recorded exact-v22 trajectory only until its first semantic action
disagreement.  States after that point belong to the incumbent world and are
therefore not used as paired counterfactuals.

The screen deliberately precedes locally generated W/L games.  It rejects
parameters that are effectively dead on the live distribution as well as
changes that alter nearly every episode too early to qualify as a local
residual.  The locked candidate tree is never edited.
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
    _classify_deck,
    _load_rows,
    _opponent_deck,
    parse_episode_source,
)
from scripts.candidate_h2h import (  # noqa: E402
    BASELINE as V22,
    CandidateAgent,
    assert_locked_baseline,
    sha256,
    tree_sha256,
)
from scripts.safe_json_output import reserve_json_output  # noqa: E402


FALLBACK_MODULE = "policies.v22.validated_fallback_policy"
MAIN_MODULE = "policies.v22.main"
FAMILIES = ("resource_timing", "attachment_timing", "target_asset")
INITIAL_FACTORS = (0.90, 0.95, 1.05, 1.10)
SEMANTIC_KEYS = (
    "type",
    "source_id",
    "source_serial",
    "source_zone",
    "source_rel",
    "target_id",
    "target_serial",
    "target_area",
    "target_rel",
    "attack_id",
    "area",
)


@dataclass(frozen=True)
class VariantSpec:
    family: str
    factor: float
    adaptive: bool = False

    @property
    def label(self) -> str:
        delta_bp = round((self.factor - 1.0) * 10_000)
        return f"{self.family}_{delta_bp:+d}bp"

    def as_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "family": self.family,
            "factor": self.factor,
            "delta_pct": round((self.factor - 1.0) * 100, 4),
            "adaptive": self.adaptive,
        }


class ParamVariantAgent(CandidateAgent):
    """An isolated exact-v22 instance with one in-memory score perturbation."""

    def __init__(self, source: pathlib.Path, spec: VariantSpec):
        if spec.family not in FAMILIES:
            raise SystemExit(f"unknown parameter family: {spec.family}")
        super().__init__(source)
        fallback = self._private_modules.get(FALLBACK_MODULE)
        if fallback is None:
            raise SystemExit("exact-v22 fallback scorer module missing")

        factor = float(spec.factor)
        if spec.family == "resource_timing":
            original = fallback.main_score
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

            def resource_main_score(st, option, history):
                score = original(st, option, history)
                action_type = int(option.get("type", -1))
                source_id = int(option.get("source_id", 0) or 0)
                is_gym_ability = (
                    action_type == 10
                    and source_id == 0
                    and int(option.get("area", 0) or 0) == 7
                )
                is_resource_trainer = action_type == 7 and source_id in resource_ids
                return score * factor if is_gym_ability or is_resource_trainer else score

            fallback.main_score = resource_main_score

        elif spec.family == "attachment_timing":
            original = fallback.main_score

            def attachment_main_score(st, option, history):
                score = original(st, option, history)
                is_manual_dark_attach = (
                    int(option.get("type", -1)) == 8
                    and int(option.get("source_id", 0) or 0) == fallback.DARK
                )
                return score * factor if is_manual_dark_attach else score

            fallback.main_score = attachment_main_score

        else:
            # Scale the asset terms of the *live* fallback scorer relative to
            # its HP clock.  target_evaluator.py has an energy*40 term, but that
            # module has no caller in exact v22 and is intentionally excluded.
            def target_threat_score(
                st,
                option,
                damage_amount=0,
                bench_damage=False,
                munk_bonus=260,
                basic_bonus=70,
            ):
                cid = int(option.get("source_id", 0) or 0)
                hp = fallback.remaining_hp(st, option)
                obj = fallback.card_obj(st, option)
                max_hp = int(obj.get("maxHp", 0) or hp)
                prize = fallback.prize_value(cid, max_hp)

                asset = prize * 120
                if cid == fallback.MUNK:
                    asset += munk_bonus
                elif cid in (fallback.IMP, fallback.SNOR, 741, 400, 343, 742):
                    asset += basic_bonus
                if int(option.get("source_zone", 0)) == 5:
                    asset += 25

                score = asset * factor
                if hp > 0:
                    # Immediate KO and Bench-only legality-like penalties stay
                    # hard constants; only the ordinary asset/clock tradeoff moves.
                    if damage_amount and hp <= damage_amount:
                        score += 1000 + prize * 300
                    score += max(0, 240 - hp)
                    if hp in (40, 50, 60, 70, 80, 90, 100, 110, 120):
                        score += 30
                if bench_damage and int(option.get("source_zone", 0)) != 5:
                    score -= 1000
                return score

            fallback.threat_score = target_threat_score


def _selected_semantics(
    obs: dict[str, Any],
    action: list[int],
    semantic_fn: Any,
) -> tuple[tuple[tuple[str, int], ...], ...]:
    select = obs.get("select")
    if not isinstance(select, dict):
        return ((('deck_sha', hash(tuple(int(card) for card in action))),),)
    raw_options = select.get("option") or []
    rows = []
    for index in action:
        semantic = semantic_fn(obs, raw_options[index])
        rows.append(tuple((key, int(semantic.get(key, 0) or 0)) for key in SEMANTIC_KEYS))
    return tuple(sorted(rows))


def _semantics_json(signature: tuple[tuple[tuple[str, int], ...], ...]) -> list[dict[str, int]]:
    return [dict(row) for row in signature]


def _validate_action(obs: dict[str, Any], action: Any) -> str | None:
    if not isinstance(action, list) or not all(isinstance(index, int) for index in action):
        return "action is not list[int]"
    select = obs.get("select")
    if select is None:
        if len(action) != 60:
            return f"deck action length={len(action)}"
        return None
    if not isinstance(select, dict):
        return "select is neither dict nor None"
    options = select.get("option") or []
    minimum = int(select.get("minCount", 0) or 0)
    maximum = int(select.get("maxCount", 0) or 0)
    if not minimum <= len(action) <= maximum:
        return f"selection count={len(action)} outside [{minimum},{maximum}]"
    if len(set(action)) != len(action):
        return "duplicate option indices"
    if any(index < 0 or index >= len(options) for index in action):
        return f"option index outside [0,{len(options)})"
    return None


def _gate(events: list[dict[str, Any]], total_episodes: int) -> dict[str, Any]:
    count = len(events)
    refs = Counter(str(event["ref"]) for event in events)
    seats = Counter(str(event["seat"]) for event in events)
    outcomes = Counter("win" if event["reward"] == 1 else "loss" for event in events)
    early = sum(int(event["turn"]) <= 2 for event in events)
    early_fraction = early / count if count else 0.0
    ordinals = [int(event["decision_ordinal"]) for event in events]
    median_ordinal = statistics.median(ordinals) if ordinals else None

    if count < 8:
        status = "TOO_SPARSE"
    elif count > 33 or early_fraction > 0.25:
        status = "TOO_BROAD"
    elif (
        len(refs) < 2
        or min(refs.values()) < 3
        or len(seats) < 2
        or min(seats.values()) < 2
        or outcomes.get("win", 0) < 2
        or outcomes.get("loss", 0) < 2
    ):
        status = "COVERAGE_FAIL"
    elif median_ordinal is None or median_ordinal < 10:
        status = "TOO_EARLY"
    else:
        status = "PASS"

    return {
        "status": status,
        "episodes_with_first_divergence": count,
        "episode_rate": round(count / total_episodes, 6) if total_episodes else None,
        "by_ref": dict(sorted(refs.items())),
        "by_seat": dict(sorted(seats.items())),
        "by_original_outcome": dict(sorted(outcomes.items())),
        "turn_le_2": early,
        "turn_le_2_fraction": round(early_fraction, 6),
        "decision_ordinal_median": median_ordinal,
        "rules": {
            "episode_count": "8 <= D <= 33 of 82",
            "ref_coverage": "each of two refs >= 3",
            "seat_coverage": "each seat >= 2",
            "outcome_coverage": "recorded wins and losses each >= 2",
            "early_divergence": "turn<=2 <= 25% of D",
            "decision_ordinal": "median >= 10",
        },
    }


def _run_pass(
    rows: list[dict[str, Any]],
    replay_dir: pathlib.Path,
    specs: list[Any],
    *,
    team_name: str,
    include_controls: bool,
    agent_class: Any = ParamVariantAgent,
) -> dict[str, Any]:
    exact = CandidateAgent(V22)
    agents: dict[str, CandidateAgent] = {
        spec.label: agent_class(V22, spec) for spec in specs
    }
    if include_controls and agent_class is not ParamVariantAgent:
        raise ValueError("built-in factor=1 controls apply only to ParamVariantAgent")
    controls = [VariantSpec(family, 1.0) for family in FAMILIES] if include_controls else []
    for spec in controls:
        agents[f"control:{spec.family}"] = ParamVariantAgent(V22, spec)

    exact_main = exact._private_modules.get(MAIN_MODULE)
    if exact_main is None or not hasattr(exact_main, "_semantic"):
        raise SystemExit("exact-v22 semantic action resolver missing")
    semantic_fn = exact_main._semantic

    events: dict[str, list[dict[str, Any]]] = {label: [] for label in agents}
    equivalent_index_changes: Counter[str] = Counter()
    calls: Counter[str] = Counter()
    faults: dict[str, list[dict[str, Any]]] = {label: [] for label in agents}
    active_calls = 0
    decision_calls = 0

    exact_deck = exact.deck()
    for label, agent in agents.items():
        if agent.deck() != exact_deck:
            raise SystemExit(f"variant changed deck: {label}")

    for row in rows:
        episode_id = int(row["id"])
        replay_path = replay_dir / f"episode-{episode_id}-replay.json"
        if not replay_path.is_file():
            raise SystemExit(f"missing replay: {replay_path}")
        replay = json.loads(replay_path.read_text(encoding="utf-8"))
        steps = replay.get("steps") or []
        seat = int(row["seat"])
        names = (replay.get("info") or {}).get("TeamNames") or []
        if seat not in (0, 1) or len(names) != 2 or names[seat] != team_name:
            raise SystemExit(
                f"team/seat mismatch ep={episode_id}: seat={seat} names={names}"
            )
        rewards = replay.get("rewards") or []
        if len(rewards) != 2 or int(rewards[seat]) != int(row["reward"]):
            raise SystemExit(f"reward mismatch ep={episode_id}")
        opponent_deck = _opponent_deck(replay, 1 - seat)
        archetype = _classify_deck(opponent_deck) if len(opponent_deck) == 60 else "unknown"

        # Reset every private policy state before replaying the episode.
        if exact.deck() != exact_deck:
            raise SystemExit("exact-v22 deck changed between episodes")
        alive = set(agents)
        for label, agent in agents.items():
            if agent.deck() != exact_deck:
                raise SystemExit(f"variant deck changed between episodes: {label}")

        ordinal = 0
        for step_index in range(len(steps) - 1):
            if seat >= len(steps[step_index]) or seat >= len(steps[step_index + 1]):
                continue
            record = steps[step_index][seat]
            if record.get("status") != "ACTIVE":
                continue
            obs = record.get("observation") or {}
            if not isinstance(obs, dict):
                continue
            expected = steps[step_index + 1][seat].get("action")
            if not isinstance(expected, list):
                expected = []

            active_calls += 1
            exact_action = exact(obs)
            if exact_action != expected:
                raise SystemExit(
                    f"exact-v22 replay mismatch ep={episode_id} step={step_index}: "
                    f"expected={expected} actual={exact_action}"
                )
            is_decision = isinstance(obs.get("select"), dict)
            if is_decision:
                ordinal += 1
                decision_calls += 1
            exact_signature = _selected_semantics(obs, exact_action, semantic_fn)

            for label in tuple(alive):
                agent = agents[label]
                calls[label] += 1
                try:
                    action = agent(obs)
                    problem = _validate_action(obs, action)
                except Exception as exc:  # pragma: no cover - defensive audit path
                    action = []
                    problem = f"{type(exc).__name__}: {exc}"
                if problem is not None:
                    faults[label].append({
                        "episode": episode_id,
                        "step": step_index,
                        "problem": problem,
                    })
                    alive.remove(label)
                    continue
                signature = _selected_semantics(obs, action, semantic_fn)
                if signature == exact_signature:
                    if action != exact_action:
                        equivalent_index_changes[label] += 1
                    continue

                select = obs.get("select") or {}
                current = obs.get("current") or {}
                events[label].append({
                    "episode": episode_id,
                    "ref": int(row["ref"]),
                    "seat": seat,
                    "reward": int(row["reward"]),
                    "end": row.get("end"),
                    "opponent": row.get("opp"),
                    "opponent_submission": row.get("opp_sub"),
                    "opponent_archetype": archetype,
                    "step_index": step_index,
                    "turn": int(current.get("turn", 0) or 0),
                    "decision_ordinal": ordinal,
                    "context": int(select.get("context", -1) if select.get("context") is not None else -1),
                    "selection_type": int(select.get("type", -1) if select.get("type") is not None else -1),
                    "incumbent_action": exact_action,
                    "variant_action": action,
                    "incumbent_semantics": _semantics_json(exact_signature),
                    "variant_semantics": _semantics_json(signature),
                })
                # The next recorded state is no longer a valid state for this
                # variant.  Do not feed it any suffix of the incumbent episode.
                alive.remove(label)

    total = len(rows)
    results = {}
    for label in agents:
        gate = _gate(events[label], total)
        results[label] = {
            "gate": gate,
            "agent_calls_before_censoring": calls[label],
            "equivalent_index_only_changes": equivalent_index_changes[label],
            "faults": faults[label],
            "first_divergences": events[label],
        }
    return {
        "episodes": total,
        "active_calls_exact": active_calls,
        "decision_calls_exact": decision_calls,
        "results": results,
    }


def _select_for_wl(
    specs: list[VariantSpec], results: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    selected = []
    for family in FAMILIES:
        for direction in (-1, 1):
            candidates = [
                spec for spec in specs
                if spec.family == family
                and (spec.factor - 1.0) * direction > 0
                and results[spec.label]["gate"]["status"] == "PASS"
            ]
            if not candidates:
                continue
            winner = min(candidates, key=lambda spec: abs(spec.factor - 1.0))
            selected.append({
                **winner.as_dict(),
                "gate": results[winner.label]["gate"],
            })
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
    replay_dir = pathlib.Path(args.replay_dir).expanduser().resolve()
    if not replay_dir.is_dir():
        raise SystemExit(f"replay directory missing: {replay_dir}")
    reservation = reserve_json_output(args.out, overwrite=args.overwrite_output)
    public_rows, validation_rows = _load_rows(args.episodes)
    if len(public_rows) != 82:
        raise SystemExit(
            f"pre-registered snapshot requires 82 PUBLIC episodes, got {len(public_rows)}"
        )

    started = time.time()
    initial_specs = [
        VariantSpec(family, factor)
        for family in FAMILIES
        for factor in INITIAL_FACTORS
    ]
    initial = _run_pass(
        public_rows,
        replay_dir,
        initial_specs,
        team_name=args.team_name,
        include_controls=True,
    )
    for family in FAMILIES:
        control = initial["results"][f"control:{family}"]
        if control["first_divergences"] or control["faults"]:
            raise SystemExit(f"factor=1 control failed for {family}")

    adaptive_specs = []
    for family in FAMILIES:
        for factor, adaptive_factor in ((0.95, 0.975), (1.05, 1.025)):
            label = VariantSpec(family, factor).label
            if initial["results"][label]["gate"]["status"] == "TOO_BROAD":
                adaptive_specs.append(
                    VariantSpec(family, adaptive_factor, adaptive=True))

    adaptive = None
    if adaptive_specs:
        adaptive = _run_pass(
            public_rows,
            replay_dir,
            adaptive_specs,
            team_name=args.team_name,
            include_controls=False,
        )

    results = {
        spec.label: {
            **spec.as_dict(),
            **initial["results"][spec.label],
        }
        for spec in initial_specs
    }
    if adaptive is not None:
        for spec in adaptive_specs:
            results[spec.label] = {
                **spec.as_dict(),
                **adaptive["results"][spec.label],
            }

    all_specs = initial_specs + adaptive_specs
    selected = _select_for_wl(all_specs, results)
    report = {
        "created_unix": time.time(),
        "method": "live-replay-first-semantic-divergence-v1",
        "interpretation": (
            "behavior exposure gate only; recorded W/L is coverage metadata, "
            "not a counterfactual reward"
        ),
        "post_divergence_policy": "censor variant for the rest of that episode",
        "candidate": str(V22),
        "candidate_main_sha256": sha256(V22 / "main.py"),
        "candidate_deck_sha256": sha256(V22 / "deck.csv"),
        "candidate_tree_sha256": tree_sha256(V22),
        "episode_sources": [
            {"ref": ref, "path": str(path), "sha256": sha256(path)}
            for ref, path in args.episodes
        ],
        "replay_dir": str(replay_dir),
        "public_episodes": len(public_rows),
        "validation_excluded": len(validation_rows),
        "exact_replay": {
            "active_calls": initial["active_calls_exact"],
            "decision_calls": initial["decision_calls_exact"],
            "action_mismatches": 0,
        },
        "factor_one_controls": {
            family: initial["results"][f"control:{family}"]
            for family in FAMILIES
        },
        "parameter_definitions": {
            "resource_timing": (
                "scale active Gym search ability and setup/search/draw/recovery "
                "Trainer MAIN scores; exclude Pokemon plays, Boss and Scrapper"
            ),
            "attachment_timing": "scale manual Darkness attachment MAIN scores",
            "target_asset": (
                "scale the called fallback threat scorer's prize/role/bench asset "
                "terms relative to HP clock; keep immediate-KO and Bench-only "
                "hard constants fixed; exclude dead target_evaluator.py"
            ),
        },
        "initial_factors": list(INITIAL_FACTORS),
        "adaptive_rule": (
            "only when +/-5% is TOO_BROAD, screen +/-2.5% once in that direction"
        ),
        "adaptive_specs": [spec.as_dict() for spec in adaptive_specs],
        "results": results,
        "selected_for_blocked_independent_wl": selected,
        "native_rng_note": (
            "no native shuffle seed setter; any later W/L stage is a blocked "
            "independent trial, not paired/CRN"
        ),
        "elapsed_s": round(time.time() - started, 3),
    }
    reservation.write(report)
    print(
        f"[done] public={len(public_rows)} variants={len(results)} "
        f"selected={len(selected)} elapsed={report['elapsed_s']}s -> {args.out}",
        flush=True,
    )
    for label, row in sorted(results.items()):
        gate = row["gate"]
        print(
            f"  {label}: {gate['status']} D={gate['episodes_with_first_divergence']} "
            f"rate={gate['episode_rate']}",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
