"""StateIso plus the stronger cross-date Daily Top residual and meta guards."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path


ALPHA = 320.0
MINIMUM_SUPPORT = 16.0
MAX_RULE_MARGIN = 500.0
PARENT_FALLBACK_LINES = {112, 169, 190, 646, 647, 648}


def _find_module(local_name: str, sibling_name: str) -> Path:
    candidates = [Path(f"/kaggle_simulations/agent/{local_name}"), Path(local_name)]
    if "__file__" in globals():
        here = Path(__file__).resolve().parent
        candidates.extend([here / local_name, here.parent / sibling_name / "main.py"])
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise ImportError(local_name)


def _find_artifact(name: str) -> Path:
    candidates = [Path(f"/kaggle_simulations/agent/{name}"), Path(name)]
    if "__file__" in globals():
        here = Path(__file__).resolve().parent
        candidates.append(here / name)
        if len(here.parents) > 2:
            candidates.append(
                here.parents[2]
                / "artifacts"
                / "official-daily-top-2026-07-23-all-days"
                / "contextual-family-cv-best"
                / name
            )
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise FileNotFoundError(name)


_V24_PATH = _find_module("dailyprior_main.py", "meta_i_alakazam_3f_dailyprior_v24")
_SPEC = importlib.util.spec_from_file_location("_ptcg_contextprior_strongguard", _V24_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError(_V24_PATH)
_V24 = importlib.util.module_from_spec(_SPEC)
_PREVIOUS_CWD = Path.cwd()
try:
    os.chdir(_V24_PATH.parent)
    _SPEC.loader.exec_module(_V24)
finally:
    os.chdir(_PREVIOUS_CWD)

_POLICY = json.loads(_find_artifact("policy.json").read_text(encoding="utf-8"))
_SUPPORT = json.loads(_find_artifact("policy_support.json").read_text(encoding="utf-8"))
_BASE = _V24._BASE


def _bucket(value: int, cuts: tuple[int, ...]) -> int:
    return sum(value > cut for cut in cuts)


def _features(obs, option):
    current = obs.current
    select = obs.select
    me = current.players[current.yourIndex]
    opponent = current.players[1 - current.yourIndex]
    context = _V24._int(select.context)
    option_type = _V24._int(option.type)
    card = _V24._option_card(obs, option)
    target = _V24._target_card(obs, option)
    card_id = getattr(card, "id", 0) if card is not None else 0
    target_id = getattr(target, "id", 0) if target is not None else 0
    attack_id = _V24._int(option.attackId, 0)
    effect_id = getattr(select.effect, "id", 0) if select.effect is not None else 0
    context_card = getattr(select.contextCard, "id", 0) if select.contextCard is not None else 0
    number = _V24._int(option.number, -1)
    exact = (
        f"{context}|{option_type}|{card_id}|{target_id}|"
        f"{effect_id}|{context_card}|{attack_id}|{number}"
    )
    own_ids = {card.id for card in me.active + me.bench if card is not None}
    opponent_ids = {
        card.id for card in opponent.active + opponent.bench if card is not None
    }
    own_stage = (
        int(741 in own_ids) + 2 * int(742 in own_ids) + 4 * int(743 in own_ids)
    )
    opponent_family = (
        "ala"
        if opponent_ids & {741, 742, 743}
        else "drag"
        if opponent_ids & {119, 120, 121}
        else "marnie"
        if opponent_ids & {112, 646, 647, 648}
        else "starmie"
        if opponent_ids & {1030, 1031}
        else "tusk"
        if 58 in opponent_ids
        else "other"
    )
    turn_bucket = _bucket(int(current.turn), (2, 4, 7, 11))
    deck_bucket = _bucket(int(me.deckCount), (4, 10, 20, 35))
    prize_bucket = _bucket(len(me.prize), (1, 2, 4))
    spent = 2 * int(bool(current.supporterPlayed)) + int(bool(current.energyAttached))
    action = f"{context}|{option_type}|{card_id}|{target_id}|{attack_id}"
    return [
        (f"exact|{exact}", 1.5),
        (f"card|{context}|{option_type}|{card_id}", 0.7),
        (f"state|{action}|t{turn_bucket}|s{own_stage}|r{spent}", 1.2),
        (f"resource|{action}|d{deck_bucket}|p{prize_bucket}", 0.8),
        (f"match|{action}|{opponent_family}", 0.8),
    ]


def heuristic_scores(obs):
    scores = _V24._ORIGINAL_HEURISTIC_SCORES(obs)
    live_seat = _V24._LIVE_SEAT
    if (
        live_seat is None
        or obs.current is None
        or obs.select is None
        or obs.current.yourIndex != live_seat
        or obs.select.context != _BASE.SelectContext.MAIN
        or obs.current.players[live_seat].deckCount <= 4
        or len(scores) < 2
    ):
        return scores
    opponent = obs.current.players[1 - live_seat]
    opponent_ids = {
        card.id for card in opponent.active + opponent.bench if card is not None
    }
    if opponent_ids & PARENT_FALLBACK_LINES:
        return scores
    ordered = sorted(scores, reverse=True)
    if ordered[0] - ordered[1] > MAX_RULE_MARGIN:
        return scores
    residuals = []
    supported_options = 0
    for option in obs.select.option:
        residual = 0.0
        supported = False
        for feature, feature_weight in _features(obs, option):
            if _SUPPORT.get(feature, 0.0) >= MINIMUM_SUPPORT:
                residual += feature_weight * _POLICY.get(feature, 0.0)
                supported = True
        residuals.append(residual)
        supported_options += int(supported)
    if supported_options < 2:
        return scores
    for index, residual in enumerate(residuals):
        scores[index] += ALPHA * residual
    return scores


_BASE.heuristic_scores = heuristic_scores
_V24.heuristic_scores = heuristic_scores
agent = _V24.agent
