#!/usr/bin/env python3
"""Engineering and directional gate for the slot-2 matchup-router lottery.

The released native engine does not expose a shuffle seed.  Every W/L arm is
therefore an independent trial; seat alternation balances position but is not
described as paired or common-random-number evaluation.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import statistics
import sys
import time
from collections import Counter
from typing import Any


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.candidate_h2h import (  # noqa: E402
    BASELINE as V22,
    CandidateAgent,
    assert_locked_baseline,
    run_match,
    sha256,
    tree_sha256,
)
from scripts.safe_json_output import reserve_json_output  # noqa: E402


MAIN_MODULE = "policies.v22.main"
ROUTER_MODULE = "policies.v22.matchup_router"
SPEC = ROOT / "reports" / "20260815_lottery_ticket_spec.md"

TARGET_LEGS = (
    ("alakazam", ROOT / "candidates" / "alakazam_codex_v22", 128, 0.71),
    ("router", ROOT / "candidates" / "lucario_advanced_router_v13", 256, 0.13),
    ("lucario", ROOT / "submission_baseline", 256, 0.16),
)
MIRROR_GAMES = 256


class DormantRouter:
    """Test-only exact mode; never shipped or selected by the candidate."""

    def reset(self) -> None:
        return None

    def observe(self, _obs: dict[str, Any]) -> str:
        return "UNKNOWN"


def _percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, int((len(ordered) - 1) * q))
    return ordered[index]


def _candidate_diff(candidate: pathlib.Path) -> dict[str, Any]:
    def files(root: pathlib.Path) -> dict[str, str]:
        return {
            path.relative_to(root).as_posix(): sha256(path)
            for path in sorted(root.rglob("*"))
            if path.is_file() and "__pycache__" not in path.parts
        }

    base = files(V22)
    trial = files(candidate)
    changed = sorted(
        path for path in set(base) & set(trial)
        if base[path] != trial[path]
    )
    added = sorted(set(trial) - set(base))
    removed = sorted(set(base) - set(trial))
    expected_changed = ["policies/v22/main.py"]
    expected_added = ["policies/v22/matchup_router.py"]
    return {
        "changed": changed,
        "added": added,
        "removed": removed,
        "only_expected_runtime_delta": (
            changed == expected_changed
            and added == expected_added
            and not removed
        ),
    }


def _static_visible_information_audit(candidate: pathlib.Path) -> dict[str, Any]:
    path = candidate / "policies" / "v22" / "matchup_router.py"
    source = path.read_text(encoding="utf-8")
    forbidden = (
        '.get("hand")',
        ".get('hand')",
        '.get("deck")',
        ".get('deck')",
        '.get("prize")',
        ".get('prize')",
        '.get("logs")',
        ".get('logs')",
        "search_begin_input",
    )
    hits = [token for token in forbidden if token in source]
    return {
        "router_source": str(path),
        "router_source_sha256": sha256(path),
        "visible_zones": ["opponent.active", "opponent.bench", "opponent.discard"],
        "public_nested_cards": ["preEvolution", "tools", "energyCards"],
        "forbidden_lookup_hits": hits,
        "pass": not hits,
    }


def _canary(
    candidate: pathlib.Path,
    audit_path: pathlib.Path,
    replay_dir: pathlib.Path,
    team_name: str,
) -> dict[str, Any]:
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    games = audit.get("games") or []
    if len(games) != 82:
        raise SystemExit(f"frozen canary requires 82 PUBLIC games, got {len(games)}")

    dormant = CandidateAgent(candidate)
    active = CandidateAgent(candidate)
    dormant_main = dormant._private_modules.get(MAIN_MODULE)
    active_main = active._private_modules.get(MAIN_MODULE)
    router_module = active._private_modules.get(ROUTER_MODULE)
    if dormant_main is None or active_main is None or router_module is None:
        raise SystemExit("candidate matchup-router modules missing")
    dormant_main._MATCHUP_ROUTER = DormantRouter()
    latency_probe = router_module.MatchupRouter()

    dormant_mismatches = 0
    active_mismatches = 0
    non_target_mismatches = 0
    active_calls = 0
    reset_failures = 0
    one_decision_lag_failures = 0
    dormant_latencies_ms: list[float] = []
    active_latencies_ms: list[float] = []
    router_latencies_ms: list[float] = []
    rows: list[dict[str, Any]] = []

    for game in games:
        episode = int(game["episode"])
        replay_path = replay_dir / f"episode-{episode}-replay.json"
        replay = json.loads(replay_path.read_text(encoding="utf-8"))
        steps = replay.get("steps") or []
        seat = int(game["seat"])
        names = (replay.get("info") or {}).get("TeamNames") or []
        if len(names) != 2 or names[seat] != team_name:
            raise SystemExit(f"team/seat mismatch ep={episode}")

        dormant.deck()
        active.deck()
        latency_probe.reset()
        reset_state = active_main._MATCHUP_ROUTER.snapshot()
        if (
            reset_state.get("mode") != "UNKNOWN"
            or reset_state.get("pending") is not None
            or int(reset_state.get("decisions", -1)) != 0
        ):
            reset_failures += 1

        gold = str(game.get("opponent_archetype") or "other")
        gold_parts = set(gold.split("+"))
        target_gold = bool(gold_parts & {"Alakazam", "Lucario"})
        switched = False
        first_switch: dict[str, Any] | None = None
        episode_mismatches = 0

        for step_index in range(len(steps) - 1):
            record = steps[step_index][seat]
            if record.get("status") != "ACTIVE":
                continue
            obs = record.get("observation") or {}
            expected = steps[step_index + 1][seat].get("action")
            if not isinstance(expected, list):
                expected = []

            started = time.perf_counter_ns()
            dormant_action = dormant(obs)
            dormant_latencies_ms.append((time.perf_counter_ns() - started) / 1e6)
            dormant_mismatches += int(dormant_action != expected)

            started = time.perf_counter_ns()
            active_action = active(obs)
            active_latencies_ms.append((time.perf_counter_ns() - started) / 1e6)
            mismatch = active_action != expected
            active_mismatches += int(mismatch)
            episode_mismatches += int(mismatch)
            if not target_gold:
                non_target_mismatches += int(mismatch)

            select = obs.get("select")
            if isinstance(select, dict) and (select.get("option") or []):
                started = time.perf_counter_ns()
                latency_probe.observe(obs)
                router_latencies_ms.append((time.perf_counter_ns() - started) / 1e6)

            state = active_main._MATCHUP_ROUTER.snapshot()
            if state.get("mode") in ("ALAKAZAM", "LUCARIO") and not switched:
                switched = True
                current = obs.get("current") or {}
                first_switch = {
                    "step_index": step_index,
                    "turn": int(current.get("turn", 0) or 0),
                    "mode": state.get("mode"),
                    "decision": state.get("switched_decision"),
                    "first_signature_decision": state.get("first_signature_decision"),
                }
                if (
                    state.get("switched_decision") is None
                    or state.get("first_signature_decision") is None
                    or int(state["switched_decision"])
                    != int(state["first_signature_decision"]) + 1
                ):
                    one_decision_lag_failures += 1
            active_calls += 1

        final_state = active_main._MATCHUP_ROUTER.snapshot()
        rows.append({
            "episode": episode,
            "ref": int(game["ref"]),
            "seat": seat,
            "gold": gold,
            "target_gold": target_gold,
            "switched": switched,
            "first_switch": first_switch,
            "final_router_state": final_state,
            "active_action_mismatches": episode_mismatches,
        })

    switched_rows = [row for row in rows if row["switched"]]
    false_switches = [row for row in switched_rows if not row["target_gold"]]
    target_rows = [row for row in rows if row["target_gold"]]
    target_switched = [row for row in target_rows if row["switched"]]
    router_p99 = _percentile(router_latencies_ms, 0.99)
    switch_rate = len(switched_rows) / len(rows)
    verdict = "PASS" if (
        dormant_mismatches == 0
        and non_target_mismatches == 0
        and reset_failures == 0
        and one_decision_lag_failures == 0
        and not false_switches
        and 0 < len(switched_rows) <= len(rows) / 2
        and router_p99 is not None
        and router_p99 < 1.0
    ) else "BEHAVIOR_KILL"

    return {
        "public_episodes": len(rows),
        "active_calls": active_calls,
        "dormant_exact_action_mismatches": dormant_mismatches,
        "active_action_mismatches": active_mismatches,
        "non_target_action_mismatches": non_target_mismatches,
        "reset_failures": reset_failures,
        "one_decision_lag_failures": one_decision_lag_failures,
        "switched_episodes": len(switched_rows),
        "switch_rate": round(switch_rate, 6),
        "target_episodes": len(target_rows),
        "target_switched_episodes": len(target_switched),
        "false_switches": false_switches,
        "switches_by_gold": dict(Counter(row["gold"] for row in switched_rows)),
        "switches_by_ref": dict(Counter(str(row["ref"]) for row in switched_rows)),
        "switches_by_seat": dict(Counter(str(row["seat"]) for row in switched_rows)),
        "latency_ms": {
            "router_observe_mean": round(statistics.mean(router_latencies_ms), 6),
            "router_observe_p99": round(float(router_p99), 6),
            "active_agent_p99": round(float(_percentile(active_latencies_ms, 0.99) or 0.0), 6),
            "dormant_agent_p99": round(float(_percentile(dormant_latencies_ms, 0.99) or 0.0), 6),
        },
        "internal_errors": 0,
        "verdict": verdict,
        "episodes": rows,
    }


def _wl(candidate: pathlib.Path, seed: int) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    print(f"[wl] mirror n={MIRROR_GAMES}", flush=True)
    mirror = run_match(
        CandidateAgent(candidate), CandidateAgent(V22), MIRROR_GAMES, seed
    )
    mirror.update({"leg": "v22_mirror", "role": "candidate", "weight": None})
    results.append(mirror)

    for index, (name, opponent_path, games, weight) in enumerate(TARGET_LEGS):
        print(f"[wl] {name} candidate/control n={games} each", flush=True)
        candidate_row = run_match(
            CandidateAgent(candidate),
            CandidateAgent(opponent_path),
            games,
            seed + (index + 1) * 100_000,
        )
        candidate_row.update({"leg": name, "role": "candidate", "weight": weight})
        results.append(candidate_row)

        control_row = run_match(
            CandidateAgent(V22),
            CandidateAgent(opponent_path),
            games,
            seed + (index + 1) * 100_000 + 50_000,
        )
        control_row.update({"leg": name, "role": "exact_control", "weight": weight})
        results.append(control_row)

    by_key = {(row["leg"], row["role"]): row for row in results}
    deltas = {
        name: round(
            float(by_key[(name, "candidate")]["win_rate"] or 0.0)
            - float(by_key[(name, "exact_control")]["win_rate"] or 0.0),
            6,
        )
        for name, _, _, _ in TARGET_LEGS
    }
    target_proxy_delta = sum(
        weight * deltas[name] for name, _, _, weight in TARGET_LEGS
    )
    candidate_games = sum(
        int(row["games"]) for row in results if row["role"] == "candidate"
    )
    candidate_faults = sum(
        int(row["candidate_faults"]) for row in results if row["role"] == "candidate"
    )
    engineering_pass = candidate_games >= 500 and candidate_faults == 0
    return {
        "trial_design": "blocked-independent; AB seat alternation; native shuffle unseeded",
        "candidate_games": candidate_games,
        "candidate_faults": candidate_faults,
        "internal_errors": 0,
        "engineering_verdict": "PASS" if engineering_pass else "FAULT_KILL",
        "target_deltas": deltas,
        "target_live_weight_proxy_delta": round(target_proxy_delta, 6),
        "directional_only_not_engineering_gate": True,
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--candidate",
        default=str(ROOT / "candidates" / "grim_v22_bronze_router_v1"),
    )
    parser.add_argument(
        "--audit",
        default=str(ROOT / "experiments" / "runs" / "live_v22_replay_audit_20260815_1045CST.json"),
    )
    parser.add_argument(
        "--replay-dir", default="/private/tmp/ptcg-live-replay-audit-20260815"
    )
    parser.add_argument("--team-name", default="可抽奖的冰棒")
    parser.add_argument("--seed", type=int, default=202608152030)
    parser.add_argument("--out", required=True)
    parser.add_argument("--overwrite-output", action="store_true")
    args = parser.parse_args()

    assert_locked_baseline()
    candidate = pathlib.Path(args.candidate).resolve()
    audit_path = pathlib.Path(args.audit).resolve()
    replay_dir = pathlib.Path(args.replay_dir).resolve()
    if not SPEC.is_file() or not candidate.is_dir() or not replay_dir.is_dir():
        raise SystemExit("spec, candidate, or replay directory missing")
    for _, opponent, _, _ in TARGET_LEGS:
        if not (opponent / "main.py").is_file():
            raise SystemExit(f"target opponent missing: {opponent}")

    reservation = reserve_json_output(args.out, overwrite=args.overwrite_output)
    started = time.time()
    diff = _candidate_diff(candidate)
    static_audit = _static_visible_information_audit(candidate)
    print("[canary] dormant reproduction + live behavior", flush=True)
    canary = _canary(candidate, audit_path, replay_dir, args.team_name)
    if canary["verdict"] != "PASS":
        wl = None
    else:
        wl = _wl(candidate, args.seed)

    engineering_pass = bool(
        diff["only_expected_runtime_delta"]
        and static_audit["pass"]
        and canary["verdict"] == "PASS"
        and wl is not None
        and wl["engineering_verdict"] == "PASS"
    )
    report = {
        "created_unix": time.time(),
        "method": "bronze-shot-matchup-router-engineering-plus-directional-v1",
        "specification": str(SPEC),
        "specification_sha256": sha256(SPEC),
        "time_kill_override": "user removed the 23:30 cutoff; gates remain unchanged",
        "candidate": str(candidate),
        "candidate_tree_sha256": tree_sha256(candidate),
        "candidate_main_sha256": sha256(candidate / "main.py"),
        "candidate_deck_sha256": sha256(candidate / "deck.csv"),
        "baseline_tree_sha256": tree_sha256(V22),
        "baseline_lock": "PASS",
        "candidate_diff": diff,
        "visible_information_audit": static_audit,
        "canary": canary,
        "wl": wl,
        "engineering_verdict": "PASS" if engineering_pass else "KILL",
        "promotion_claim": None,
        "submitted": False,
        "elapsed_s": round(time.time() - started, 3),
    }
    reservation.write(report)
    proxy = None if wl is None else wl["target_live_weight_proxy_delta"]
    print(
        f"Bronze-shot engineering={report['engineering_verdict']} "
        f"switch={canary['switched_episodes']}/82 false={len(canary['false_switches'])} "
        f"target_proxy_delta={proxy}",
        flush=True,
    )
    return 0 if engineering_pass else 2


if __name__ == "__main__":
    raise SystemExit(main())
