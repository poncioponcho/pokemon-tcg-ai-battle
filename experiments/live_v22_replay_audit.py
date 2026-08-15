#!/usr/bin/env python3
"""Audit exact-v22 decisions and tactical-guard exposure in live replays.

Episode-list rows contain only outcome/opponent metadata.  This tool joins
those rows to downloaded Kaggle replay JSON, identifies our seat, and replays
only observations whose *current* status is ACTIVE.  Kaggle stores the action
returned for ``steps[s]`` in ``steps[s + 1]``; comparing against the action in
the same step is an off-by-one error.

The locked exact-v22 policy is run sequentially through every episode.  Exact
action reproduction is a prerequisite for interpreting guard opportunities.
Target guards are reported both as independent raw predicate matches and as
the first non-None rule in ``manual_guards.GUARDS`` (the actually reachable
manual-guard decision).

This script is read-only with respect to Kaggle and candidates.  Replays must
already be downloaded.  Its JSON output uses the shared exclusive-lock and
atomic-write protocol.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import pathlib
import statistics
import sys
import time
from collections import Counter, defaultdict
from typing import Any


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiments.v22_guard_factorial import (  # noqa: E402
    MANUAL_GUARDS_MODULE,
    TARGETS,
    _guard_name,
    _state_snapshot,
)
from scripts.candidate_h2h import (  # noqa: E402
    BASELINE as V22,
    CandidateAgent,
    assert_locked_baseline,
    sha256,
    tree_sha256,
)
from scripts.safe_json_output import reserve_json_output  # noqa: E402


DEFAULT_TEAM = "可抽奖的冰棒"
ARCHETYPE_SIGNATURES = (
    ("Lucario", {678}),
    ("Grimmsnarl", {648}),
    ("Alakazam", {743}),
    ("Dragapult", {121}),
    ("Archaludon", {190}),
    ("Gardevoir", {747}),
    ("Charizard", {790, 928}),
    ("Gengar", {772}),
    ("Crustle", {345}),
    ("Cornerstone", {117}),
    ("Gholdengo", {700, 191}),
)


def parse_episode_source(raw: str) -> tuple[int, pathlib.Path]:
    """Parse REF=PATH for one submission episode-list snapshot."""
    if "=" not in raw:
        raise argparse.ArgumentTypeError("episode source must be REF=PATH")
    ref_raw, path_raw = raw.split("=", 1)
    try:
        ref = int(ref_raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("episode source ref must be an integer") from exc
    path = pathlib.Path(path_raw).expanduser()
    if not path.is_absolute():
        path = ROOT / path
    if not path.is_file():
        raise argparse.ArgumentTypeError(f"episode source missing: {path}")
    return ref, path.resolve()


def _rate(games: list[dict[str, Any]]) -> dict[str, Any]:
    wins = sum(game["reward"] == 1 for game in games)
    losses = sum(game["reward"] == -1 for game in games)
    decisive = wins + losses
    return {
        "games": len(games),
        "wins": wins,
        "losses": losses,
        "win_rate": round(wins / decisive, 6) if decisive else None,
    }


def _group_rates(
    games: list[dict[str, Any]], key: str
) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for game in games:
        grouped[str(game[key])].append(game)
    return {
        name: _rate(rows)
        for name, rows in sorted(grouped.items(), key=lambda item: item[0])
    }


def _wilson_interval(wins: int, total: int, z: float = 1.96) -> list[float] | None:
    if total <= 0:
        return None
    p = wins / total
    denom = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denom
    margin = z * math.sqrt(
        (p * (1 - p) + z * z / (4 * total)) / total
    ) / denom
    return [round(max(0.0, center - margin), 6), round(min(1.0, center + margin), 6)]


def _zero_success_upper(total: int, alpha: float = 0.05) -> float | None:
    if total <= 0:
        return None
    return round(1 - alpha ** (1 / total), 8)


def _deck_hash(deck: list[int]) -> str:
    counts = Counter(int(card) for card in deck)
    payload = "\n".join(f"{card}:{counts[card]}" for card in sorted(counts))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _classify_deck(deck: list[int]) -> str:
    ids = set(deck)
    matches = [name for name, signatures in ARCHETYPE_SIGNATURES if ids & signatures]
    if not matches:
        return "other"
    return "+".join(matches)


def _first_manual_guard(
    guards: tuple[Any, ...], obs: dict[str, Any]
) -> tuple[str | None, list[int] | None]:
    """Mirror manual_guards.apply, including its per-rule exception fallback."""
    for guard in guards:
        try:
            action, _ = guard(obs)
        except Exception:
            continue
        if action is not None:
            return _guard_name(guard), list(action)
    return None, None


def _load_rows(
    sources: list[tuple[int, pathlib.Path]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    public: list[dict[str, Any]] = []
    validation: list[dict[str, Any]] = []
    seen: set[int] = set()
    for ref, path in sources:
        rows = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(rows, list):
            raise SystemExit(f"episode source is not a JSON list: {path}")
        for raw in rows:
            row = dict(raw)
            episode_id = int(row["id"])
            if episode_id in seen:
                raise SystemExit(f"duplicate episode id across sources: {episode_id}")
            seen.add(episode_id)
            row["ref"] = ref
            row["source"] = str(path)
            if row.get("opp_sub") is None:
                validation.append(row)
            else:
                public.append(row)
    public.sort(key=lambda row: row.get("end") or "")
    validation.sort(key=lambda row: row.get("end") or "")
    return public, validation


def _opponent_deck(replay: dict[str, Any], opponent_seat: int) -> list[int]:
    steps = replay.get("steps") or []
    if len(steps) < 2 or len(steps[1]) != 2:
        return []
    action = steps[1][opponent_seat].get("action")
    if not isinstance(action, list) or len(action) != 60:
        return []
    if not all(isinstance(card, int) for card in action):
        return []
    return [int(card) for card in action]


def _final_state(replay: dict[str, Any], seat: int) -> dict[str, Any]:
    for step in reversed(replay.get("steps") or []):
        if seat >= len(step):
            continue
        obs = step[seat].get("observation") or {}
        current = obs.get("current") or {}
        players = current.get("players") or []
        if len(players) != 2:
            continue
        return {
            "turn": int(current.get("turn", 0) or 0),
            "our_prizes_remaining": len(players[seat].get("prize") or []),
            "opponent_prizes_remaining": len(players[1 - seat].get("prize") or []),
        }
    return {
        "turn": None,
        "our_prizes_remaining": None,
        "opponent_prizes_remaining": None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--episodes",
        action="append",
        type=parse_episode_source,
        required=True,
        metavar="REF=PATH",
        help="repeat for each submission episode-list snapshot",
    )
    parser.add_argument("--replay-dir", required=True)
    parser.add_argument("--team-name", default=DEFAULT_TEAM)
    parser.add_argument("--out", required=True)
    parser.add_argument("--overwrite-output", action="store_true")
    args = parser.parse_args()

    replay_dir = pathlib.Path(args.replay_dir).expanduser().resolve()
    if not replay_dir.is_dir():
        raise SystemExit(f"replay directory missing: {replay_dir}")
    reservation = reserve_json_output(args.out, overwrite=args.overwrite_output)

    assert_locked_baseline()
    policy = CandidateAgent(V22)
    manual = policy._private_modules.get(MANUAL_GUARDS_MODULE)
    if manual is None:
        raise SystemExit("exact-v22 manual guard module missing")
    guards = tuple(manual.GUARDS)
    target_functions = {
        _guard_name(guard): guard
        for guard in guards
        if _guard_name(guard) in TARGETS
    }
    if set(target_functions) != set(TARGETS):
        raise SystemExit(f"target guard mismatch: {sorted(target_functions)}")

    public_rows, validation_rows = _load_rows(args.episodes)
    missing: list[int] = []
    games: list[dict[str, Any]] = []
    mismatch_samples: list[dict[str, Any]] = []
    target_raw: dict[str, list[dict[str, Any]]] = {target: [] for target in TARGETS}
    target_reached: dict[str, list[dict[str, Any]]] = {
        target: [] for target in TARGETS
    }
    first_manual_counts: Counter[str] = Counter()
    total_active_calls = 0
    total_decision_calls = 0
    total_mismatches = 0
    started = time.time()

    for row in public_rows:
        episode_id = int(row["id"])
        replay_path = replay_dir / f"episode-{episode_id}-replay.json"
        if not replay_path.is_file():
            missing.append(episode_id)
            continue
        replay = json.loads(replay_path.read_text(encoding="utf-8"))
        steps = replay.get("steps") or []
        if len(steps) < 2:
            raise SystemExit(f"replay has fewer than two steps: {replay_path}")

        seat = int(row["seat"])
        names = (replay.get("info") or {}).get("TeamNames") or []
        if seat not in (0, 1) or len(names) != 2 or names[seat] != args.team_name:
            raise SystemExit(
                f"team/seat mismatch ep={episode_id}: seat={seat} names={names}"
            )
        rewards = replay.get("rewards") or []
        if len(rewards) != 2 or int(rewards[seat]) != int(row["reward"]):
            raise SystemExit(
                f"reward mismatch ep={episode_id}: rows={row['reward']} replay={rewards}"
            )
        opponent_seat = 1 - seat
        deck = _opponent_deck(replay, opponent_seat)
        if len(deck) != 60:
            raise SystemExit(f"opponent deck missing from replay ep={episode_id}")
        archetype = _classify_deck(deck)
        game_raw_counts = Counter()
        game_reached_counts = Counter()
        game_calls = 0
        game_mismatches = 0

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

            total_active_calls += 1
            game_calls += 1
            select = obs.get("select")
            first_name = None
            first_action = None
            if isinstance(select, dict):
                total_decision_calls += 1
                for target, guard in target_functions.items():
                    try:
                        action, _ = guard(obs)
                    except Exception:
                        action = None
                    if action is not None:
                        event = {
                            "ref": int(row["ref"]),
                            "episode": episode_id,
                            "step": step_index,
                            "reward": int(row["reward"]),
                            "seat": seat,
                            "opponent": row.get("opp"),
                            "opponent_submission": row.get("opp_sub"),
                            "opponent_archetype": archetype,
                            "guard_action": list(action),
                            "recorded_action": list(expected),
                            "state": _state_snapshot(obs),
                        }
                        target_raw[target].append(event)
                        game_raw_counts[target] += 1
                first_name, first_action = _first_manual_guard(guards, obs)
                if first_name is not None:
                    first_manual_counts[first_name] += 1
                if first_name in target_reached:
                    event = {
                        "ref": int(row["ref"]),
                        "episode": episode_id,
                        "step": step_index,
                        "reward": int(row["reward"]),
                        "seat": seat,
                        "opponent": row.get("opp"),
                        "opponent_submission": row.get("opp_sub"),
                        "opponent_archetype": archetype,
                        "guard_action": list(first_action or []),
                        "recorded_action": list(expected),
                        "recorded_matches_guard": list(expected) == list(first_action or []),
                        "state": _state_snapshot(obs),
                    }
                    target_reached[first_name].append(event)
                    game_reached_counts[first_name] += 1

            predicted = policy(obs)
            if list(predicted) != list(expected):
                total_mismatches += 1
                game_mismatches += 1
                if len(mismatch_samples) < 20:
                    mismatch_samples.append({
                        "ref": int(row["ref"]),
                        "episode": episode_id,
                        "step": step_index,
                        "status": record.get("status"),
                        "context": (
                            select.get("context") if isinstance(select, dict) else None
                        ),
                        "predicted": list(predicted),
                        "recorded_next_step": list(expected),
                        "first_manual_guard": first_name,
                    })

        final_state = _final_state(replay, seat)
        games.append({
            "ref": int(row["ref"]),
            "episode": episode_id,
            "end": row.get("end"),
            "reward": int(row["reward"]),
            "seat": seat,
            "duration_s": row.get("dur_s"),
            "opponent": row.get("opp"),
            "opponent_submission": row.get("opp_sub"),
            "opponent_archetype": archetype,
            "opponent_deck_hash": _deck_hash(deck),
            "replay_seed": (replay.get("configuration") or {}).get("seed"),
            "statuses": replay.get("statuses"),
            "active_calls": game_calls,
            "action_mismatches": game_mismatches,
            "target_raw_events": dict(game_raw_counts),
            "target_reached_events": dict(game_reached_counts),
            **final_state,
        })

    if missing:
        raise SystemExit(
            f"missing {len(missing)} PUBLIC replay files, first={missing[:10]}"
        )
    if len(games) != len(public_rows):
        raise SystemExit(f"processed {len(games)} of {len(public_rows)} PUBLIC episodes")

    target_summary: dict[str, Any] = {}
    for target in TARGETS:
        raw = target_raw[target]
        reached = target_reached[target]
        raw_episodes = {event["episode"] for event in raw}
        reached_episodes = {event["episode"] for event in reached}
        target_summary[target] = {
            "raw_predicate_events": len(raw),
            "raw_predicate_episodes": len(raw_episodes),
            "raw_episode_rate": round(len(raw_episodes) / len(games), 8) if games else None,
            "first_reached_events": len(reached),
            "first_reached_episodes": len(reached_episodes),
            "first_reached_episode_rate": (
                round(len(reached_episodes) / len(games), 8) if games else None
            ),
            "first_reached_episode_wilson95": _wilson_interval(
                len(reached_episodes), len(games)
            ),
            "zero_event_one_sided_95_upper": (
                _zero_success_upper(len(games)) if not reached_episodes else None
            ),
            "recorded_action_matches": sum(
                bool(event["recorded_matches_guard"]) for event in reached
            ),
            "events": reached,
        }

    durations = [
        float(game["duration_s"])
        for game in games
        if game.get("duration_s") is not None
    ]
    unique_seeds = {
        int(game["replay_seed"])
        for game in games
        if game.get("replay_seed") is not None
    }
    summary = {
        "public": _rate(games),
        "validation_excluded": len(validation_rows),
        "by_ref": _group_rates(games, "ref"),
        "by_seat": _group_rates(games, "seat"),
        "by_opponent_archetype": _group_rates(games, "opponent_archetype"),
        "duration_s": {
            "mean": round(statistics.mean(durations), 3) if durations else None,
            "median": round(statistics.median(durations), 3) if durations else None,
        },
        "all_statuses_done": all(
            game.get("statuses") == ["DONE", "DONE"] for game in games
        ),
        "active_calls": total_active_calls,
        "decision_calls": total_decision_calls,
        "exact_action_mismatches": total_mismatches,
        "exact_action_reproduction_rate": (
            round((total_active_calls - total_mismatches) / total_active_calls, 8)
            if total_active_calls
            else None
        ),
        "mismatch_samples": mismatch_samples,
        "unique_replay_seeds": len(unique_seeds),
        "first_manual_guard_counts": dict(first_manual_counts.most_common()),
        "targets": target_summary,
    }
    report = {
        "created_unix": time.time(),
        "method": "live-exact-v22-active-observation-replay-audit-v1",
        "action_alignment": "steps[s].ACTIVE observation -> steps[s+1].action",
        "episode_scope": "PUBLIC only; validation (opp_sub=null) excluded",
        "team_name": args.team_name,
        "episode_sources": [
            {"ref": ref, "path": str(path), "sha256": sha256(path)}
            for ref, path in args.episodes
        ],
        "replay_dir": str(replay_dir),
        "candidate": str(V22),
        "candidate_tree_sha256": tree_sha256(V22),
        "targets": list(TARGETS),
        "summary": summary,
        "validation_rows": validation_rows,
        "games": games,
        "elapsed_s": round(time.time() - started, 3),
        "output_protocol": "exclusive-lock+atomic-replace-v1",
    }
    reservation.write(report)
    print(
        f"[live-audit] public={len(games)} calls={total_active_calls} "
        f"mismatches={total_mismatches} validation_excluded={len(validation_rows)}",
        flush=True,
    )
    for target in TARGETS:
        row = target_summary[target]
        print(
            f"  {target}: raw={row['raw_predicate_events']} "
            f"reached={row['first_reached_events']} "
            f"episodes={row['first_reached_episodes']}",
            flush=True,
        )
    print(f"[live-audit] -> {pathlib.Path(args.out).resolve()}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
