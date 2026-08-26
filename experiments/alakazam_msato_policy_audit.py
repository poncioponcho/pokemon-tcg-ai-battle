#!/usr/bin/env python3
"""Audit one public Alakazam policy from Kaggle replays.

The original use case was M Sato submission 55198468, whose submission later
changed decks.  The tool admits only episodes whose selected team seat has one
stable Alakazam deck.  It
summarizes matchup/outcome mechanics and replays the same observations through
local public Alakazam policies.  Kaggle's action alignment is
``steps[s].observation -> steps[s + 1].action``.

Action agreement is descriptive, not causal.  A close public policy is useful
as an implementation starting point; disagreement can also be caused by a
policy's private RNG.  Every candidate is replayed independently with the
episode seed and receives the usual ``select=None`` reset before each game.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import pathlib
import random
import statistics
import sys
import time
from collections import Counter, defaultdict
from typing import Any


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.candidate_h2h import CandidateAgent, sha256, tree_sha256  # noqa: E402
from scripts.safe_json_output import reserve_json_output  # noqa: E402


OPTION_NAMES = {
    0: "NUMBER",
    1: "YES",
    2: "NO",
    3: "CARD",
    4: "TOOL_CARD",
    5: "ENERGY_CARD",
    6: "ENERGY",
    7: "PLAY",
    8: "ATTACH",
    9: "EVOLVE",
    10: "ABILITY",
    11: "DISCARD",
    12: "RETREAT",
    13: "ATTACK",
    14: "END",
    15: "SKILL",
    16: "SPECIAL_CONDITION",
}

CONTEXT_NAMES = {
    0: "MAIN",
    1: "SETUP_ACTIVE",
    2: "SETUP_BENCH",
    3: "SWITCH",
    4: "TO_ACTIVE",
    5: "TO_BENCH",
    6: "TO_FIELD",
    7: "TO_HAND",
    8: "DISCARD",
    9: "TO_DECK",
    10: "TO_DECK_BOTTOM",
    11: "TO_PRIZE",
    12: "NOT_MOVE",
    13: "DAMAGE_COUNTER",
    14: "DAMAGE_COUNTER_ANY",
    15: "DAMAGE",
    16: "REMOVE_DAMAGE_COUNTER",
    17: "HEAL",
    18: "EVOLVES_FROM",
    19: "EVOLVES_TO",
    20: "DEVOLVE",
    21: "ATTACH_FROM",
    22: "ATTACH_TO",
    23: "DETACH_FROM",
    24: "LOOK",
    25: "EFFECT_TARGET",
    26: "DISCARD_ENERGY_CARD",
    27: "DISCARD_TOOL_CARD",
    28: "SWITCH_ENERGY_CARD",
    29: "DISCARD_CARD_OR_ATTACHED_CARD",
    30: "DISCARD_ENERGY",
    31: "TO_HAND_ENERGY",
    32: "TO_DECK_ENERGY",
    33: "SWITCH_ENERGY",
    34: "SKILL_ORDER",
    35: "ATTACK",
    36: "DISABLE_ATTACK",
    37: "EVOLVE",
    38: "DRAW_COUNT",
    39: "DAMAGE_COUNTER_COUNT",
    40: "REMOVE_DAMAGE_COUNTER_COUNT",
    41: "IS_FIRST",
    42: "MULLIGAN",
    43: "ACTIVATE",
    44: "FIRST_EFFECT",
    45: "MORE_DEVOLVE",
    46: "COIN_HEAD",
    47: "AFFECT_SPECIAL_CONDITION",
    48: "RECOVER_SPECIAL_CONDITION",
}

ARCHETYPE_SIGNATURES = (
    ("Grimmsnarl", {648}),
    ("Alakazam", {743}),
    ("Lucario", {678}),
    ("Crustle", {345}),
    ("Dragapult", {121}),
    ("Archaludon", {190}),
    ("Gardevoir", {747}),
    ("Charizard", {790, 928}),
    ("Gengar", {772}),
    ("Cornerstone", {117}),
    ("Gholdengo", {700, 191}),
    ("FroslassLopunny", {849, 861}),
)

ALAKAZAM_SIGNATURE = {741, 742, 743}


def parse_candidate(raw: str) -> tuple[str, pathlib.Path]:
    if "=" not in raw:
        raise argparse.ArgumentTypeError("candidate must be NAME=PATH")
    name, path = raw.split("=", 1)
    if not name.strip() or not path.strip():
        raise argparse.ArgumentTypeError("candidate must be NAME=PATH")
    return name.strip(), pathlib.Path(path).expanduser().resolve()


def deck_hash(deck: list[int]) -> str:
    counts = Counter(int(card) for card in deck)
    payload = "\n".join(f"{card}:{counts[card]}" for card in sorted(counts))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def classify_deck(deck: list[int]) -> str:
    ids = set(deck)
    matches = [name for name, signatures in ARCHETYPE_SIGNATURES if ids & signatures]
    return "+".join(matches) if matches else "other"


def initial_deck(replay: dict[str, Any], seat: int) -> list[int]:
    steps = replay.get("steps") or []
    if len(steps) < 2 or seat >= len(steps[1]):
        return []
    action = steps[1][seat].get("action")
    if not isinstance(action, list) or len(action) != 60:
        return []
    if not all(isinstance(card, int) for card in action):
        return []
    return [int(card) for card in action]


def _zone(current: dict[str, Any], player: int, area: int) -> list[Any]:
    players = current.get("players") or []
    if player not in (0, 1) or player >= len(players):
        return []
    state = players[player]
    key = {1: "deck", 2: "hand", 3: "discard", 4: "active", 5: "bench", 6: "prize"}.get(area)
    if key is None:
        return []
    value = state.get(key)
    return value if isinstance(value, list) else []


def resolve_card_id(obs: dict[str, Any], option: dict[str, Any]) -> int | None:
    raw = option.get("cardId")
    if isinstance(raw, int):
        return raw
    current = obs.get("current") or {}
    your = int(current.get("yourIndex", 0) or 0)
    try:
        option_type = int(option.get("type", -1))
    except (TypeError, ValueError):
        option_type = -1
    try:
        index = int(option.get("index", -1))
    except (TypeError, ValueError):
        return None
    if option_type == 7:  # PLAY: index within hand
        area, player = 2, your
    else:
        try:
            area = int(option.get("area", 2 if option_type in (8, 9) else -1))
            player = int(option.get("playerIndex", your))
        except (TypeError, ValueError):
            return None
    zone = _zone(current, player, area)
    if 0 <= index < len(zone) and isinstance(zone[index], dict):
        cid = zone[index].get("id")
        return int(cid) if isinstance(cid, int) else None
    return None


def option_signature(obs: dict[str, Any], option: dict[str, Any]) -> str:
    try:
        option_type = int(option.get("type", -1))
    except (TypeError, ValueError):
        option_type = -1
    name = OPTION_NAMES.get(option_type, f"TYPE_{option_type}")
    fields: list[str] = []
    card_id = resolve_card_id(obs, option)
    if card_id is not None:
        fields.append(f"card={card_id}")
    for key in ("attackId", "number", "specialConditionType"):
        value = option.get(key)
        if isinstance(value, (int, float)):
            fields.append(f"{key}={int(value)}")
    if not fields and option_type not in (1, 2, 12, 14):
        for key in ("area", "index", "playerIndex", "inPlayArea", "inPlayIndex"):
            value = option.get(key)
            if isinstance(value, int):
                fields.append(f"{key}={value}")
    return name + ("[" + ",".join(fields) + "]" if fields else "")


def action_signature(obs: dict[str, Any], action: list[int]) -> str:
    select = obs.get("select")
    if not isinstance(select, dict):
        return "DECK"
    options = select.get("option") or []
    labels = []
    for raw_index in action:
        if not isinstance(raw_index, int) or raw_index < 0 or raw_index >= len(options):
            labels.append(f"INVALID_{raw_index}")
            continue
        option = options[raw_index]
        labels.append(option_signature(obs, option) if isinstance(option, dict) else "INVALID_OPTION")
    return "+".join(sorted(labels))


def turn_bucket(turn: int) -> str:
    if turn <= 2:
        return "01-02"
    if turn <= 4:
        return "03-04"
    if turn <= 7:
        return "05-07"
    return "08+"


def final_state(replay: dict[str, Any], seat: int) -> dict[str, Any]:
    for step in reversed(replay.get("steps") or []):
        if seat >= len(step):
            continue
        current = (step[seat].get("observation") or {}).get("current") or {}
        players = current.get("players") or []
        if len(players) != 2:
            continue
        me, opponent = players[seat], players[1 - seat]
        return {
            "turn": int(current.get("turn", 0) or 0),
            "our_deck_count": int(me.get("deckCount", len(me.get("deck") or [])) or 0),
            "opponent_deck_count": int(opponent.get("deckCount", len(opponent.get("deck") or [])) or 0),
            "our_prizes_remaining": len(me.get("prize") or []),
            "opponent_prizes_remaining": len(opponent.get("prize") or []),
        }
    return {
        "turn": None,
        "our_deck_count": None,
        "opponent_deck_count": None,
        "our_prizes_remaining": None,
        "opponent_prizes_remaining": None,
    }


def result_event(replay: dict[str, Any]) -> dict[str, int | None]:
    """Read the authoritative named Result log from the visualization stream."""
    for step in reversed(replay.get("steps") or []):
        for record in step:
            visualizations = record.get("visualize") or []
            if not isinstance(visualizations, list):
                continue
            for frame in reversed(visualizations):
                for log in reversed((frame or {}).get("logs") or []):
                    if isinstance(log, dict) and log.get("type") == "Result":
                        result = log.get("result")
                        reason = log.get("reason")
                        return {
                            "winner_seat": int(result) if isinstance(result, int) else None,
                            "reason": int(reason) if isinstance(reason, int) else None,
                        }
    return {"winner_seat": None, "reason": None}


def rate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    wins = sum(row["reward"] == 1 for row in rows)
    losses = sum(row["reward"] == -1 for row in rows)
    return {
        "games": len(rows),
        "wins": wins,
        "losses": losses,
        "win_rate": round(wins / (wins + losses), 6) if wins + losses else None,
    }


def counter_json(counter: Counter[Any], limit: int | None = None) -> dict[str, int]:
    rows = counter.most_common(limit)
    return {str(key): int(value) for key, value in rows}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episodes", required=True)
    parser.add_argument("--replay-dir", required=True)
    parser.add_argument("--leaderboard", default="")
    parser.add_argument("--team-name", default="M Sato")
    parser.add_argument(
        "--scope-label",
        default="M Sato submission 55198468 Alakazam deck only",
        help="human-readable provenance/scope stored in the report",
    )
    parser.add_argument("--candidate", action="append", type=parse_candidate, default=[])
    parser.add_argument(
        "--max-replay-files",
        type=int,
        default=0,
        help="deterministic filename-ordered audit subset; 0 means every replay",
    )
    parser.add_argument("--out", required=True)
    parser.add_argument("--overwrite-output", action="store_true")
    args = parser.parse_args()

    episode_path = pathlib.Path(args.episodes).expanduser().resolve()
    replay_dir = pathlib.Path(args.replay_dir).expanduser().resolve()
    rows = json.loads(episode_path.read_text(encoding="utf-8"))
    metadata = {int(row["id"]): dict(row) for row in rows}
    scores: dict[str, float] = {}
    if args.leaderboard:
        with pathlib.Path(args.leaderboard).expanduser().resolve().open(
            encoding="utf-8-sig", newline=""
        ) as stream:
            for row in csv.DictReader(stream):
                try:
                    scores[" ".join(row["TeamName"].split()).casefold()] = float(row["Score"])
                except (KeyError, TypeError, ValueError):
                    continue

    candidates: dict[str, CandidateAgent] = {}
    candidate_meta: dict[str, dict[str, Any]] = {}
    for name, root in args.candidate:
        if name in candidates:
            raise SystemExit(f"duplicate candidate name: {name}")
        policy = CandidateAgent(root)
        candidates[name] = policy
        candidate_meta[name] = {
            "root": str(root),
            "tree_sha256": tree_sha256(root),
            "main_sha256": sha256(root / "main.py"),
            "deck_sha256": sha256(root / "deck.csv"),
            "deck_hash": deck_hash(policy.deck()),
        }

    files = sorted(replay_dir.glob("episode-*-replay.json"))
    if args.max_replay_files > 0:
        files = files[: args.max_replay_files]
    games: list[dict[str, Any]] = []
    excluded_wrong_submission = 0
    excluded_wrong_deck = 0
    target_deck_hash: str | None = None
    expert_contexts: Counter[str] = Counter()
    expert_actions_by_context: dict[str, Counter[str]] = defaultdict(Counter)
    expert_main_actions: Counter[str] = Counter()
    expert_setup_active: Counter[str] = Counter()
    candidate_counts: dict[str, Counter[str]] = {
        name: Counter() for name in candidates
    }
    candidate_context: dict[str, dict[str, Counter[str]]] = {
        name: defaultdict(Counter) for name in candidates
    }
    candidate_archetype: dict[str, dict[str, Counter[str]]] = {
        name: defaultdict(Counter) for name in candidates
    }
    candidate_turn: dict[str, dict[str, Counter[str]]] = {
        name: defaultdict(Counter) for name in candidates
    }
    disagreement: dict[str, Counter[str]] = {name: Counter() for name in candidates}
    mismatch_samples: dict[str, list[dict[str, Any]]] = {name: [] for name in candidates}
    started = time.time()

    for replay_path in files:
        replay = json.loads(replay_path.read_text(encoding="utf-8"))
        episode_id = int((replay.get("info") or {}).get("EpisodeId", -1))
        row = metadata.get(episode_id)
        if row is None or row.get("opp_sub") is None:
            excluded_wrong_submission += 1
            continue
        names = (replay.get("info") or {}).get("TeamNames") or []
        if args.team_name not in names or len(names) != 2:
            excluded_wrong_submission += 1
            continue
        seat = names.index(args.team_name)
        our_deck = initial_deck(replay, seat)
        opponent_deck = initial_deck(replay, 1 - seat)
        if len(our_deck) != 60 or not ALAKAZAM_SIGNATURE.issubset(set(our_deck)):
            excluded_wrong_deck += 1
            continue
        this_hash = deck_hash(our_deck)
        if target_deck_hash is None:
            target_deck_hash = this_hash
        if this_hash != target_deck_hash:
            raise SystemExit(f"multiple target Alakazam deck hashes; episode {episode_id}")
        for name, meta in candidate_meta.items():
            if meta["deck_hash"] != target_deck_hash:
                raise SystemExit(
                    f"candidate {name} deck differs from M Sato Alakazam deck: "
                    f"{meta['deck_hash']} != {target_deck_hash}"
                )

        reward = int((replay.get("rewards") or [0, 0])[seat])
        if reward not in (-1, 1):
            continue
        archetype = classify_deck(opponent_deck)
        decisions: list[tuple[int, dict[str, Any], list[int], str, int, str]] = []
        steps = replay.get("steps") or []
        for step_index in range(len(steps) - 1):
            if seat >= len(steps[step_index]) or seat >= len(steps[step_index + 1]):
                continue
            record = steps[step_index][seat]
            if record.get("status") != "ACTIVE":
                continue
            obs = record.get("observation") or {}
            select = obs.get("select")
            expected = steps[step_index + 1][seat].get("action")
            if not isinstance(select, dict) or not isinstance(expected, list):
                continue
            try:
                context_number = int(select.get("context", -1))
            except (TypeError, ValueError):
                context_number = -1
            context = CONTEXT_NAMES.get(context_number, f"CONTEXT_{context_number}")
            turn = int(((obs.get("current") or {}).get("turn", 0)) or 0)
            signature = action_signature(obs, expected)
            decisions.append((step_index, obs, list(expected), context, turn, signature))
            expert_contexts[context] += 1
            expert_actions_by_context[context][signature] += 1
            if context == "MAIN":
                expert_main_actions[signature] += 1
            elif context == "SETUP_ACTIVE":
                expert_setup_active[signature] += 1

        seed = (replay.get("configuration") or {}).get("seed")
        game_candidate: dict[str, dict[str, Any]] = {}
        for name, policy in candidates.items():
            if seed is not None:
                random.seed(int(seed))
            policy.deck()
            exact = semantic = faults = 0
            by_context = defaultdict(Counter)
            by_turn = defaultdict(Counter)
            for step_index, obs, expected, context, turn, expert_sig in decisions:
                try:
                    predicted = policy(obs)
                except Exception as exc:  # pragma: no cover - audit must preserve the sample
                    faults += 1
                    if len(mismatch_samples[name]) < 20:
                        mismatch_samples[name].append({
                            "episode": episode_id,
                            "step": step_index,
                            "context": context,
                            "fault": repr(exc),
                        })
                    continue
                predicted = list(predicted) if isinstance(predicted, list) else []
                predicted_sig = action_signature(obs, predicted)
                is_exact = predicted == expected
                is_semantic = predicted_sig == expert_sig
                exact += int(is_exact)
                semantic += int(is_semantic)
                candidate_counts[name]["calls"] += 1
                candidate_counts[name]["exact"] += int(is_exact)
                candidate_counts[name]["semantic"] += int(is_semantic)
                candidate_context[name][context]["calls"] += 1
                candidate_context[name][context]["exact"] += int(is_exact)
                candidate_context[name][context]["semantic"] += int(is_semantic)
                bucket = turn_bucket(turn)
                candidate_turn[name][bucket]["calls"] += 1
                candidate_turn[name][bucket]["exact"] += int(is_exact)
                candidate_turn[name][bucket]["semantic"] += int(is_semantic)
                candidate_archetype[name][archetype]["calls"] += 1
                candidate_archetype[name][archetype]["exact"] += int(is_exact)
                candidate_archetype[name][archetype]["semantic"] += int(is_semantic)
                if not is_semantic:
                    disagreement[name][f"{context}: {expert_sig} <- {predicted_sig}"] += 1
                    if len(mismatch_samples[name]) < 20:
                        mismatch_samples[name].append({
                            "episode": episode_id,
                            "step": step_index,
                            "reward": reward,
                            "archetype": archetype,
                            "turn": turn,
                            "context": context,
                            "expert": expert_sig,
                            "candidate": predicted_sig,
                        })
            game_candidate[name] = {
                "calls": len(decisions),
                "exact": exact,
                "semantic": semantic,
                "faults": faults,
            }

        ending = final_state(replay, seat)
        ending.update(result_event(replay))
        normalized_opp = " ".join(str(row.get("opp") or "").split()).casefold()
        games.append({
            "episode": episode_id,
            "end": row.get("end"),
            "reward": reward,
            "seat": seat,
            "opponent": row.get("opp"),
            "opponent_submission": row.get("opp_sub"),
            "opponent_score_snapshot": scores.get(normalized_opp),
            "opponent_archetype": archetype,
            "opponent_deck_hash": deck_hash(opponent_deck),
            "decisions": len(decisions),
            "ending": ending,
            "candidate_agreement": game_candidate,
        })

    games.sort(key=lambda game: game.get("end") or "")
    by_archetype_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for game in games:
        by_archetype_rows[game["opponent_archetype"]].append(game)

    def ratios(counter: Counter[str]) -> dict[str, Any]:
        calls = int(counter["calls"])
        return {
            "calls": calls,
            "exact": int(counter["exact"]),
            "exact_rate": round(counter["exact"] / calls, 6) if calls else None,
            "semantic": int(counter["semantic"]),
            "semantic_rate": round(counter["semantic"] / calls, 6) if calls else None,
        }

    candidate_report = {}
    for name in candidates:
        candidate_report[name] = {
            **candidate_meta[name],
            "overall": ratios(candidate_counts[name]),
            "by_context": {
                key: ratios(value) for key, value in sorted(candidate_context[name].items())
            },
            "by_turn_bucket": {
                key: ratios(value) for key, value in sorted(candidate_turn[name].items())
            },
            "by_opponent_archetype": {
                key: ratios(value) for key, value in sorted(candidate_archetype[name].items())
            },
            "top_semantic_disagreements": counter_json(disagreement[name], 40),
            "mismatch_samples": mismatch_samples[name],
        }

    decisive = len(games)
    deckout = {
        "our_deck_zero": sum(game["ending"]["our_deck_count"] == 0 for game in games),
        "opponent_deck_zero": sum(game["ending"]["opponent_deck_count"] == 0 for game in games),
        "either_deck_zero": sum(
            game["ending"]["our_deck_count"] == 0
            or game["ending"]["opponent_deck_count"] == 0
            for game in games
        ),
    }
    result_reason_names = {1: "prizes", 2: "deckout", 3: "no_active", 4: "card_effect"}
    result_reasons = Counter(
        result_reason_names.get(game["ending"].get("reason"), f"reason_{game['ending'].get('reason')}")
        for game in games
    )
    report = {
        "created_unix": time.time(),
        "method": "msato-alakazam-public-replay-policy-audit-v1",
        "action_alignment": "steps[s].ACTIVE observation -> steps[s+1].action",
        "scope": args.scope_label,
        "episodes": str(episode_path),
        "episodes_sha256": sha256(episode_path),
        "replay_dir": str(replay_dir),
        "replay_files_seen": len(files),
        "excluded_wrong_submission": excluded_wrong_submission,
        "excluded_wrong_deck": excluded_wrong_deck,
        "target_deck_hash": target_deck_hash,
        "sample": {
            **rate(games),
            "oldest_end": games[0]["end"] if games else None,
            "newest_end": games[-1]["end"] if games else None,
            "decisions": sum(game["decisions"] for game in games),
            "opponent_score_mean": round(statistics.mean(
                game["opponent_score_snapshot"]
                for game in games if game["opponent_score_snapshot"] is not None
            ), 2) if any(game["opponent_score_snapshot"] is not None for game in games) else None,
            "deckout_endings": deckout,
            "authoritative_result_reasons": counter_json(result_reasons),
        },
        "by_opponent_archetype": {
            key: rate(value) for key, value in sorted(by_archetype_rows.items())
        },
        "expert_decision_distribution": {
            "contexts": counter_json(expert_contexts),
            "actions_by_context": {
                key: counter_json(value, 60)
                for key, value in sorted(expert_actions_by_context.items())
            },
            "main_actions": counter_json(expert_main_actions, 60),
            "setup_active": counter_json(expert_setup_active, 30),
        },
        "candidate_agreement": candidate_report,
        "games": games,
        "elapsed_s": round(time.time() - started, 3),
    }
    reserve_json_output(args.out, overwrite=args.overwrite_output).write(report)
    print(json.dumps({
        "sample": report["sample"],
        "by_opponent_archetype": report["by_opponent_archetype"],
        "candidate_agreement": {
            name: data["overall"] for name, data in candidate_report.items()
        },
        "elapsed_s": report["elapsed_s"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
