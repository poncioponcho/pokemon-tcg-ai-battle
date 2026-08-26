"""M Sato visible-state imitation head with a complete Marnie-policy fallback.

The head ranks only currently legal MAIN options.  It was trained on public
replays of submission 55198468 with an episode-time split and uses no opponent
deck label, future state, reward, team name, or submission identifier.  Low
support or low margin returns the parent action unchanged.
"""

from __future__ import annotations

import importlib.util
import json
import os
from collections import Counter
from pathlib import Path


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


def _find(name):
    candidates = [Path(f"/kaggle_simulations/agent/{name}"), Path(name)]
    if "__file__" in globals():
        candidates.append(Path(__file__).resolve().parent / name)
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise FileNotFoundError(name)


_PARENT_PATH = _find("parent_main.py")
_SPEC = importlib.util.spec_from_file_location("_msato_imitation_parent", _PARENT_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError(_PARENT_PATH)
_PARENT = importlib.util.module_from_spec(_SPEC)
_PREVIOUS_CWD = Path.cwd()
try:
    os.chdir(_PARENT_PATH.parent)
    _SPEC.loader.exec_module(_PARENT)
finally:
    os.chdir(_PREVIOUS_CWD)

_MODEL = json.loads(_find("msato_model.json").read_text(encoding="utf-8"))
_WEIGHTS = {str(key): float(value) for key, value in _MODEL["weights"].items()}
_SUPPORT = Counter({str(key): int(value) for key, value in _MODEL["descriptor_support"].items()})
_MINIMUM_SUPPORT = int(_MODEL["minimum_support"])
_MINIMUM_MARGIN = float(_MODEL["minimum_margin"])
_MINIMUM_MARGIN = 1.0


def _bucket(value, cuts):
    for cut in cuts:
        if value <= cut:
            return f"le{cut}"
    return f"gt{cuts[-1]}"


def _zone(current, player, area):
    players = current.get("players") or []
    if player not in (0, 1) or player >= len(players):
        return []
    key = {1: "deck", 2: "hand", 3: "discard", 4: "active", 5: "bench", 6: "prize"}.get(area)
    if key is None:
        return []
    value = players[player].get(key)
    return value if isinstance(value, list) else []


def _card_id(obs, option):
    raw = option.get("cardId")
    if isinstance(raw, int):
        return raw
    current = obs.get("current") or {}
    your = int(current.get("yourIndex", 0) or 0)
    try:
        option_type = int(option.get("type", -1))
        index = int(option.get("index", -1))
    except (TypeError, ValueError):
        return 0
    if option_type == 7:
        area, player = 2, your
    else:
        try:
            area = int(option.get("area", 2 if option_type in (8, 9) else -1))
            player = int(option.get("playerIndex", your))
        except (TypeError, ValueError):
            return 0
    zone = _zone(current, player, area)
    if 0 <= index < len(zone) and isinstance(zone[index], dict):
        return int(zone[index].get("id", 0) or 0)
    return 0


def _zone_card_id(obs, player, area, index):
    if area is None or index is None:
        return 0
    zone = _zone(obs.get("current") or {}, player, area)
    if 0 <= index < len(zone) and isinstance(zone[index], dict):
        return int(zone[index].get("id", 0) or 0)
    return 0


def _descriptor(obs, option):
    try:
        option_type = int(option.get("type", -1))
    except (TypeError, ValueError):
        option_type = -1
    card = _card_id(obs, option)
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


def _classify_visible(ids):
    values = set(ids)
    matches = [name for name, signatures in ARCHETYPE_SIGNATURES if values & signatures]
    return "+".join(matches) if matches else "other"


def _visible_archetype(obs):
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
    return _classify_visible(ids) if ids else "unknown"


def _active_id(player):
    active = player.get("active") or []
    if active and isinstance(active[0], dict):
        return int(active[0].get("id", 0) or 0)
    return 0


def _features(obs, option):
    select = obs.get("select") or {}
    options = select.get("option") or []
    current = obs.get("current") or {}
    your = int(current.get("yourIndex", 0) or 0)
    players = current.get("players") or [{}, {}]
    if len(players) != 2:
        players = [{}, {}]
    me, opponent = players[your], players[1 - your]
    descriptor = _descriptor(obs, option)
    option_type = descriptor.split(":", 1)[0]
    turn = int(current.get("turn", 0) or 0)
    hand_count = int(me.get("handCount", len(me.get("hand") or [])) or 0)
    deck_count = int(me.get("deckCount", len(me.get("deck") or [])) or 0)
    our_prizes = len(me.get("prize") or [])
    opponent_prizes = len(opponent.get("prize") or [])
    available_types = ",".join(sorted({str(opt.get("type", -1)) for opt in options if isinstance(opt, dict)}))
    state_tokens = (
        f"turn={_bucket(turn, (2, 4, 7, 10))}",
        f"hand={_bucket(hand_count, (2, 4, 6, 9))}",
        f"deck={_bucket(deck_count, (4, 9, 19, 34))}",
        f"prizes={our_prizes}:{opponent_prizes}",
        f"visible={_visible_archetype(obs)}",
        f"active={_active_id(me)}:{_active_id(opponent)}",
        f"supporter={int(bool(current.get('supporterPlayed')))}",
        f"energy={int(bool(current.get('energyAttached')))}",
        f"available={available_types}",
    )
    features = {f"A={descriptor}": 1.0, f"T={option_type}": 1.0}
    for token in state_tokens:
        features[f"A={descriptor}|{token}"] = 1.0
        features[f"T={option_type}|{token}"] = 1.0
    return features


def _model_pick(obs):
    select = obs.get("select")
    if not isinstance(select, dict) or select.get("context") != 0:
        return None
    options = select.get("option") or []
    if len(options) < 2 or not all(isinstance(option, dict) for option in options):
        return None
    scored = []
    for index, option in enumerate(options):
        score = sum(_WEIGHTS.get(key, 0.0) * value for key, value in _features(obs, option).items())
        scored.append((score, index))
    scored.sort(reverse=True)
    best_score, best_index = scored[0]
    margin = best_score - scored[1][0]
    descriptor = _descriptor(obs, options[best_index])
    if _SUPPORT[descriptor] < _MINIMUM_SUPPORT or margin < _MINIMUM_MARGIN:
        return None
    return [best_index]


def agent(obs):
    parent_action = _PARENT.agent(obs)
    try:
        model_action = _model_pick(obs)
        return model_action if model_action is not None else parent_action
    except Exception:
        return parent_action
