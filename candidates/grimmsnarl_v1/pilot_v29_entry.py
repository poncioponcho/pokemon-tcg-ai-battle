"""Grim fixed-deck visible router: v28 default, v22 for mirror/psychic.

Both policies are deterministic handwritten engines for the identical 60-card
Grimmsnarl deck.  Routing uses only opponent cards already visible in active,
bench, or discard zones.  v28 advances its embedded v22 engine on every call,
so switching after a signature appears does not introduce stale policy state.
"""
from __future__ import annotations

from policies.v22.main import agent as _v22
from policies.v28.main import agent as _v28


_PSYCHIC_LINE = frozenset({741, 742, 743})
_GRIM_LINE = frozenset({646, 647, 648})
_SPECIAL = _PSYCHIC_LINE | _GRIM_LINE
_mode = "v28"
_last_turn = None


def _visible_ids(obs):
    state = obs.get("current") or {}
    players = state.get("players") or []
    try:
        opponent = players[1 - int(state.get("yourIndex", 0) or 0)]
    except (IndexError, TypeError, ValueError):
        return set()
    cards = []
    for zone in ("active", "bench", "discard"):
        cards.extend(opponent.get(zone) or [])
    return {
        int(card.get("id", card.get("cardId", 0)) or 0)
        for card in cards if isinstance(card, dict)
    }


def competition_entrypoint(obs):
    global _last_turn, _mode
    if not obs or obs.get("select") is None:
        _mode = "v28"
        _last_turn = None
        return _v28(obs or {"select": None})

    state = obs.get("current") or {}
    turn = state.get("turn")
    if isinstance(turn, int):
        if _last_turn is not None and turn < _last_turn:
            _mode = "v28"
            # The local H2H harness reuses modules across games.  Explicitly
            # reset both stateful engines before processing the new game.
            try:
                _v28({"select": None})
            except Exception:
                pass
        _last_turn = turn

    if _mode == "v28" and (_visible_ids(obs) & _SPECIAL):
        _mode = "v22"
    return _v22(obs) if _mode == "v22" else _v28(obs)
