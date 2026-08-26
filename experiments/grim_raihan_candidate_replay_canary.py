#!/usr/bin/env python3
"""Compare a Grim residual and exact-v22 on unseen Raihan replay states.

Actions use Kaggle's off-by-one alignment: an ACTIVE observation at step s is
paired with the recorded action at step s+1.  This is an off-policy behavior
canary, not a W/L estimate; native H2H remains the promotion gate.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import random
import sys
import time
from collections import Counter
from typing import Any


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiments.alakazam_msato_policy_audit import action_signature, deck_hash, initial_deck  # noqa: E402
from scripts.candidate_h2h import CandidateAgent, sha256, tree_sha256  # noqa: E402
from scripts.safe_json_output import reserve_json_output  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replay-dir", action="append", required=True)
    parser.add_argument("--team-name", default="Raihan Ramadistra")
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--baseline", default=str(ROOT / "candidates/grim_v22_final"))
    parser.add_argument("--episode-min", type=int, default=0)
    parser.add_argument("--episode-max", type=int, default=0)
    parser.add_argument("--out", required=True)
    parser.add_argument("--overwrite-output", action="store_true")
    args = parser.parse_args()

    reservation = reserve_json_output(args.out, overwrite=args.overwrite_output)
    candidate_root = pathlib.Path(args.candidate).expanduser().resolve()
    baseline_root = pathlib.Path(args.baseline).expanduser().resolve()
    candidate = CandidateAgent(candidate_root)
    baseline = CandidateAgent(baseline_root)
    target_deck = baseline.deck()
    target_hash = deck_hash(target_deck)

    replay_paths: dict[int, pathlib.Path] = {}
    for raw_dir in args.replay_dir:
        for path in pathlib.Path(raw_dir).expanduser().resolve().glob("episode-*-replay.json"):
            try:
                episode = int(path.name.split("-")[1])
            except (IndexError, ValueError):
                continue
            if args.episode_min and episode < args.episode_min:
                continue
            if args.episode_max and episode > args.episode_max:
                continue
            replay_paths.setdefault(episode, path)

    totals: Counter[str] = Counter()
    by_context: dict[int, Counter[str]] = {}
    by_turn: dict[str, Counter[str]] = {}
    games: list[dict[str, Any]] = []
    override_samples: list[dict[str, Any]] = []
    started = time.time()
    for episode, path in sorted(replay_paths.items()):
        replay = json.loads(path.read_text(encoding="utf-8"))
        names = (replay.get("info") or {}).get("TeamNames") or []
        if args.team_name not in names or len(names) != 2:
            continue
        seat = names.index(args.team_name)
        expert_deck = initial_deck(replay, seat)
        if len(expert_deck) != 60 or deck_hash(expert_deck) != target_hash:
            totals["deck_mismatch_games"] += 1
            continue
        if candidate.deck() != target_deck or baseline.deck() != target_deck:
            raise SystemExit("candidate/baseline deck changed")
        seed = (replay.get("configuration") or {}).get("seed")
        game_reward = int((replay.get("rewards") or [0, 0])[seat])
        if seed is not None:
            random.seed(int(seed))
        game = Counter()
        steps = replay.get("steps") or []
        for index in range(len(steps) - 1):
            if seat >= len(steps[index]) or seat >= len(steps[index + 1]):
                continue
            record = steps[index][seat]
            if record.get("status") != "ACTIVE":
                continue
            obs = record.get("observation") or {}
            expected = steps[index + 1][seat].get("action")
            if not isinstance(obs, dict) or not isinstance(expected, list):
                continue
            try:
                candidate_action = list(candidate(obs))
                baseline_action = list(baseline(obs))
            except Exception:
                totals["exceptions"] += 1
                continue
            select = obs.get("select")
            context = int(select.get("context", -1)) if isinstance(select, dict) else -1
            turn = int(((obs.get("current") or {}).get("turn", 0)) or 0)
            turn_key = "01-02" if turn <= 2 else "03-04" if turn <= 4 else "05-07" if turn <= 7 else "08+"
            expert_sig = action_signature(obs, expected)
            candidate_sig = action_signature(obs, candidate_action)
            baseline_sig = action_signature(obs, baseline_action)
            candidate_ok = candidate_sig == expert_sig
            baseline_ok = baseline_sig == expert_sig
            override = candidate_sig != baseline_sig
            if override and len(override_samples) < 200:
                override_samples.append({
                    "episode": episode,
                    "step": index,
                    "turn": turn,
                    "context": context,
                    "expert_reward": game_reward,
                    "expert": expert_sig,
                    "candidate": candidate_sig,
                    "baseline": baseline_sig,
                    "candidate_right": candidate_ok,
                    "baseline_right": baseline_ok,
                })
            for counter in (totals, game, by_context.setdefault(context, Counter()), by_turn.setdefault(turn_key, Counter())):
                counter["calls"] += 1
                counter["candidate_expert"] += int(candidate_ok)
                counter["baseline_expert"] += int(baseline_ok)
                counter["overrides"] += int(override)
                counter["override_candidate_right"] += int(override and candidate_ok and not baseline_ok)
                counter["override_baseline_right"] += int(override and baseline_ok and not candidate_ok)
                counter["override_both_wrong"] += int(override and not candidate_ok and not baseline_ok)
        totals["games"] += 1
        game["episode"] = episode
        game["reward"] = game_reward
        games.append(dict(game))

    def render(counter: Counter[str]) -> dict[str, Any]:
        calls = int(counter["calls"])
        overrides = int(counter["overrides"])
        return {
            key: int(counter[key])
            for key in (
                "calls",
                "candidate_expert",
                "baseline_expert",
                "overrides",
                "override_candidate_right",
                "override_baseline_right",
                "override_both_wrong",
            )
        } | {
            "candidate_expert_rate": round(counter["candidate_expert"] / calls, 6) if calls else None,
            "baseline_expert_rate": round(counter["baseline_expert"] / calls, 6) if calls else None,
            "override_rate": round(overrides / calls, 6) if calls else None,
            "override_net_expert": int(counter["override_candidate_right"] - counter["override_baseline_right"]),
        }

    report = {
        "created_unix": time.time(),
        "method": "unseen-expert-replay-offpolicy-canary-v1",
        "action_alignment": "steps[s].ACTIVE observation -> steps[s+1].action",
        "scope_warning": "off-policy action fidelity after a divergence is not causal W/L evidence",
        "team": args.team_name,
        "target_deck_hash": target_hash,
        "candidate": str(candidate_root),
        "candidate_tree_sha256": tree_sha256(candidate_root),
        "baseline": str(baseline_root),
        "baseline_tree_sha256": tree_sha256(baseline_root),
        "replay_dirs": [str(pathlib.Path(value).expanduser().resolve()) for value in args.replay_dir],
        "replay_files_seen": len(replay_paths),
        "episode_range": {"minimum": args.episode_min or None, "maximum": args.episode_max or None},
        "deck_mismatch_games": int(totals["deck_mismatch_games"]),
        "exceptions": int(totals["exceptions"]),
        "totals": render(totals),
        "by_context": {str(key): render(value) for key, value in sorted(by_context.items())},
        "by_turn": {key: render(value) for key, value in sorted(by_turn.items())},
        "games": games,
        "override_samples": override_samples,
        "elapsed_s": round(time.time() - started, 3),
    }
    reservation.write(report)
    print(json.dumps({
        "games": int(totals["games"]),
        "deck_mismatch_games": report["deck_mismatch_games"],
        "exceptions": report["exceptions"],
        "totals": report["totals"],
        "main": report["by_context"].get("0"),
        "by_turn": report["by_turn"],
        "elapsed_s": report["elapsed_s"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
