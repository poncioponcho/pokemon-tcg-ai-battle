"""High-confidence visible-state residual with exact-v22 fallback."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from .raihan_features import option_type, score_options


_ROOT = Path(__file__).resolve().parent
_MODEL = json.loads((_ROOT / "raihan_model.json").read_text(encoding="utf-8"))
_CONFIG = json.loads((_ROOT / "raihan_config.json").read_text(encoding="utf-8"))
_WEIGHTS = {str(key): float(value) for key, value in _MODEL["weights"].items()}
_SUPPORT = Counter({str(key): int(value) for key, value in _MODEL["descriptor_support"].items()})


def maybe_override(obs: dict[str, Any], parent_action: list[int]) -> list[int]:
    """Return a learned action only inside the frozen high-confidence envelope."""
    try:
        select = obs.get("select")
        if not isinstance(select, dict) or int(select.get("context", -1)) != 0:
            return parent_action
        options = select.get("option") or []
        if len(parent_action) != 1 or len(options) < 2 or not all(isinstance(row, dict) for row in options):
            return parent_action
        parent_index = int(parent_action[0])
        if parent_index < 0 or parent_index >= len(options):
            return parent_action
        turn = int(((obs.get("current") or {}).get("turn", 0)) or 0)
        if turn < int(_CONFIG.get("minimum_turn", 0)) or turn > int(_CONFIG.get("maximum_turn", 999)):
            return parent_action
        if turn in {int(value) for value in _CONFIG.get("excluded_turns", [])}:
            return parent_action
        blocked_ids = {int(value) for value in _CONFIG.get("blocked_opponent_visible_ids", [])}
        if blocked_ids:
            current = obs.get("current") or {}
            your = int(current.get("yourIndex", 0) or 0)
            players = current.get("players") or []
            if len(players) == 2:
                opponent = players[1 - your]
                visible_ids = {
                    int(card.get("id", 0) or 0)
                    for card in (opponent.get("active") or []) + (opponent.get("bench") or [])
                    if isinstance(card, dict)
                }
                if visible_ids & blocked_ids:
                    return parent_action
        prediction, margin, descriptor = score_options(obs, _WEIGHTS)
        if prediction < 0 or prediction == parent_index:
            return parent_action
        if _SUPPORT[descriptor] < int(_CONFIG["minimum_support"]):
            return parent_action
        if margin < float(_CONFIG["minimum_margin"]):
            return parent_action
        if _CONFIG.get("override_mode") == "same_type":
            if option_type(options[prediction]) != option_type(options[parent_index]):
                return parent_action
        return [prediction]
    except Exception:
        return parent_action
