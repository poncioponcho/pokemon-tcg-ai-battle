"""Visible-archetype router for the final Lucario challenger.

The advanced rule policy is stronger in the mirror and against the tested
Grim/Great-Tusk families, but it regresses badly against Alakazam.  Both policy
modules use the same locked 60-card deck, so routing on cards already visible
to the player changes only decision policy and does not use hidden information.
"""

from __future__ import annotations

import advanced_policy
import retreat_policy


ALAKAZAM_LINE = frozenset({741, 742, 743})  # Abra, Kadabra, Alakazam

_mode = "advanced"
_last_turn: int | None = None


def _card_id(card) -> int | None:
    if not isinstance(card, dict):
        return None
    value = card.get("id")
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _opponent_shows_alakazam(state: dict) -> bool:
    players = state.get("players") or []
    try:
        your_index = int(state.get("yourIndex", 0))
        opponent = players[1 - your_index]
    except (IndexError, TypeError, ValueError):
        return False

    visible = []
    for zone in ("active", "bench", "discard"):
        visible.extend(opponent.get(zone) or [])
    return any(_card_id(card) in ALAKAZAM_LINE for card in visible)


def agent(obs_dict: dict) -> list[int]:
    global _last_turn, _mode

    if not isinstance(obs_dict, dict):
        return advanced_policy.competition_entrypoint(obs_dict)

    state = obs_dict.get("current")
    if state is None and obs_dict.get("select") is None:
        _mode = "advanced"
        _last_turn = None
        return advanced_policy.competition_entrypoint(obs_dict)

    if isinstance(state, dict):
        turn = state.get("turn")
        if isinstance(turn, int):
            # The local H2H harness reuses the imported module across games.
            # A decreasing turn counter is therefore also a new-game signal.
            if _last_turn is not None and turn < _last_turn:
                _mode = "advanced"
            _last_turn = turn
        if _mode == "advanced" and _opponent_shows_alakazam(state):
            _mode = "retreat"

    if _mode == "retreat":
        return retreat_policy.agent(obs_dict)
    return advanced_policy.competition_entrypoint(obs_dict)


def competition_entrypoint(obs_dict: dict) -> list[int]:
    """Absolute-final one-argument callable for Kaggle discovery."""
    return agent(obs_dict)
