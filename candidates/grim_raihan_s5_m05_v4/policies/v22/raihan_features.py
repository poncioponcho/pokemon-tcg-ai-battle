"""Visible-state feature contract for the Raihan Grim residual head.

This module deliberately uses only the current public observation and legal
options.  It is copied byte-for-byte into a candidate package so training and
Kaggle inference cannot drift apart.
"""

from __future__ import annotations

from collections import Counter
from typing import Any


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


def bucket(value: int, cuts: tuple[int, ...]) -> str:
    for cut in cuts:
        if value <= cut:
            return f"le{cut}"
    return f"gt{cuts[-1]}"


def card_id(card: Any) -> int:
    return int(card.get("id", 0) or 0) if isinstance(card, dict) else 0


def zone(obs: dict[str, Any], player: int, area: int) -> list[Any]:
    current = obs.get("current") or {}
    players = current.get("players") or []
    if player not in (0, 1) or player >= len(players):
        return []
    key = {1: "deck", 2: "hand", 3: "discard", 4: "active", 5: "bench", 6: "prize"}.get(area)
    if key is None:
        return []
    value = players[player].get(key)
    return value if isinstance(value, list) else []


def option_source(obs: dict[str, Any], option: dict[str, Any]) -> tuple[int, int]:
    current = obs.get("current") or {}
    your = int(current.get("yourIndex", 0) or 0)
    raw = option.get("cardId")
    if isinstance(raw, int):
        return int(raw), int(option.get("area", 0) or 0)
    try:
        option_type = int(option.get("type", -1))
        index = int(option.get("index", -1))
        player = int(option.get("playerIndex", your) if option.get("playerIndex") is not None else your)
    except (TypeError, ValueError):
        return 0, 0
    area = 2 if option_type == 7 and option.get("area") is None else int(option.get("area", 0) or 0)
    cards = zone(obs, player, area)
    return (card_id(cards[index]), area) if 0 <= index < len(cards) else (0, area)


def option_target(obs: dict[str, Any], option: dict[str, Any]) -> tuple[int, int, int, int]:
    current = obs.get("current") or {}
    your = int(current.get("yourIndex", 0) or 0)
    try:
        area = int(option.get("inPlayArea", 0) or 0)
        index = int(option.get("inPlayIndex", -1))
        player = int(option.get("playerIndex", your) if option.get("playerIndex") is not None else your)
    except (TypeError, ValueError):
        return 0, 0, 0, 0
    cards = zone(obs, player, area)
    target = cards[index] if 0 <= index < len(cards) else None
    if not isinstance(target, dict):
        return 0, area, 0, 0
    hp = int(target.get("hp", 0) or 0)
    maximum = int(target.get("maxHp", hp) or hp)
    damage = max(0, maximum - hp)
    energy = len(target.get("energyCards") or [])
    return card_id(target), area, damage, energy


def option_type(option: dict[str, Any]) -> int:
    try:
        return int(option.get("type", -1))
    except (TypeError, ValueError):
        return -1


def option_descriptor(obs: dict[str, Any], option: dict[str, Any]) -> str:
    source, source_area = option_source(obs, option)
    target, target_area, damage, energy = option_target(obs, option)
    attack = int(option.get("attackId", 0) or 0)
    number = int(option.get("number", -1) if option.get("number") is not None else -1)
    return (
        f"{option_type(option)}:{source}:{source_area}:{target}:{target_area}:"
        f"d{bucket(damage, (0, 30, 70, 120))}:e{bucket(energy, (0, 1, 2))}:{attack}:{number}"
    )


def visible_archetype(obs: dict[str, Any]) -> str:
    current = obs.get("current") or {}
    your = int(current.get("yourIndex", 0) or 0)
    players = current.get("players") or []
    if len(players) != 2:
        return "unknown"
    opponent = players[1 - your]
    ids = {
        card_id(card)
        for card in (opponent.get("active") or []) + (opponent.get("bench") or [])
        if isinstance(card, dict)
    }
    matches = [name for name, signatures in ARCHETYPE_SIGNATURES if ids & signatures]
    return "+".join(matches) if matches else ("other" if ids else "unknown")


def board_tokens(prefix: str, player: dict[str, Any]) -> list[str]:
    tokens: list[str] = []
    for area_name in ("active", "bench"):
        for card in player.get(area_name) or []:
            if not isinstance(card, dict):
                continue
            cid = card_id(card)
            hp = int(card.get("hp", 0) or 0)
            maximum = int(card.get("maxHp", hp) or hp)
            damage = max(0, maximum - hp)
            energy = len(card.get("energyCards") or [])
            tokens.append(
                f"{prefix}_{area_name}={cid}:d{bucket(damage, (0, 30, 70, 120))}:"
                f"e{bucket(energy, (0, 1, 2))}"
            )
    return tokens


def state_tokens(obs: dict[str, Any]) -> list[str]:
    select = obs.get("select") or {}
    options = select.get("option") or []
    current = obs.get("current") or {}
    your = int(current.get("yourIndex", 0) or 0)
    players = current.get("players") or [{}, {}]
    if len(players) != 2:
        players = [{}, {}]
    me, opponent = players[your], players[1 - your]
    turn = int(current.get("turn", 0) or 0)
    action_count = int(current.get("turnActionCount", 0) or 0)
    hand = me.get("hand") or []
    discard = me.get("discard") or []
    hand_counts = Counter(card_id(card) for card in hand if isinstance(card, dict))
    discard_counts = Counter(card_id(card) for card in discard if isinstance(card, dict))
    first = int(current.get("firstPlayer", -1) if current.get("firstPlayer") is not None else -1)
    tokens = [
        f"turn={bucket(turn, (2, 4, 7, 10))}",
        f"action_count={bucket(action_count, (1, 3, 6, 10))}",
        f"hand_n={bucket(int(me.get('handCount', len(hand)) or 0), (2, 4, 6, 9))}",
        f"deck_n={bucket(int(me.get('deckCount', len(me.get('deck') or [])) or 0), (4, 9, 19, 34))}",
        f"prizes={len(me.get('prize') or [])}:{len(opponent.get('prize') or [])}",
        f"visible={visible_archetype(obs)}",
        f"first_rel={-1 if first == -1 else int(first == your)}",
        f"supporter={int(bool(current.get('supporterPlayed')))}",
        f"energy={int(bool(current.get('energyAttached')))}",
        f"retreated={int(bool(current.get('retreated')))}",
        "available=" + ",".join(str(value) for value in sorted({option_type(x) for x in options if isinstance(x, dict)})),
    ]
    tokens.extend(board_tokens("me", me))
    tokens.extend(board_tokens("op", opponent))
    tokens.extend(f"hand={cid}:n{bucket(count, (1, 2, 3))}" for cid, count in sorted(hand_counts.items()))
    tokens.extend(f"discard={cid}:n{bucket(count, (1, 2, 3))}" for cid, count in sorted(discard_counts.items()))
    return tokens


def option_features(obs: dict[str, Any], option: dict[str, Any]) -> dict[str, float]:
    descriptor = option_descriptor(obs, option)
    kind = option_type(option)
    features: dict[str, float] = {f"A={descriptor}": 1.0, f"T={kind}": 1.0}
    for token in state_tokens(obs):
        features[f"A={descriptor}|{token}"] = 1.0
        features[f"T={kind}|{token}"] = 1.0
    return features


def score_options(obs: dict[str, Any], weights: dict[str, float]) -> tuple[int, float, str]:
    options = (obs.get("select") or {}).get("option") or []
    scored: list[tuple[float, int]] = []
    for index, option in enumerate(options):
        if not isinstance(option, dict):
            continue
        score = sum(weights.get(key, 0.0) * value for key, value in option_features(obs, option).items())
        scored.append((score, index))
    if not scored:
        return -1, float("-inf"), ""
    scored.sort(key=lambda row: (row[0], -row[1]), reverse=True)
    best_score, best_index = scored[0]
    second = scored[1][0] if len(scored) > 1 else float("-inf")
    return best_index, best_score - second, option_descriptor(obs, options[best_index])
