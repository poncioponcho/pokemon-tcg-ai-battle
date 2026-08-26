"""StateIso plus a conservative exact-action prior from official Daily Top.

The prior is trained on all downloaded 2026-07-18..21 winning seats using the
fixed 3f4515092dc5 deck.  It only breaks close MAIN-action decisions, requires
support for at least two currently legal options, and never scores the
opponent's rollout policy.
"""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path


_ALPHA = 40.0
_MIN_SUPPORT = 24.0
_MAX_RULE_MARGIN = 500.0
_LIVE_SEAT = None


def _find_base() -> Path:
    candidates = [Path("/kaggle_simulations/agent/base_main.py"), Path("base_main.py")]
    if "__file__" in globals():
        here = Path(__file__).resolve().parent
        candidates.extend(
            [
                here / "base_main.py",
                here.parent / "meta_e_alakazam_3f_stateiso_standalone_v2" / "main.py",
            ]
        )
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise ImportError("StateIso base_main.py not found")


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
                / "exact3f-wins"
                / name
            )
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise FileNotFoundError(name)


_BASE_PATH = _find_base()
_SPEC = importlib.util.spec_from_file_location("_ptcg_dailyprior_base", _BASE_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError(f"cannot load StateIso policy from {_BASE_PATH}")
_BASE = importlib.util.module_from_spec(_SPEC)
_PREVIOUS_CWD = Path.cwd()
try:
    os.chdir(_BASE_PATH.parent)
    _SPEC.loader.exec_module(_BASE)
finally:
    os.chdir(_PREVIOUS_CWD)

_POLICY = json.loads(_find_artifact("policy.json").read_text(encoding="utf-8"))
_SUPPORT = json.loads(_find_artifact("policy_support.json").read_text(encoding="utf-8"))
_ORIGINAL_HEURISTIC_SCORES = _BASE.heuristic_scores
_ORIGINAL_AGENT = _BASE.agent


def _int(value, default=-1):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _option_card(obs, option):
    player_index = (
        option.playerIndex
        if option.playerIndex is not None
        else obs.current.yourIndex
    )
    card = _BASE.get_card(obs, option.area, option.index, player_index)
    if card is None and option.index is not None:
        card = _BASE.get_card(
            obs,
            _BASE.AreaType.HAND,
            option.index,
            obs.current.yourIndex,
        )
    return card


def _target_card(obs, option):
    if option.inPlayArea is None or option.inPlayIndex is None:
        return None
    return _BASE.get_card(
        obs,
        option.inPlayArea,
        option.inPlayIndex,
        obs.current.yourIndex,
    )


def _exact_key(obs, option):
    select = obs.select
    card = _option_card(obs, option)
    target = _target_card(obs, option)
    return "exact|{}|{}|{}|{}|{}|{}|{}|{}".format(
        _int(select.context),
        _int(option.type),
        getattr(card, "id", 0) if card is not None else 0,
        getattr(target, "id", 0) if target is not None else 0,
        getattr(select.effect, "id", 0) if select.effect is not None else 0,
        getattr(select.contextCard, "id", 0) if select.contextCard is not None else 0,
        _int(option.attackId, 0),
        _int(option.number, -1),
    )


def heuristic_scores(obs):
    scores = _ORIGINAL_HEURISTIC_SCORES(obs)
    if (
        _LIVE_SEAT is None
        or obs.current is None
        or obs.select is None
        or obs.current.yourIndex != _LIVE_SEAT
        or obs.select.context != _BASE.SelectContext.MAIN
        or obs.current.players[_LIVE_SEAT].deckCount <= 4
        or len(scores) < 2
    ):
        return scores
    ordered = sorted(scores, reverse=True)
    if ordered[0] - ordered[1] > _MAX_RULE_MARGIN:
        return scores
    priors = []
    for option in obs.select.option:
        key = _exact_key(obs, option)
        support = _SUPPORT.get(key, {}).get("available_weight", 0.0)
        priors.append(_POLICY.get(key) if support >= _MIN_SUPPORT else None)
    if sum(value is not None for value in priors) < 2:
        return scores
    for index, value in enumerate(priors):
        if value is not None:
            scores[index] += _ALPHA * value
    return scores


_BASE.heuristic_scores = heuristic_scores
_post_pick = _BASE._post_pick
OptionType = _BASE.OptionType
SelectContext = _BASE.SelectContext
AreaType = _BASE.AreaType
ATTACK_POWERFUL_HAND = _BASE.ATTACK_POWERFUL_HAND
Boss_Orders = _BASE.Boss_Orders
card_table = _BASE.card_table
to_observation_class = _BASE.to_observation_class


def agent(obs_dict):
    global _LIVE_SEAT
    try:
        obs = _BASE.to_observation_class(obs_dict)
        if obs.select is None:
            _LIVE_SEAT = None
        elif obs.current is not None:
            _LIVE_SEAT = obs.current.yourIndex
    except Exception:
        pass
    return _ORIGINAL_AGENT(obs_dict)
