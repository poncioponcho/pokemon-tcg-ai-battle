#!/usr/bin/env python3
"""Check whether live exact-deck Alakazam agents reproduce one local policy.

The frozen v22 replay audit records our seat, the opponent submission, and a
canonical opponent-deck hash.  This audit selects the live opponents whose
deck is byte-equivalent as a multiset to ``candidates/alakazam_codex_v22`` and
replays their ACTIVE observations through that local candidate.  Kaggle stores
the action for ``steps[s]`` in ``steps[s + 1]``; same-step comparison is wrong.

One observed game is not an estimate of submission strength.  It is only an
identity screen.  Zero mismatches across every decision is strong compatibility
evidence.  The policy's search layer samples hidden zones, so nonzero mismatch
is inconclusive unless the platform's Python-RNG initialization is also known.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import random
import sys
import time
from collections import Counter
from typing import Any


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.candidate_h2h import CandidateAgent, sha256, tree_sha256  # noqa: E402
from scripts.safe_json_output import reserve_json_output  # noqa: E402


DEFAULT_CANDIDATE = ROOT / "candidates" / "alakazam_codex_v22"


def deck_hash(deck: list[int]) -> str:
    counts = Counter(int(card) for card in deck)
    payload = "\n".join(f"{card}:{counts[card]}" for card in sorted(counts))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", required=True, help="live-v22 replay audit JSON")
    parser.add_argument("--replay-dir", required=True)
    parser.add_argument("--candidate", default=str(DEFAULT_CANDIDATE))
    parser.add_argument("--out", required=True)
    parser.add_argument("--overwrite-output", action="store_true")
    args = parser.parse_args()

    audit_path = pathlib.Path(args.audit).expanduser().resolve()
    replay_dir = pathlib.Path(args.replay_dir).expanduser().resolve()
    candidate_root = pathlib.Path(args.candidate).expanduser().resolve()
    reservation = reserve_json_output(args.out, overwrite=args.overwrite_output)

    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    policy = CandidateAgent(candidate_root)
    candidate_deck = policy.deck()
    target_hash = deck_hash(candidate_deck)
    target_games = [
        game for game in audit.get("games", [])
        if game.get("opponent_deck_hash") == target_hash
    ]
    if not target_games:
        raise SystemExit(f"no live opponent uses candidate deck hash {target_hash}")

    results: list[dict[str, Any]] = []
    total_calls = 0
    total_mismatches = 0
    mismatch_samples: list[dict[str, Any]] = []
    started = time.time()

    for game in target_games:
        episode_id = int(game["episode"])
        replay_path = replay_dir / f"episode-{episode_id}-replay.json"
        if not replay_path.is_file():
            raise SystemExit(f"missing replay: {replay_path}")
        replay = json.loads(replay_path.read_text(encoding="utf-8"))
        live_seat = 1 - int(game["seat"])
        steps = replay.get("steps") or []

        replay_seed = (replay.get("configuration") or {}).get("seed")
        if replay_seed is not None:
            # The policy's search layer samples hidden zones with Python's
            # global RNG.  Reuse the episode seed before the startup call; a
            # mismatch after this remains evidence against exact execution,
            # while a mismatch without seeding would be uninterpretable.
            random.seed(int(replay_seed))

        # Kaggle asks for the deck at the beginning of each episode.  For
        # stateful agents this is also the only reliable episode-reset signal.
        if policy.deck() != candidate_deck:
            raise SystemExit("candidate deck changed between episodes")

        calls = mismatches = 0
        for step_index in range(len(steps) - 1):
            if live_seat >= len(steps[step_index]) or live_seat >= len(steps[step_index + 1]):
                continue
            record = steps[step_index][live_seat]
            if record.get("status") != "ACTIVE":
                continue
            observation = record.get("observation") or {}
            expected = steps[step_index + 1][live_seat].get("action")
            if not isinstance(observation, dict) or not isinstance(expected, list):
                continue
            predicted = policy(observation)
            calls += 1
            total_calls += 1
            if list(predicted) != list(expected):
                mismatches += 1
                total_mismatches += 1
                if len(mismatch_samples) < 24:
                    select = observation.get("select")
                    mismatch_samples.append({
                        "episode": episode_id,
                        "submission": game.get("opponent_submission"),
                        "step": step_index,
                        "context": select.get("context") if isinstance(select, dict) else None,
                        "predicted": list(predicted),
                        "recorded": list(expected),
                    })
        results.append({
            "episode": episode_id,
            "submission": int(game["opponent_submission"]),
            "team": game.get("opponent"),
            "reward_vs_v22": -int(game["reward"]),
            "replay_seed": replay_seed,
            "active_calls": calls,
            "action_mismatches": mismatches,
            "exact_reproduction": mismatches == 0,
        })

    exact_submissions = sorted({
        row["submission"] for row in results if row["exact_reproduction"]
    })
    different_submissions = sorted({
        row["submission"] for row in results if not row["exact_reproduction"]
    })
    report = {
        "created_unix": time.time(),
        "method": "live-exact-deck-action-identity-v1",
        "action_alignment": "steps[s].ACTIVE observation -> steps[s+1].action",
        "scope_warning": (
            "one observed game per submission does not estimate strength; "
            "zero mismatch is compatibility evidence, but stochastic-search "
            "mismatch is not proof of different source code"
        ),
        "audit_source": str(audit_path),
        "audit_source_sha256": sha256(audit_path),
        "candidate": str(candidate_root),
        "candidate_tree_sha256": tree_sha256(candidate_root),
        "candidate_main_sha256": sha256(candidate_root / "main.py"),
        "candidate_deck_sha256": sha256(candidate_root / "deck.csv"),
        "candidate_deck_hash": target_hash,
        "live_exact_deck_games": len(results),
        "active_calls": total_calls,
        "action_mismatches": total_mismatches,
        "exact_policy_submissions": exact_submissions,
        "different_policy_submissions": different_submissions,
        "results": results,
        "mismatch_samples": mismatch_samples,
        "elapsed_s": round(time.time() - started, 3),
    }
    reservation.write(report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
