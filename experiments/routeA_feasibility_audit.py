#!/usr/bin/env python3
"""Read-only feasibility counts for an exact-v22 MAIN override learner."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys
import time
from collections import Counter, defaultdict
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
from experiments.v22_live_decision_surface import (  # noqa: E402
    MAIN_MODULE,
    _action_category,
    _semantic_signature,
)
from scripts.candidate_h2h import (  # noqa: E402
    BASELINE as V22,
    CandidateAgent,
    assert_locked_baseline,
    sha256,
    tree_sha256,
)
from scripts.safe_json_output import reserve_json_output  # noqa: E402


TURN_BUCKETS = ("turn<=2", "turn3-4", "turn5-8", "turn>=9")


def _turn_bucket(turn: int) -> str:
    if turn <= 2:
        return "turn<=2"
    if turn <= 4:
        return "turn3-4"
    if turn <= 8:
        return "turn5-8"
    return "turn>=9"


def _deck_hash(deck: list[int]) -> str:
    payload = ",".join(str(card) for card in sorted(int(card) for card in deck))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


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
    reservation = reserve_json_output(args.out, overwrite=args.overwrite_output)
    replay_dir = pathlib.Path(args.replay_dir).expanduser().resolve()
    public, validation = _load_rows(args.episodes)
    if len(public) != 82:
        raise SystemExit(f"frozen audit requires 82 PUBLIC episodes, got {len(public)}")

    agent = CandidateAgent(V22)
    main_module = agent._private_modules.get(MAIN_MODULE)
    if main_module is None:
        raise SystemExit("exact-v22 main module missing")
    exact_deck = agent.deck()

    context_counts = Counter()
    main_decisions = Counter()
    main_actions: dict[str, Counter[str]] = defaultdict(Counter)
    main_episode_sets: dict[str, set[int]] = defaultdict(set)
    opportunity_states = Counter()
    opportunity_episode_sets: dict[str, set[int]] = defaultdict(set)
    option_count_hist = Counter()
    opponent_archetypes = Counter()
    opponent_deck_hashes = Counter()
    full_opponent_decks = 0
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
        if len(opponent_deck) == 60:
            full_opponent_decks += 1
            opponent_deck_hashes[_deck_hash(opponent_deck)] += 1
            opponent_archetypes[_classify_deck(opponent_deck)] += 1

        if agent.deck() != exact_deck:
            raise SystemExit("exact-v22 deck changed between episodes")
        for step_index in range(len(steps) - 1):
            record = steps[step_index][seat]
            if record.get("status") != "ACTIVE":
                continue
            obs = record.get("observation") or {}
            expected = steps[step_index + 1][seat].get("action")
            if not isinstance(expected, list):
                expected = []
            active_calls += 1
            actual = agent(obs)
            if actual != expected:
                mismatches += 1
            select = obs.get("select")
            if not isinstance(select, dict):
                continue
            decision_calls += 1
            context = int(select.get("context", -1) if select.get("context") is not None else -1)
            context_counts[str(context)] += 1
            if context != 0:
                continue

            state = main_module._state(obs)
            turn = int(state.get("turn", 0) or 0)
            bucket = _turn_bucket(turn)
            raw_options = select.get("option") or []
            options = [main_module._semantic(obs, option) for option in raw_options]
            main_decisions[bucket] += 1
            main_episode_sets[bucket].add(episode_id)
            main_actions[bucket][_action_category(options, actual)] += 1
            option_count_hist[str(len(options))] += 1

            actual_signature = _semantic_signature(main_module, obs, actual)
            distinct = {
                _semantic_signature(main_module, obs, [index])
                for index in range(len(raw_options))
            }
            if any(signature != actual_signature for signature in distinct):
                opportunity_states[bucket] += 1
                opportunity_episode_sets[bucket].add(episode_id)

    if mismatches:
        raise SystemExit(f"exact-v22 replay mismatches={mismatches}")

    report: dict[str, Any] = {
        "created_unix": time.time(),
        "method": "routeA-exact-v22-main-feasibility-v1",
        "candidate": str(V22),
        "candidate_tree_sha256": tree_sha256(V22),
        "candidate_main_sha256": sha256(V22 / "main.py"),
        "candidate_deck_sha256": sha256(V22 / "deck.csv"),
        "public_episodes": len(public),
        "validation_excluded": len(validation),
        "active_calls": active_calls,
        "decision_calls": decision_calls,
        "exact_action_mismatches": mismatches,
        "context_counts": dict(context_counts.most_common()),
        "main": {
            "context": 0,
            "decisions": sum(main_decisions.values()),
            "episode_cluster_note": (
                "terminal rewards are correlated within episode; decision count is not "
                "an independent reward sample size"
            ),
            "turn_buckets": {
                bucket: {
                    "decisions": main_decisions[bucket],
                    "episodes_exposed": len(main_episode_sets[bucket]),
                    "episodes_with_semantic_alternative": len(
                        opportunity_episode_sets[bucket]
                    ),
                    "states_with_semantic_alternative": opportunity_states[bucket],
                    "action_counts": dict(main_actions[bucket].most_common()),
                }
                for bucket in TURN_BUCKETS
            },
            "option_count_histogram": dict(
                sorted(option_count_hist.items(), key=lambda row: int(row[0]))
            ),
        },
        "live_opponents": {
            "full_60_card_decks": full_opponent_decks,
            "unique_deck_multisets": len(opponent_deck_hashes),
            "archetypes": dict(opponent_archetypes.most_common()),
            "policy_source_available": False,
            "limitation": (
                "replays expose complete deck lists and recorded actions, but not an "
                "executable opponent policy for post-intervention trajectories"
            ),
        },
        "elapsed_s": round(time.time() - started, 3),
    }
    reservation.write(report)
    print(
        f"[done] episodes={len(public)} decisions={decision_calls} "
        f"main={report['main']['decisions']} full_decks={full_opponent_decks} "
        f"unique_decks={len(opponent_deck_hashes)} -> {args.out}",
        flush=True,
    )
    for bucket, row in report["main"]["turn_buckets"].items():
        print(
            f"  {bucket}: decisions={row['decisions']} "
            f"episodes={row['episodes_exposed']} "
            f"alternative_episodes={row['episodes_with_semantic_alternative']}",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
