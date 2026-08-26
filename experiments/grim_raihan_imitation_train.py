#!/usr/bin/env python3
"""Train a visible-state residual head from Raihan's exact-deck Grim pilot.

Only legal MAIN options and the current observation are used.  Replays are
deduplicated by episode, required to contain the exact v22 60-card multiset,
and split chronologically before any regularization or deployment gate is
selected.  Native W/L promotion remains a separate downstream requirement.
"""

from __future__ import annotations

import argparse
import json
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
    action_signature,
    classify_deck,
    deck_hash,
    initial_deck,
)
from experiments.grim_raihan_features import (  # noqa: E402
    option_descriptor,
    option_features,
    score_options,
)
from scripts.candidate_h2h import sha256  # noqa: E402
from scripts.safe_json_output import reserve_json_output  # noqa: E402


@dataclass
class Decision:
    episode: int
    reward: int
    turn: int
    obs: dict[str, Any]
    chosen: int


def metadata_map(path: pathlib.Path | None, team_name: str) -> dict[int, dict[str, Any]]:
    if path is None:
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload if isinstance(payload, list) else payload.get("games", [])
    result: dict[int, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        if row.get("opponent") == team_name:
            result[int(row["episode"])] = {
                "submission": row.get("opponent_submission"),
                "end": row.get("end"),
                "score": row.get("opponent_score_snapshot"),
            }
        elif row.get("team") == team_name or row.get("team_name") == team_name:
            episode_id = row.get("episode", row.get("id"))
            if episode_id is None:
                continue
            result[int(episode_id)] = {
                "submission": row.get("submission", row.get("submission_id")),
                "end": row.get("end", row.get("endTime")),
                "score": row.get("score"),
            }
    return result


def load_corpus(
    replay_dirs: list[pathlib.Path],
    team_name: str,
    target_deck: list[int],
    metadata: dict[int, dict[str, Any]],
    default_submission: int,
    reward_filter: int | None,
) -> tuple[list[Decision], dict[str, Any]]:
    target_hash = deck_hash(target_deck)
    files: dict[int, pathlib.Path] = {}
    invalid: list[dict[str, Any]] = []
    for directory in replay_dirs:
        for path in sorted(directory.glob("episode-*-replay.json")):
            try:
                episode = int(path.name.split("-")[1])
            except (IndexError, ValueError):
                continue
            files.setdefault(episode, path)

    decisions: list[Decision] = []
    games: list[dict[str, Any]] = []
    deck_hashes: Counter[str] = Counter()
    for episode, path in sorted(files.items()):
        try:
            replay = json.loads(path.read_text(encoding="utf-8"))
            names = (replay.get("info") or {}).get("TeamNames") or []
            if team_name not in names or len(names) != 2:
                continue
            seat = names.index(team_name)
            deck = initial_deck(replay, seat)
            this_hash = deck_hash(deck) if len(deck) == 60 else "invalid"
            deck_hashes[this_hash] += 1
            if this_hash != target_hash:
                invalid.append({"episode": episode, "reason": "deck_mismatch", "hash": this_hash})
                continue
            reward = int((replay.get("rewards") or [0, 0])[seat])
            if reward not in (-1, 1) or (reward_filter is not None and reward != reward_filter):
                continue
            opponent_deck = initial_deck(replay, 1 - seat)
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
                if not isinstance(select, dict) or int(select.get("context", -1)) != 0:
                    continue
                options = select.get("option") or []
                if not isinstance(action, list) or len(action) != 1 or len(options) < 2:
                    continue
                chosen = int(action[0])
                if chosen < 0 or chosen >= len(options) or not all(isinstance(x, dict) for x in options):
                    continue
                turn = int(((obs.get("current") or {}).get("turn", 0)) or 0)
                decisions.append(Decision(episode, reward, turn, obs, chosen))
                count += 1
            meta = metadata.get(episode, {})
            games.append({
                "episode": episode,
                "submission": int(meta.get("submission") or default_submission),
                "end": meta.get("end"),
                "score": meta.get("score"),
                "reward": reward,
                "opponent": names[1 - seat],
                "opponent_archetype": classify_deck(opponent_deck),
                "main_decisions": count,
                "source": str(path),
            })
        except Exception as exc:
            invalid.append({"episode": episode, "reason": type(exc).__name__, "error": str(exc)[:300]})
    games.sort(key=lambda row: row["episode"])
    decisions.sort(key=lambda row: (row.episode, row.turn))
    return decisions, {
        "team": team_name,
        "target_deck_hash": target_hash,
        "replay_dirs": [str(path) for path in replay_dirs],
        "unique_files_seen": len(files),
        "eligible_games": len(games),
        "wins": sum(int(row["reward"] == 1) for row in games),
        "losses": sum(int(row["reward"] == -1) for row in games),
        "deck_hashes": dict(deck_hashes),
        "invalid": invalid,
        "games": games,
    }


def split_games(games: list[dict[str, Any]]) -> dict[str, set[int]]:
    episodes = [int(row["episode"]) for row in games if int(row["main_decisions"]) > 0]
    n = len(episodes)
    train_end = max(1, int(n * 0.60))
    validation_end = min(n - 1, max(train_end + 1, int(n * 0.80))) if n >= 3 else n
    return {
        "train": set(episodes[:train_end]),
        "validation": set(episodes[train_end:validation_end]),
        "test": set(episodes[validation_end:]),
    }


def difference(left: dict[str, float], right: dict[str, float]) -> dict[str, float]:
    result = dict(left)
    for key, value in right.items():
        result[key] = result.get(key, 0.0) - value
        if result[key] == 0:
            result.pop(key)
    return result


def pairwise_rows(decisions: list[Decision]) -> tuple[list[dict[str, float]], list[int], list[float]]:
    rows: list[dict[str, float]] = []
    labels: list[int] = []
    weights: list[float] = []
    for decision in decisions:
        options = decision.obs["select"]["option"]
        chosen = option_features(decision.obs, options[decision.chosen])
        alternatives = [index for index in range(len(options)) if index != decision.chosen]
        pair_weight = 0.5 / len(alternatives)
        for index in alternatives:
            delta = difference(chosen, option_features(decision.obs, options[index]))
            rows.extend((delta, {key: -value for key, value in delta.items()}))
            labels.extend((1, 0))
            weights.extend((pair_weight, pair_weight))
    return rows, labels, weights


def chosen_support(decisions: list[Decision]) -> Counter[str]:
    return Counter(
        option_descriptor(row.obs, row.obs["select"]["option"][row.chosen])
        for row in decisions
    )


def evaluate(
    decisions: list[Decision],
    weights: dict[str, float],
    support: Counter[str],
    minimum_support: int = 0,
    minimum_margin: float = float("-inf"),
) -> dict[str, Any]:
    covered = exact = semantic = 0
    by_reward: dict[int, Counter[str]] = {-1: Counter(), 1: Counter()}
    by_turn: dict[str, Counter[str]] = {}
    for row in decisions:
        prediction, margin, descriptor = score_options(row.obs, weights)
        if prediction < 0 or support[descriptor] < minimum_support or margin < minimum_margin:
            continue
        covered += 1
        expected = [row.chosen]
        predicted = [prediction]
        exact_match = prediction == row.chosen
        semantic_match = action_signature(row.obs, predicted) == action_signature(row.obs, expected)
        exact += int(exact_match)
        semantic += int(semantic_match)
        by_reward[row.reward]["n"] += 1
        by_reward[row.reward]["semantic"] += int(semantic_match)
        turn = "01-02" if row.turn <= 2 else "03-04" if row.turn <= 4 else "05-07" if row.turn <= 7 else "08+"
        by_turn.setdefault(turn, Counter())["n"] += 1
        by_turn[turn]["semantic"] += int(semantic_match)
    coverage = covered / len(decisions) if decisions else 0.0
    accuracy = semantic / covered if covered else 0.0
    return {
        "decisions": len(decisions),
        "covered": covered,
        "coverage": round(coverage, 6),
        "exact": exact,
        "exact_accuracy": round(exact / covered, 6) if covered else None,
        "semantic": semantic,
        "semantic_accuracy": round(accuracy, 6) if covered else None,
        "signed_coverage_advantage": round(coverage * (2 * accuracy - 1), 6) if covered else None,
        "by_reward": {
            str(key): {
                "n": int(value["n"]),
                "semantic_accuracy": round(value["semantic"] / value["n"], 6) if value["n"] else None,
            }
            for key, value in by_reward.items()
        },
        "by_turn": {
            key: {
                "n": int(value["n"]),
                "semantic_accuracy": round(value["semantic"] / value["n"], 6),
            }
            for key, value in sorted(by_turn.items())
        },
    }


def fit(decisions: list[Decision], c_value: float) -> tuple[dict[str, float], Counter[str], int]:
    rows, labels, sample_weights = pairwise_rows(decisions)
    vectorizer = DictVectorizer(sparse=True, sort=True)
    matrix = vectorizer.fit_transform(rows)
    model = LogisticRegression(
        C=c_value,
        fit_intercept=False,
        solver="liblinear",
        max_iter=600,
        random_state=20260816,
    )
    model.fit(
        matrix,
        np.asarray(labels, dtype=np.int8),
        sample_weight=np.asarray(sample_weights, dtype=np.float64),
    )
    weights = {
        str(name): float(value)
        for name, value in zip(vectorizer.get_feature_names_out(), model.coef_[0], strict=True)
        if abs(float(value)) >= 1e-8
    }
    return weights, chosen_support(decisions), len(vectorizer.feature_names_)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replay-dir", action="append", required=True)
    parser.add_argument("--team-name", default="Raihan Ramadistra")
    parser.add_argument("--target-deck", default=str(ROOT / "candidates/grim_v22_final/deck.csv"))
    parser.add_argument("--metadata-audit")
    parser.add_argument("--default-submission", type=int, default=55177269)
    parser.add_argument("--reward-filter", type=int, choices=(-1, 1), default=None)
    parser.add_argument("--model-out", required=True)
    parser.add_argument("--report-out", required=True)
    parser.add_argument("--overwrite-output", action="store_true")
    args = parser.parse_args()

    started = time.time()
    deck_path = pathlib.Path(args.target_deck).expanduser().resolve()
    target_deck = [int(line.strip()) for line in deck_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(target_deck) != 60:
        raise SystemExit(f"target deck has {len(target_deck)} cards")
    metadata_path = pathlib.Path(args.metadata_audit).expanduser().resolve() if args.metadata_audit else None
    decisions, source = load_corpus(
        [pathlib.Path(value).expanduser().resolve() for value in args.replay_dir],
        args.team_name,
        target_deck,
        metadata_map(metadata_path, args.team_name),
        args.default_submission,
        args.reward_filter,
    )
    if source["eligible_games"] < 15 or len(decisions) < 100:
        raise SystemExit(f"insufficient corpus: games={source['eligible_games']} decisions={len(decisions)}")
    splits = split_games(source["games"])
    split_rows = {
        name: [row for row in decisions if row.episode in episodes]
        for name, episodes in splits.items()
    }

    regularization = []
    fitted: dict[float, tuple[dict[str, float], Counter[str], int]] = {}
    for c_value in (0.01, 0.03, 0.1, 0.3, 1.0):
        weights, support, feature_count = fit(split_rows["train"], c_value)
        metrics = evaluate(split_rows["validation"], weights, support)
        regularization.append({"C": c_value, "features": feature_count, "validation": metrics})
        fitted[c_value] = (weights, support, feature_count)
    best_row = max(
        regularization,
        key=lambda row: (
            row["validation"]["semantic_accuracy"] or 0.0,
            row["validation"]["signed_coverage_advantage"] or -1.0,
            -row["C"],
        ),
    )
    selected_c = float(best_row["C"])
    design_weights, design_support, _ = fitted[selected_c]

    gates = []
    for support_min in (1, 2, 3, 5, 8, 12):
        for margin_min in (0.0, 0.25, 0.5, 1.0, 1.5, 2.0):
            metrics = evaluate(
                split_rows["validation"],
                design_weights,
                design_support,
                support_min,
                margin_min,
            )
            gates.append({
                "minimum_support": support_min,
                "minimum_margin": margin_min,
                "validation": metrics,
            })
    eligible = [
        row
        for row in gates
        if (row["validation"]["coverage"] or 0.0) >= 0.05
        and (row["validation"]["semantic_accuracy"] or 0.0) >= 0.55
    ]
    if not eligible:
        eligible = [row for row in gates if (row["validation"]["covered"] or 0) > 0]
    selected_gate = max(
        eligible,
        key=lambda row: (
            row["validation"]["signed_coverage_advantage"] or -1.0,
            row["validation"]["semantic_accuracy"] or 0.0,
            row["validation"]["coverage"] or 0.0,
        ),
    )

    refit_rows = split_rows["train"] + split_rows["validation"]
    final_weights, final_support, final_features = fit(refit_rows, selected_c)
    test_gated = evaluate(
        split_rows["test"],
        final_weights,
        final_support,
        int(selected_gate["minimum_support"]),
        float(selected_gate["minimum_margin"]),
    )
    test_always = evaluate(split_rows["test"], final_weights, final_support)
    split_summary = {
        name: {
            "episodes": len(episodes),
            "decisions": len(split_rows[name]),
            "first_episode": min(episodes) if episodes else None,
            "last_episode": max(episodes) if episodes else None,
        }
        for name, episodes in splits.items()
    }

    model = {
        "version": "raihan-grim-visible-pairwise-residual-v1",
        "created_unix": time.time(),
        "source_team": args.team_name,
        "source_submissions": sorted({int(row["submission"]) for row in source["games"]}),
        "source_deck_hash": source["target_deck_hash"],
        "target_deck_sha256": sha256(deck_path),
        "reward_filter": args.reward_filter,
        "regularization_C": selected_c,
        "minimum_support": int(selected_gate["minimum_support"]),
        "minimum_margin": float(selected_gate["minimum_margin"]),
        "override_mode": "same_type",
        "weights": final_weights,
        "descriptor_support": dict(final_support),
        "visible_information_contract": (
            "current observation, own private hand, public boards/discards/counts/flags, and legal options; "
            "no future state, outcome, team, submission id, hidden opponent deck, or replay index"
        ),
    }
    report = {
        "created_unix": time.time(),
        "method": "raihan-exact-deck-visible-pairwise-residual-v1",
        "source": source,
        "split": split_summary,
        "regularization": regularization,
        "selected_C": selected_c,
        "gate_search": gates,
        "selected_gate": selected_gate,
        "refit": {"decisions": len(refit_rows), "features": final_features, "weights": len(final_weights)},
        "blind_test_gated": test_gated,
        "blind_test_always": test_always,
        "model_out": str(pathlib.Path(args.model_out).expanduser().resolve()),
        "elapsed_s": round(time.time() - started, 3),
        "promotion_contract": (
            "action fidelity is only a behavior screen; candidate must still beat exact-v22 in independent "
            "native H2H, retain cross-meta legs, produce zero faults, and pass exact-archive smoke"
        ),
    }
    reserve_json_output(args.model_out, overwrite=args.overwrite_output).write(model)
    reserve_json_output(args.report_out, overwrite=args.overwrite_output).write(report)
    print(json.dumps({
        "source": {key: source[key] for key in ("eligible_games", "wins", "losses", "deck_hashes")},
        "split": split_summary,
        "selected_C": selected_c,
        "selected_gate": selected_gate,
        "blind_test_gated": test_gated,
        "blind_test_always": test_always,
        "weights": len(final_weights),
        "elapsed_s": report["elapsed_s"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
