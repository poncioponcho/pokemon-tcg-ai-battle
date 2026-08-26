#!/usr/bin/env python3
"""Train a small visible-state option scorer from M Sato's rank-leading Alakazam.

The learner is deliberately an option-ranking residual, not a whole-agent
network.  It sees only information present in the live observation, ranks the
currently legal MAIN options, and can fall back to a complete rule/search
policy when support or score margin is low.  Episodes are split by time at the
game level before fitting; validation chooses regularization and a deployment
gate, while the newest split is reported once as a blind test.
"""

from __future__ import annotations

import argparse
import json
import math
import pathlib
import sys
import time
from collections import Counter
from dataclasses import dataclass
from typing import Any

import numpy as np
from sklearn.feature_extraction import DictVectorizer
from sklearn.linear_model import LogisticRegression


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiments.alakazam_msato_policy_audit import (  # noqa: E402
    ALAKAZAM_SIGNATURE,
    action_signature,
    classify_deck,
    deck_hash,
    initial_deck,
    resolve_card_id,
)
from scripts.candidate_h2h import sha256  # noqa: E402
from scripts.safe_json_output import reserve_json_output  # noqa: E402


@dataclass
class Decision:
    episode: int
    end: str
    reward: int
    turn: int
    obs: dict[str, Any]
    chosen: int


def _bucket(value: int, cuts: tuple[int, ...]) -> str:
    for cut in cuts:
        if value <= cut:
            return f"le{cut}"
    return f"gt{cuts[-1]}"


def _zone_card_id(
    obs: dict[str, Any], player: int, area: int | None, index: int | None
) -> int:
    if area is None or index is None:
        return 0
    current = obs.get("current") or {}
    players = current.get("players") or []
    if player not in (0, 1) or player >= len(players):
        return 0
    key = {1: "deck", 2: "hand", 3: "discard", 4: "active", 5: "bench", 6: "prize"}.get(area)
    if key is None:
        return 0
    zone = players[player].get(key)
    if not isinstance(zone, list) or index < 0 or index >= len(zone):
        return 0
    card = zone[index]
    return int(card.get("id", 0) or 0) if isinstance(card, dict) else 0


def option_descriptor(obs: dict[str, Any], option: dict[str, Any]) -> str:
    try:
        option_type = int(option.get("type", -1))
    except (TypeError, ValueError):
        option_type = -1
    card = resolve_card_id(obs, option) or 0
    current = obs.get("current") or {}
    your = int(current.get("yourIndex", 0) or 0)
    try:
        in_area = int(option["inPlayArea"]) if option.get("inPlayArea") is not None else None
        in_index = int(option["inPlayIndex"]) if option.get("inPlayIndex") is not None else None
    except (TypeError, ValueError):
        in_area = in_index = None
    target = _zone_card_id(obs, your, in_area, in_index)
    attack = int(option.get("attackId", 0) or 0)
    number = int(option.get("number", -1) if option.get("number") is not None else -1)
    return f"{option_type}:{card}:{target}:{attack}:{number}"


def _visible_archetype(obs: dict[str, Any]) -> str:
    current = obs.get("current") or {}
    your = int(current.get("yourIndex", 0) or 0)
    players = current.get("players") or []
    if len(players) != 2:
        return "unknown"
    opponent = players[1 - your]
    ids = [
        int(card.get("id", 0) or 0)
        for card in (opponent.get("active") or []) + (opponent.get("bench") or [])
        if isinstance(card, dict)
    ]
    return classify_deck(ids) if ids else "unknown"


def _active_id(player: dict[str, Any]) -> int:
    active = player.get("active") or []
    if active and isinstance(active[0], dict):
        return int(active[0].get("id", 0) or 0)
    return 0


def option_features(obs: dict[str, Any], option: dict[str, Any]) -> dict[str, float]:
    """Sparse option/state interaction features, all legal at live inference."""
    select = obs.get("select") or {}
    options = select.get("option") or []
    current = obs.get("current") or {}
    your = int(current.get("yourIndex", 0) or 0)
    players = current.get("players") or [{}, {}]
    if len(players) != 2:
        players = [{}, {}]
    me, opponent = players[your], players[1 - your]
    descriptor = option_descriptor(obs, option)
    option_type = descriptor.split(":", 1)[0]
    turn = int(current.get("turn", 0) or 0)
    hand_count = int(me.get("handCount", len(me.get("hand") or [])) or 0)
    deck_count = int(me.get("deckCount", len(me.get("deck") or [])) or 0)
    our_prizes = len(me.get("prize") or [])
    opponent_prizes = len(opponent.get("prize") or [])
    visible_arch = _visible_archetype(obs)
    own_active = _active_id(me)
    opponent_active = _active_id(opponent)
    available_types = ",".join(sorted({str(opt.get("type", -1)) for opt in options if isinstance(opt, dict)}))
    state_tokens = (
        f"turn={_bucket(turn, (2, 4, 7, 10))}",
        f"hand={_bucket(hand_count, (2, 4, 6, 9))}",
        f"deck={_bucket(deck_count, (4, 9, 19, 34))}",
        f"prizes={our_prizes}:{opponent_prizes}",
        f"visible={visible_arch}",
        f"active={own_active}:{opponent_active}",
        f"supporter={int(bool(current.get('supporterPlayed')))}",
        f"energy={int(bool(current.get('energyAttached')))}",
        f"available={available_types}",
    )
    features: dict[str, float] = {
        f"A={descriptor}": 1.0,
        f"T={option_type}": 1.0,
    }
    for token in state_tokens:
        features[f"A={descriptor}|{token}"] = 1.0
        features[f"T={option_type}|{token}"] = 1.0
    return features


def _difference(left: dict[str, float], right: dict[str, float]) -> dict[str, float]:
    result = dict(left)
    for key, value in right.items():
        result[key] = result.get(key, 0.0) - value
        if result[key] == 0:
            result.pop(key)
    return result


def load_decisions(
    episode_path: pathlib.Path,
    replay_dir: pathlib.Path,
    team_name: str,
    opponent_archetype: str | None = None,
    context: int = 0,
    reward_filter: int | None = None,
) -> tuple[list[Decision], dict[str, Any]]:
    metadata = {
        int(row["id"]): row
        for row in json.loads(episode_path.read_text(encoding="utf-8"))
        if row.get("opp_sub") is not None and row.get("reward") in (-1, 1)
    }
    decisions: list[Decision] = []
    games: list[dict[str, Any]] = []
    target_hash = None
    excluded = 0
    for path in sorted(replay_dir.glob("episode-*-replay.json")):
        replay = json.loads(path.read_text(encoding="utf-8"))
        episode = int((replay.get("info") or {}).get("EpisodeId", -1))
        row = metadata.get(episode)
        names = (replay.get("info") or {}).get("TeamNames") or []
        if row is None or team_name not in names or len(names) != 2:
            excluded += 1
            continue
        seat = names.index(team_name)
        deck = initial_deck(replay, seat)
        if len(deck) != 60 or not ALAKAZAM_SIGNATURE.issubset(set(deck)):
            excluded += 1
            continue
        this_hash = deck_hash(deck)
        if target_hash is None:
            target_hash = this_hash
        if this_hash != target_hash:
            raise SystemExit(f"multiple expert deck hashes, episode={episode}")
        opponent_deck = initial_deck(replay, 1 - seat)
        archetype = classify_deck(opponent_deck)
        if opponent_archetype and archetype != opponent_archetype:
            continue
        reward = int((replay.get("rewards") or [0, 0])[seat])
        if reward_filter is not None and reward != reward_filter:
            continue
        count = 0
        steps = replay.get("steps") or []
        for index in range(len(steps) - 1):
            if seat >= len(steps[index]) or seat >= len(steps[index + 1]):
                continue
            record = steps[index][seat]
            if record.get("status") != "ACTIVE":
                continue
            obs = record.get("observation") or {}
            select = obs.get("select")
            action = steps[index + 1][seat].get("action")
            if not isinstance(select, dict) or select.get("context") != context:
                continue
            if not isinstance(action, list) or len(action) != 1:
                continue
            options = select.get("option") or []
            chosen = int(action[0])
            if chosen < 0 or chosen >= len(options) or len(options) < 2:
                continue
            if not all(isinstance(option, dict) for option in options):
                continue
            turn = int(((obs.get("current") or {}).get("turn", 0)) or 0)
            decisions.append(Decision(episode, str(row.get("end") or ""), reward, turn, obs, chosen))
            count += 1
        games.append({
            "episode": episode,
            "end": str(row.get("end") or ""),
            "reward": reward,
            "opponent_archetype": archetype,
            "main_decisions": count,
        })
    games.sort(key=lambda row: row["end"])
    decisions.sort(key=lambda row: (row.end, row.episode))
    return decisions, {
        "games": games,
        "excluded_replay_files": excluded,
        "target_deck_hash": target_hash,
        "opponent_archetype_filter": opponent_archetype,
        "context": context,
        "reward_filter": reward_filter,
    }


def split_episodes(games: list[dict[str, Any]]) -> dict[str, set[int]]:
    episodes = [int(game["episode"]) for game in games if game["main_decisions"] > 0]
    n = len(episodes)
    train_end = max(1, int(n * 0.60))
    validation_end = max(train_end + 1, int(n * 0.80))
    return {
        "train": set(episodes[:train_end]),
        "validation": set(episodes[train_end:validation_end]),
        "test": set(episodes[validation_end:]),
    }


def pairwise_rows(decisions: list[Decision]) -> tuple[list[dict[str, float]], list[int], list[float]]:
    rows: list[dict[str, float]] = []
    labels: list[int] = []
    weights: list[float] = []
    for decision in decisions:
        options = decision.obs["select"]["option"]
        chosen_features = option_features(decision.obs, options[decision.chosen])
        alternatives = [index for index in range(len(options)) if index != decision.chosen]
        pair_weight = 0.5 / len(alternatives)
        for index in alternatives:
            alternative_features = option_features(decision.obs, options[index])
            positive = _difference(chosen_features, alternative_features)
            rows.append(positive)
            labels.append(1)
            weights.append(pair_weight)
            rows.append({key: -value for key, value in positive.items()})
            labels.append(0)
            weights.append(pair_weight)
    return rows, labels, weights


def score_options(
    decision: Decision, weights: dict[str, float]
) -> tuple[int, float, int, str]:
    options = decision.obs["select"]["option"]
    scored = []
    for index, option in enumerate(options):
        score = sum(weights.get(key, 0.0) * value for key, value in option_features(decision.obs, option).items())
        scored.append((score, index))
    scored.sort(reverse=True)
    best_score, best_index = scored[0]
    second_score = scored[1][0] if len(scored) > 1 else -math.inf
    descriptor = option_descriptor(decision.obs, options[best_index])
    return best_index, best_score - second_score, len(options), descriptor


def evaluate(
    decisions: list[Decision],
    weights: dict[str, float],
    descriptor_support: Counter[str],
    minimum_support: int = 0,
    minimum_margin: float = -math.inf,
) -> dict[str, Any]:
    exact = semantic = covered = 0
    margins: list[float] = []
    by_turn: dict[str, Counter[str]] = {}
    for decision in decisions:
        prediction, margin, _, descriptor = score_options(decision, weights)
        is_covered = descriptor_support[descriptor] >= minimum_support and margin >= minimum_margin
        if not is_covered:
            continue
        covered += 1
        margins.append(margin)
        expert = [decision.chosen]
        predicted = [prediction]
        exact += int(prediction == decision.chosen)
        semantic += int(action_signature(decision.obs, predicted) == action_signature(decision.obs, expert))
        bucket = _bucket(decision.turn, (2, 4, 7, 10))
        row = by_turn.setdefault(bucket, Counter())
        row["n"] += 1
        row["exact"] += int(prediction == decision.chosen)
    return {
        "decisions": len(decisions),
        "covered": covered,
        "coverage": round(covered / len(decisions), 6) if decisions else None,
        "exact": exact,
        "exact_accuracy": round(exact / covered, 6) if covered else None,
        "semantic": semantic,
        "semantic_accuracy": round(semantic / covered, 6) if covered else None,
        "margin_mean": round(float(np.mean(margins)), 6) if margins else None,
        "by_turn": {
            key: {
                "n": int(value["n"]),
                "exact_accuracy": round(value["exact"] / value["n"], 6),
            }
            for key, value in sorted(by_turn.items())
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episodes", required=True)
    parser.add_argument("--replay-dir", required=True)
    parser.add_argument("--team-name", default="M Sato")
    parser.add_argument(
        "--opponent-archetype",
        default="",
        help="optional exact full-deck archetype filter for matchup-specialist training",
    )
    parser.add_argument(
        "--context",
        type=int,
        default=0,
        help="SelectContext integer to imitate; default 0 is MAIN",
    )
    parser.add_argument(
        "--reward-filter",
        type=int,
        choices=(-1, 1),
        default=None,
        help="optional exploratory outcome-conditioned trajectory filter",
    )
    parser.add_argument("--model-out", required=True)
    parser.add_argument("--report-out", required=True)
    parser.add_argument("--overwrite-output", action="store_true")
    args = parser.parse_args()

    episode_path = pathlib.Path(args.episodes).expanduser().resolve()
    replay_dir = pathlib.Path(args.replay_dir).expanduser().resolve()
    started = time.time()
    decisions, source = load_decisions(
        episode_path,
        replay_dir,
        args.team_name,
        args.opponent_archetype or None,
        args.context,
        args.reward_filter,
    )
    splits = split_episodes(source["games"])
    split_rows = {
        name: [decision for decision in decisions if decision.episode in episodes]
        for name, episodes in splits.items()
    }
    train_pairs, train_labels, train_weights = pairwise_rows(split_rows["train"])
    vectorizer = DictVectorizer(sparse=True, sort=True)
    matrix = vectorizer.fit_transform(train_pairs)
    labels = np.asarray(train_labels, dtype=np.int8)
    sample_weights = np.asarray(train_weights, dtype=np.float64)

    descriptor_support: Counter[str] = Counter()
    for decision in split_rows["train"]:
        for option in decision.obs["select"]["option"]:
            descriptor_support[option_descriptor(decision.obs, option)] += 1

    candidates = []
    fitted: dict[float, tuple[LogisticRegression, dict[str, float]]] = {}
    for c_value in (0.03, 0.1, 0.3, 1.0, 3.0):
        model = LogisticRegression(
            C=c_value,
            fit_intercept=False,
            solver="liblinear",
            max_iter=500,
            random_state=20260815,
        )
        model.fit(matrix, labels, sample_weight=sample_weights)
        names = vectorizer.get_feature_names_out()
        weights = {
            str(name): float(weight)
            for name, weight in zip(names, model.coef_[0], strict=True)
            if abs(float(weight)) >= 1e-8
        }
        validation = evaluate(split_rows["validation"], weights, descriptor_support)
        candidates.append({"C": c_value, "validation": validation})
        fitted[c_value] = (model, weights)
    best = max(candidates, key=lambda row: (row["validation"]["exact_accuracy"] or 0, -row["C"]))
    best_c = float(best["C"])
    _, learned_weights = fitted[best_c]

    gates = []
    fallback_accuracy = 0.40
    for support in (0, 3, 8, 16, 32):
        for margin in (-1.0, 0.0, 0.25, 0.5, 1.0, 2.0):
            metrics = evaluate(
                split_rows["validation"], learned_weights, descriptor_support, support, margin
            )
            coverage = metrics["coverage"] or 0.0
            accuracy = metrics["exact_accuracy"] or 0.0
            estimated = coverage * accuracy + (1 - coverage) * fallback_accuracy
            gates.append({
                "minimum_support": support,
                "minimum_margin": margin,
                "estimated_with_40pct_fallback": round(estimated, 6),
                "validation": metrics,
            })
    eligible_gates = [row for row in gates if (row["validation"]["coverage"] or 0) >= 0.15]
    selected_gate = max(
        eligible_gates,
        key=lambda row: (
            row["estimated_with_40pct_fallback"],
            row["validation"]["exact_accuracy"] or 0,
        ),
    )
    test_metrics = evaluate(
        split_rows["test"],
        learned_weights,
        descriptor_support,
        int(selected_gate["minimum_support"]),
        float(selected_gate["minimum_margin"]),
    )
    test_always = evaluate(split_rows["test"], learned_weights, descriptor_support)

    split_summary = {
        name: {
            "episodes": len(episodes),
            "decisions": len(split_rows[name]),
            "oldest_end": min((row.end for row in split_rows[name]), default=None),
            "newest_end": max((row.end for row in split_rows[name]), default=None),
        }
        for name, episodes in splits.items()
    }
    model_artifact = {
        "version": "msato-alakazam-visible-pairwise-v1",
        "created_unix": time.time(),
        "source_submission": 55198468,
        "context": args.context,
        "reward_filter": args.reward_filter,
        "source_episodes_sha256": sha256(episode_path),
        "source_deck_hash": source["target_deck_hash"],
        "split": split_summary,
        "regularization_C": best_c,
        "minimum_support": int(selected_gate["minimum_support"]),
        "minimum_margin": float(selected_gate["minimum_margin"]),
        "weights": learned_weights,
        "descriptor_support": dict(descriptor_support),
        "visible_information_contract": (
            "current turn/hand/deck/prizes/boards, supporter/energy flags, and legal options only; "
            "no episode outcome, future state, full opponent deck, team, or submission id"
        ),
    }
    report = {
        "created_unix": time.time(),
        "method": "visible-state-pairwise-option-imitation-v1",
        "source": source,
        "split": split_summary,
        "training": {
            "pair_rows": len(train_pairs),
            "features": len(vectorizer.feature_names_),
            "regularization_candidates": candidates,
            "selected_C": best_c,
        },
        "gate_search": gates,
        "selected_gate": selected_gate,
        "blind_test_gated": test_metrics,
        "blind_test_always_model": test_always,
        "model_out": str(pathlib.Path(args.model_out).expanduser().resolve()),
        "elapsed_s": round(time.time() - started, 3),
        "interpretation_limit": (
            "held-out action fidelity is not W/L; promotion still requires native H2H, "
            "cross-meta regression, zero-fault, and exact-archive checks"
        ),
    }
    reserve_json_output(args.model_out, overwrite=args.overwrite_output).write(model_artifact)
    reserve_json_output(args.report_out, overwrite=args.overwrite_output).write(report)
    print(json.dumps({
        "split": split_summary,
        "selected_C": best_c,
        "selected_gate": selected_gate,
        "blind_test_gated": test_metrics,
        "blind_test_always_model": test_always,
        "weights": len(learned_weights),
        "elapsed_s": report["elapsed_s"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
