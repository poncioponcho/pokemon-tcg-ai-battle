"""Pure-Python deployable Route-A head copied into a passing candidate.

This module intentionally has no NumPy/sklearn/repository imports.  The model
JSON is loaded once from the same package directory.  Any error fails closed
to the exact action supplied by v22 main.py.
"""

from __future__ import annotations

import json
import math
import os

from . import validated_fallback_policy as fallback  # type: ignore[attr-defined]


MAX_SCORE_GAP = 25.0
_MODEL = None
_USED = False


def reset():
    global _USED
    _USED = False


def _model():
    global _MODEL
    if _MODEL is None:
        path = os.path.join(os.path.dirname(__file__), "routeA_model.json")
        with open(path, encoding="utf-8") as stream:
            payload = json.load(stream)
        coefficients = tuple(float(value) for value in payload["coefficients"])
        if len(coefficients) != 65:
            raise ValueError("Route-A model coefficient width mismatch")
        _MODEL = (
            float(payload["intercept"]),
            coefficients,
            float(payload["decision_threshold"]),
        )
    return _MODEL


def _clip(value, low=0.0, high=1.0):
    return min(high, max(low, float(value)))


def _semantic_key(option):
    keys = (
        "type", "source_id", "source_zone", "source_rel",
        "target_id", "target_serial", "target_area", "target_rel",
        "attack_id", "area",
    )
    return tuple(int(option.get(key, 0) or 0) for key in keys)


def _active_metrics(player):
    active = (player.get("active") or [{}])[0] or {}
    hp = float(active.get("hp", 0) or 0)
    max_hp = float(active.get("maxHp", 0) or 0)
    energy = float(active.get("en", 0) or 0)
    return ((_clip(hp / max_hp) if max_hp > 0 else 0.0), _clip(energy / 4.0))


def _features(state, exact_option, alternative_option, exact_score, alternative_score):
    me = state.get("me") or {}
    op = state.get("op") or {}
    flags = state.get("flags") or {}
    me_hp, me_energy = _active_metrics(me)
    op_hp, op_energy = _active_metrics(op)
    board = [
        int((card or {}).get("id", 0) or 0)
        for card in (me.get("active") or []) + (me.get("bench") or [])
        if isinstance(card, dict)
    ]
    exact_type = int(exact_option.get("type", -1))
    alt_type = int(alternative_option.get("type", -1))
    gap = abs(float(exact_score) - float(alternative_score))
    values = [
        _clip(float(state.get("turn", 0) or 0) / 20.0),
        _clip(float(state.get("tac", 0) or 0) / 20.0),
        float(state.get("first_rel", -1) or 0),
        float(bool(flags.get("energy"))),
        float(bool(flags.get("supporter"))),
        float(bool(flags.get("stadium"))),
        float(bool(flags.get("retreated"))),
        _clip(float(me.get("prize_n", 0) or 0) / 6.0),
        _clip(float(op.get("prize_n", 0) or 0) / 6.0),
        _clip(float(me.get("hand_n", 0) or 0) / 10.0),
        _clip(float(op.get("hand_n", 0) or 0) / 10.0),
        _clip(float(me.get("deck", 0) or 0) / 60.0),
        _clip(float(op.get("deck", 0) or 0) / 60.0),
        _clip(len(me.get("bench") or []) / 5.0),
        _clip(len(op.get("bench") or []) / 5.0),
        me_hp,
        me_energy,
        op_hp,
        op_energy,
        _clip(board.count(646) / 4.0),
        _clip(board.count(647) / 3.0),
        _clip(board.count(648) / 3.0),
        _clip(board.count(112) / 4.0),
        _clip((board.count(860) + board.count(104)) / 4.0),
        _clip(float(exact_score) / 10000.0, -1.0, 1.5),
        _clip(float(alternative_score) / 10000.0, -1.0, 1.5),
        _clip(gap / 1200.0),
        float(alt_type == 7),
        float(alt_type == 9),
        float(alt_type == 8),
        float(alt_type == 10),
        float(alt_type == exact_type),
    ]
    if len(values) != 32:
        raise ValueError("Route-A feature width mismatch")
    return tuple(values)


def _proposal(state, options, history, exact_action):
    if int(state.get("context", -1)) != 0 or len(exact_action) != 1:
        return None
    exact_index = int(exact_action[0])
    if not 0 <= exact_index < len(options):
        return None
    exact_option = options[exact_index]
    exact_key = _semantic_key(exact_option)
    exact_score = float(fallback.main_score(state, exact_option, history))
    candidates = []
    for index, option in enumerate(options):
        if index == exact_index or _semantic_key(option) == exact_key:
            continue
        action_type = int(option.get("type", -1))
        source_id = int(option.get("source_id", 0) or 0)
        if action_type not in (7, 8, 9, 10):
            continue
        if action_type == 7 and source_id == 1182:
            continue
        score = float(fallback.main_score(state, option, history))
        candidates.append((score, -index, option))
    if not candidates:
        return None
    alternative_score, neg_index, alternative_option = max(candidates)
    if abs(exact_score - alternative_score) > MAX_SCORE_GAP:
        return None
    alternative_index = -neg_index
    return (
        [alternative_index],
        _features(state, exact_option, alternative_option, exact_score, alternative_score),
    )


def _probability(features, treatment, intercept, coefficients):
    design = list(features) + [float(treatment)]
    design.extend(float(treatment) * value for value in features)
    logit = intercept + sum(weight * value for weight, value in zip(coefficients, design))
    if logit >= 0:
        exp_neg = math.exp(-min(logit, 60.0))
        return 1.0 / (1.0 + exp_neg)
    exp_pos = math.exp(max(logit, -60.0))
    return exp_pos / (1.0 + exp_pos)


def maybe_override(state, options, history, exact_action):
    global _USED
    if _USED:
        return list(exact_action)
    try:
        proposal = _proposal(state, options, history, exact_action)
        if proposal is None:
            return list(exact_action)
        alternative_action, features = proposal
        intercept, coefficients, threshold = _model()
        advantage = (
            _probability(features, 1, intercept, coefficients)
            - _probability(features, 0, intercept, coefficients)
        )
        if advantage < threshold:
            return list(exact_action)
        _USED = True
        return list(alternative_action)
    except Exception:
        return list(exact_action)
