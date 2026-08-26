#!/usr/bin/env python3
"""Map exact-v22 live decisions to actionable policy surfaces.

This is a hypothesis audit, not a causal estimator.  It replays the frozen
10:45 CST PUBLIC snapshot, attributes each final action to a manual guard or
hierarchical layer/job, and reports episode-level exposure associations
separately for the old submission (design) and new submission (replication).

Only pre-divergence exact-v22 behavior is inspected.  Recorded W/L is used to
prioritize surfaces for a future intervention; it never acts as a
counterfactual reward and this script does not create a candidate.
"""

from __future__ import annotations

import argparse
import json
import math
import pathlib
import sys
import time
from collections import Counter, defaultdict
from typing import Any, cast


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiments.live_v22_replay_audit import (  # noqa: E402
    DEFAULT_TEAM,
    _classify_deck,
    _first_manual_guard,
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


MAIN_MODULE = "policies.v22.main"
MANUAL_MODULE = "policies.v22.manual_guards"
HIERARCHICAL_MODULE = "policies.v22.hierarchical_policy"
FALLBACK_MODULE = "policies.v22.validated_fallback_policy"


def _guard_name(fn: Any) -> str:
    return str(fn.__module__).rsplit(".", 1)[-1]


def _semantic_signature(
    main: Any, obs: dict[str, Any], action: list[int]
) -> tuple[tuple[int, ...], ...]:
    select = obs.get("select") or {}
    raw = select.get("option") or []
    keys = (
        "type", "source_id", "source_serial", "source_zone", "source_rel",
        "target_id", "target_serial", "target_area", "target_rel",
        "attack_id", "area",
    )
    rows = []
    for index in action:
        option = main._semantic(obs, raw[index])
        rows.append(tuple(int(option.get(key, 0) or 0) for key in keys))
    return tuple(sorted(rows))


def _action_category(options: list[dict[str, Any]], action: list[int]) -> str:
    if not action:
        return "decline"
    first = options[action[0]]
    action_type = int(first.get("type", -1))
    source = int(first.get("source_id", 0) or 0)
    if action_type == 7:
        if source in (104, 112, 646, 647, 648, 860):
            return f"play_pokemon:{source}"
        if source == 1182:
            return "play_boss"
        if source == 1137:
            return "play_scrapper"
        return f"play_resource:{source}"
    if action_type == 8:
        target = int(first.get("target_id", 0) or 0)
        area = int(first.get("target_area", 0) or 0)
        return f"attach:{target}:area{area}"
    if action_type == 9:
        return f"evolve:{source}"
    if action_type == 10:
        return f"ability:{source or int(first.get('area', 0) or 0)}"
    if action_type == 12:
        return "retreat"
    if action_type == 13:
        return f"attack:{int(first.get('attack_id', 0) or 0)}"
    if action_type == 14:
        return "end_turn"
    return f"type:{action_type}"


def _fisher_two_sided(a: int, b: int, c: int, d: int) -> float:
    """Two-sided Fisher exact p for [[a,b],[c,d]]."""
    row1 = a + b
    row2 = c + d
    col1 = a + c
    total = row1 + row2
    if total == 0:
        return 1.0

    def probability(x: int) -> float:
        if not (0 <= x <= row1 and 0 <= col1 - x <= row2):
            return 0.0
        return (
            math.comb(row1, x) * math.comb(row2, col1 - x)
            / math.comb(total, col1)
        )

    observed = probability(a)
    lower = max(0, col1 - row2)
    upper = min(row1, col1)
    return min(1.0, sum(
        probability(x) for x in range(lower, upper + 1)
        if probability(x) <= observed + 1e-15
    ))


def _association(
    games: list[dict[str, Any]], feature: str
) -> dict[str, Any]:
    exposed = [game for game in games if feature in game["features"]]
    unexposed = [game for game in games if feature not in game["features"]]
    ew = sum(game["reward"] == 1 for game in exposed)
    el = sum(game["reward"] == -1 for game in exposed)
    uw = sum(game["reward"] == 1 for game in unexposed)
    ul = sum(game["reward"] == -1 for game in unexposed)
    exposed_wr = ew / (ew + el) if ew + el else None
    unexposed_wr = uw / (uw + ul) if uw + ul else None
    delta = (
        exposed_wr - unexposed_wr
        if exposed_wr is not None and unexposed_wr is not None
        else None
    )
    return {
        "exposed": len(exposed),
        "unexposed": len(unexposed),
        "exposed_wins": ew,
        "exposed_losses": el,
        "unexposed_wins": uw,
        "unexposed_losses": ul,
        "exposed_win_rate": round(exposed_wr, 6) if exposed_wr is not None else None,
        "unexposed_win_rate": round(unexposed_wr, 6) if unexposed_wr is not None else None,
        "delta": round(delta, 6) if delta is not None else None,
        "fisher_two_sided": round(_fisher_two_sided(ew, el, uw, ul), 8),
    }


def _add_feature(features: set[str], base: str, turn: int) -> None:
    features.add(base)
    if turn <= 2:
        features.add(base + "@turn<=2")
    if turn <= 4:
        features.add(base + "@turn<=4")


def _candidate_findings(
    associations: dict[str, dict[str, dict[str, Any]]]
) -> list[dict[str, Any]]:
    findings = []
    for feature, by_ref in associations.items():
        design = by_ref.get("55499962")
        replication = by_ref.get("55516725")
        if design is None or replication is None:
            continue
        # Restrict intervention hypotheses to early, genuinely action-changing
        # policy surfaces.  Descriptive action/context features remain in the
        # full association map but cannot nominate a candidate by themselves.
        if not feature.startswith("control:") or not feature.endswith("@turn<=4"):
            continue
        if (
            design["exposed"] < 5
            or design["unexposed"] < 5
            or replication["exposed"] < 3
            or replication["unexposed"] < 3
        ):
            continue
        d1 = design["delta"]
        d2 = replication["delta"]
        if d1 is None or d2 is None or d1 == 0 or d2 == 0 or d1 * d2 <= 0:
            continue
        findings.append({
            "feature": feature,
            "direction": "loss_associated" if d1 < 0 else "win_associated",
            "design": design,
            "replication": replication,
            "min_abs_delta": round(min(abs(d1), abs(d2)), 6),
            "causal_status": "hypothesis_only",
        })
    return sorted(
        findings,
        key=lambda row: (-row["min_abs_delta"], row["feature"]),
    )


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
    public, validation = _load_rows(args.episodes)
    if len(public) != 82:
        raise SystemExit(f"frozen audit requires 82 PUBLIC episodes, got {len(public)}")

    agent = CandidateAgent(V22)
    main_module = agent._private_modules.get(MAIN_MODULE)
    manual_module = agent._private_modules.get(MANUAL_MODULE)
    hierarchy = agent._private_modules.get(HIERARCHICAL_MODULE)
    fallback = agent._private_modules.get(FALLBACK_MODULE)
    if any(module is None for module in (
        main_module, manual_module, hierarchy, fallback
    )):
        raise SystemExit("exact-v22 policy modules missing")
    assert main_module is not None
    assert manual_module is not None
    assert hierarchy is not None
    assert fallback is not None
    guards = tuple(manual_module.GUARDS)
    exact_deck = agent.deck()
    games: list[dict[str, Any]] = []
    trace_counts: Counter[str] = Counter()
    control_counts: Counter[str] = Counter()
    action_counts: Counter[str] = Counter()
    context_counts: Counter[str] = Counter()
    active_calls = decision_calls = mismatches = 0
    started = time.time()

    for row in public:
        episode_id = int(row["id"])
        replay_path = replay_dir / f"episode-{episode_id}-replay.json"
        replay = json.loads(replay_path.read_text(encoding="utf-8"))
        steps = replay.get("steps") or []
        seat = int(row["seat"])
        names = (replay.get("info") or {}).get("TeamNames") or []
        if len(names) != 2 or names[seat] != args.team_name:
            raise SystemExit(f"team/seat mismatch ep={episode_id}")
        opponent_deck = _opponent_deck(replay, 1 - seat)
        archetype = _classify_deck(opponent_deck) if len(opponent_deck) == 60 else "unknown"
        if agent.deck() != exact_deck:
            raise SystemExit("exact-v22 deck changed between episodes")

        features: set[str] = set()
        controls: list[dict[str, Any]] = []
        actions: Counter[str] = Counter()
        contexts: Counter[str] = Counter()
        for step_index in range(len(steps) - 1):
            record = steps[step_index][seat]
            if record.get("status") != "ACTIVE":
                continue
            obs = record.get("observation") or {}
            expected = steps[step_index + 1][seat].get("action")
            if not isinstance(expected, list):
                expected = []
            active_calls += 1
            if not isinstance(obs.get("select"), dict):
                actual = agent(obs)
                if actual != expected:
                    mismatches += 1
                continue

            decision_calls += 1
            state = main_module._state(obs)
            raw_options = (obs.get("select") or {}).get("option") or []
            options = [main_module._semantic(obs, option) for option in raw_options]
            history = list(main_module._HISTORY)
            fallback_action = fallback.choose(state, options, history)
            manual_name, manual_action = _first_manual_guard(guards, obs)
            actual = agent(obs)
            if actual != expected:
                mismatches += 1
                if mismatches <= 5:
                    print(
                        f"[mismatch] ep={episode_id} step={step_index} "
                        f"expected={expected} actual={actual}",
                        flush=True,
                    )
            turn = int(state.get("turn", 0) or 0)
            context = int(state.get("context", -1))
            category = _action_category(options, actual)
            actions[category] += 1
            action_counts[category] += 1
            contexts[str(context)] += 1
            context_counts[str(context)] += 1
            _add_feature(features, "action:" + category, turn)
            _add_feature(features, f"context:{context}", turn)

            actual_sig = _semantic_signature(main_module, obs, actual)
            fallback_sig = _semantic_signature(main_module, obs, fallback_action)
            changed = actual_sig != fallback_sig
            if manual_name is not None:
                layer = "manual_guard"
                job = manual_name
                mode = "effective_hit"
            else:
                trace = dict(hierarchy._LAST_TRACE)
                layer = str(trace.get("layer", "fallback"))
                job = str(trace.get("job", "fallback"))
                mode = str(trace.get("mode", "fallback_only"))
                # Trust semantic comparison over an index-only trace flag.
                changed = actual_sig != fallback_sig

            trace_key = f"{layer}/{job}/{mode}"
            trace_counts[trace_key] += 1
            _add_feature(features, "trace:" + trace_key, turn)
            if changed:
                control_key = f"{layer}/{job}/{mode}"
                control_counts[control_key] += 1
                _add_feature(features, "control:" + control_key, turn)
                if len(controls) < 50:
                    controls.append({
                        "step_index": step_index,
                        "turn": turn,
                        "context": context,
                        "layer": layer,
                        "job": job,
                        "mode": mode,
                        "action": actual,
                        "fallback": fallback_action,
                        "action_category": category,
                    })

        games.append({
            "episode": episode_id,
            "ref": int(row["ref"]),
            "reward": int(row["reward"]),
            "seat": seat,
            "end": row.get("end"),
            "opponent": row.get("opp"),
            "opponent_archetype": archetype,
            "features": sorted(features),
            "actions": dict(actions),
            "contexts": dict(contexts),
            "control_changes": controls,
        })

    if mismatches:
        raise SystemExit(f"exact-v22 replay mismatches={mismatches}; refusing interpretation")

    feature_names = sorted({
        feature
        for game in games
        for feature in cast(list[str], game["features"])
    })
    by_ref = defaultdict(list)
    for game in games:
        by_ref[str(game["ref"])].append(game)
    associations = {
        feature: {
            ref: _association(rows, feature)
            for ref, rows in sorted(by_ref.items())
        }
        for feature in feature_names
    }
    findings = _candidate_findings(associations)
    report = {
        "created_unix": time.time(),
        "method": "exact-v22-live-decision-surface-split-ref-v1",
        "interpretation": (
            "episode-level exposure association only; not causal and not "
            "counterfactual reward"
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
        "public_episodes": len(public),
        "validation_excluded": len(validation),
        "active_calls": active_calls,
        "decision_calls": decision_calls,
        "exact_action_mismatches": mismatches,
        "trace_counts": dict(trace_counts.most_common()),
        "control_change_counts": dict(control_counts.most_common()),
        "action_counts": dict(action_counts.most_common()),
        "context_counts": dict(context_counts.most_common()),
        "association_rules": {
            "design_ref": 55499962,
            "replication_ref": 55516725,
            "candidate_scope": "control:*@turn<=4 only",
            "design_min_exposed_unexposed": [5, 5],
            "replication_min_exposed_unexposed": [3, 3],
            "direction": "same non-zero delta in both refs",
            "causal_claim": False,
        },
        "replicated_control_hypotheses": findings,
        "associations": associations,
        "games": games,
        "elapsed_s": round(time.time() - started, 3),
    }
    reservation.write(report)
    print(
        f"[done] games={len(games)} decisions={decision_calls} "
        f"controls={sum(control_counts.values())} findings={len(findings)} "
        f"elapsed={report['elapsed_s']}s -> {args.out}",
        flush=True,
    )
    for row in findings[:20]:
        print(
            f"  {row['direction']} {row['feature']} "
            f"design={row['design']['delta']:+.3f} "
            f"replication={row['replication']['delta']:+.3f}",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
