#!/usr/bin/env python3
"""Audit when opponent archetypes become identifiable from public live state."""

from __future__ import annotations

import argparse
import csv
import json
import math
import pathlib
import sys
import time
from collections import Counter, defaultdict
from typing import Any


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiments.live_v22_replay_audit import ARCHETYPE_SIGNATURES, _opponent_deck  # noqa: E402
from scripts.candidate_h2h import sha256  # noqa: E402
from scripts.safe_json_output import reserve_json_output  # noqa: E402


DESIGN_REF = 55499962
HOLDOUT_REF = 55516725
TURN_POINTS: tuple[int | str, ...] = (0, 1, 2, 3, 4, 5, 6, 8, 10, "end")


def _card_names() -> dict[int, str]:
    path = ROOT / "candidates" / "grim_v22_final" / "EN_Card_Data.csv"
    names: dict[int, str] = {}
    with path.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            try:
                names[int(row["Card ID"])] = str(row["Card Name"])
            except (KeyError, TypeError, ValueError):
                continue
    return names


def _add_card(card: Any, ids: set[int]) -> None:
    if isinstance(card, int):
        ids.add(int(card))
        return
    if not isinstance(card, dict):
        return
    try:
        card_id = int(card.get("id", 0) or 0)
    except (TypeError, ValueError):
        card_id = 0
    if card_id > 0:
        ids.add(card_id)
    for key in ("preEvolution", "tools", "energyCards"):
        nested = card.get(key) or []
        if isinstance(nested, list):
            for item in nested:
                _add_card(item, ids)


def _public_opponent_ids(current: dict[str, Any], opponent_seat: int) -> set[int]:
    ids: set[int] = set()
    players = current.get("players") or []
    if not 0 <= opponent_seat < len(players):
        return ids
    opponent = players[opponent_seat] or {}
    for zone in ("active", "bench", "discard"):
        for card in opponent.get(zone) or []:
            _add_card(card, ids)
    for card in current.get("stadium") or []:
        if isinstance(card, dict) and int(card.get("playerIndex", -1) or -1) == opponent_seat:
            _add_card(card, ids)
    return ids


def _timeline(replay: dict[str, Any], seat: int) -> dict[int, set[int]]:
    cumulative: set[int] = set()
    by_turn: dict[int, set[int]] = {}
    for step in replay.get("steps") or []:
        if not isinstance(step, list) or not 0 <= seat < len(step):
            continue
        record = step[seat]
        if record.get("status") != "ACTIVE":
            continue
        current = (record.get("observation") or {}).get("current")
        if not isinstance(current, dict):
            continue
        turn = int(current.get("turn", 0) or 0)
        cumulative.update(_public_opponent_ids(current, 1 - seat))
        by_turn[turn] = set(cumulative)
    return by_turn


def _ids_at(timeline: dict[int, set[int]], point: int | str) -> set[int]:
    if not timeline:
        return set()
    if point == "end":
        return set(timeline[max(timeline)])
    eligible = [turn for turn in timeline if turn <= int(point)]
    return set(timeline[max(eligible)]) if eligible else set()


def _signature_prediction(ids: set[int]) -> str:
    matches = [name for name, signatures in ARCHETYPE_SIGNATURES if ids & signatures]
    return "+".join(matches) if matches else "unknown"


def _primary(label: str) -> str:
    return label.split("+", 1)[0] if label != "other" else "other"


def _marker_dictionary(design: list[dict[str, Any]], names: dict[int, str]) -> list[dict[str, Any]]:
    unique_decks: dict[str, dict[str, Any]] = {}
    for game in design:
        unique_decks.setdefault(game["deck_hash"], game)
    support: dict[int, Counter[str]] = defaultdict(Counter)
    for game in unique_decks.values():
        label = _primary(game["gold"])
        for card_id in set(game["deck"]):
            support[int(card_id)][label] += 1
    markers = []
    for card_id, counts in support.items():
        total = sum(counts.values())
        ranking = counts.most_common()
        if total < 2 or not ranking or ranking[0][0] == "other":
            continue
        top_label, top_count = ranking[0]
        if len(ranking) > 1 and ranking[1][1] == top_count:
            continue
        purity = top_count / total
        if purity < 0.80:
            continue
        other = total - top_count
        markers.append({
            "card_id": card_id,
            "card_name": names.get(card_id, f"card-{card_id}"),
            "label": top_label,
            "support_unique_design_decks": total,
            "label_support": top_count,
            "purity": round(purity, 6),
            "weight": round(math.log((top_count + 1.0) / (other + 1.0)), 8),
        })
    markers.sort(key=lambda row: (-float(row["purity"]), -int(row["support_unique_design_decks"]), int(row["card_id"])))
    return markers


def _marker_prediction(ids: set[int], marker_map: dict[int, dict[str, Any]]) -> str:
    scores: Counter[str] = Counter()
    for card_id in ids:
        marker = marker_map.get(card_id)
        if marker is not None:
            scores[str(marker["label"])] += float(marker["weight"])
    if not scores:
        return "unknown"
    ranking = scores.most_common()
    if len(ranking) > 1 and abs(ranking[0][1] - ranking[1][1]) <= 1e-12:
        return "unknown"
    return ranking[0][0]


def _matrix(games: list[dict[str, Any]], predictor: Any, point: int | str, *, primary: bool) -> dict[str, dict[str, int]]:
    matrix: dict[str, Counter[str]] = defaultdict(Counter)
    for game in games:
        gold = _primary(game["gold"]) if primary else game["gold"]
        prediction = predictor(_ids_at(game["timeline"], point))
        matrix[gold][prediction] += 1
    return {gold: dict(sorted(values.items())) for gold, values in sorted(matrix.items())}


def _curve(games: list[dict[str, Any]], predictor: Any, *, primary: bool) -> list[dict[str, Any]]:
    rows = []
    for point in TURN_POINTS:
        predictions = []
        for game in games:
            gold = _primary(game["gold"]) if primary else game["gold"]
            prediction = predictor(_ids_at(game["timeline"], point))
            predictions.append((gold, prediction))
        predicted = sum(prediction != "unknown" for _, prediction in predictions)
        correct = sum(gold == prediction for gold, prediction in predictions)
        compatible = sum(
            prediction != "unknown" and set(prediction.split("+")) <= set(gold.split("+"))
            for gold, prediction in predictions
        )
        rows.append({
            "turn": point,
            "episodes": len(games),
            "predicted": predicted,
            "coverage": round(predicted / len(games), 6) if games else None,
            "correct": correct,
            "accuracy": round(correct / len(games), 6) if games else None,
            "precision_when_predicted": round(correct / predicted, 6) if predicted else None,
            "compatible_partial_or_exact": compatible,
            "compatible_precision": round(compatible / predicted, 6) if predicted else None,
        })
    return rows


def _stable_turns(games: list[dict[str, Any]], predictor: Any, *, primary: bool) -> dict[str, Any]:
    values = []
    by_label: dict[str, list[int]] = defaultdict(list)
    for game in games:
        gold = _primary(game["gold"]) if primary else game["gold"]
        turns = sorted(game["timeline"])
        predictions = [predictor(game["timeline"][turn]) for turn in turns]
        stable = None
        for index, (turn, prediction) in enumerate(zip(turns, predictions)):
            if prediction == gold and all(later == gold for later in predictions[index:]):
                stable = turn
                break
        if stable is not None:
            values.append(stable)
            by_label[gold].append(stable)
    ordered = sorted(values)
    percentile = lambda q: ordered[min(len(ordered) - 1, int((len(ordered) - 1) * q))] if ordered else None
    return {
        "recognized": len(values),
        "episodes": len(games),
        "rate": round(len(values) / len(games), 6) if games else None,
        "median_turn": percentile(0.5),
        "p90_turn": percentile(0.9),
        "by_label": {
            label: {
                "recognized": len(turns),
                "median_turn": sorted(turns)[(len(turns) - 1) // 2],
                "turns": sorted(turns),
            }
            for label, turns in sorted(by_label.items())
        },
    }


def _evaluation(games: list[dict[str, Any]], predictor: Any, *, primary: bool) -> dict[str, Any]:
    return {
        "episodes": len(games),
        "curve": _curve(games, predictor, primary=primary),
        "confusion_matrices": {
            str(point): _matrix(games, predictor, point, primary=primary)
            for point in (2, 4, 6, "end")
        },
        "stable_recognition": _stable_turns(games, predictor, primary=primary),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", required=True)
    parser.add_argument("--replay-dir", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    audit_path = pathlib.Path(args.audit).resolve()
    replay_dir = pathlib.Path(args.replay_dir).resolve()
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    if len(audit.get("games") or []) != 82:
        raise SystemExit("matchup recognition audit requires frozen 82-game snapshot")
    reservation = reserve_json_output(args.out)
    names = _card_names()
    games = []
    started = time.time()
    for row in audit["games"]:
        episode = int(row["episode"])
        replay_path = replay_dir / f"episode-{episode}-replay.json"
        replay = json.loads(replay_path.read_text(encoding="utf-8"))
        seat = int(row["seat"])
        deck = _opponent_deck(replay, 1 - seat)
        if len(deck) != 60:
            raise SystemExit(f"opponent deck extraction failed ep={episode}")
        games.append({
            "episode": episode,
            "ref": int(row["ref"]),
            "seat": seat,
            "gold": str(row["opponent_archetype"]),
            "deck_hash": str(row["opponent_deck_hash"]),
            "deck": deck,
            "timeline": _timeline(replay, seat),
        })
    design = [game for game in games if game["ref"] == DESIGN_REF]
    holdout = [game for game in games if game["ref"] == HOLDOUT_REF]
    if len(design) != 50 or len(holdout) != 32:
        raise SystemExit("frozen ref split changed")
    design_hashes = {game["deck_hash"] for game in design}
    novel_holdout = [game for game in holdout if game["deck_hash"] not in design_hashes]
    markers = _marker_dictionary(design, names)
    marker_map = {int(marker["card_id"]): marker for marker in markers}
    marker_predictor = lambda ids: _marker_prediction(ids, marker_map)

    report = {
        "created_unix": time.time(),
        "method": "live-visible-matchup-recognition-design-holdout-v1",
        "scope": "read-only postseason feasibility; no candidate promotion",
        "analysis_plan": str(ROOT / "reports" / "20260815_postfinal_exploration_plan.md"),
        "source_audit": str(audit_path),
        "source_audit_sha256": sha256(audit_path),
        "replay_dir": str(replay_dir),
        "public_episodes": len(games),
        "design_ref": DESIGN_REF,
        "design_episodes": len(design),
        "holdout_ref": HOLDOUT_REF,
        "holdout_episodes": len(holdout),
        "novel_deck_holdout_episodes": len(novel_holdout),
        "unique_decks": len({game["deck_hash"] for game in games}),
        "visible_information_contract": (
            "cumulative opponent active/bench/discard plus public evolution/tool/energy "
            "cards and opponent-owned stadium; no hidden hand/deck/future state"
        ),
        "gold_labels": dict(Counter(game["gold"] for game in games)),
        "strict_signature_all82": _evaluation(games, _signature_prediction, primary=False),
        "learned_markers": {
            "rules": {"unique_design_deck_support_min": 2, "purity_min": 0.80},
            "count": len(markers),
            "markers": markers,
            "holdout32": _evaluation(holdout, marker_predictor, primary=True),
            "novel_deck_holdout": _evaluation(novel_holdout, marker_predictor, primary=True),
        },
        "elapsed_s": round(time.time() - started, 6),
        "winner": None,
        "submitted": False,
    }
    reservation.write(report)
    strict_end = report["strict_signature_all82"]["curve"][-1]
    marker_t4 = next(row for row in report["learned_markers"]["holdout32"]["curve"] if row["turn"] == 4)
    print(
        f"Matchup recognition complete strict_end={strict_end['correct']}/82 "
        f"marker_holdout_t4={marker_t4['correct']}/32 coverage={marker_t4['coverage']}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
