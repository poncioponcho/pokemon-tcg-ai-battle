"""High-precision public-board matchup latch for the bronze-shot ticket.

The classifier uses only high-confidence public evolution/engine-line cards
frozen before candidate evaluation.  It never inspects an opponent's private
zones, submission identity, player identity, outcome, or future state.
"""

from __future__ import annotations

from typing import Any


UNKNOWN = "UNKNOWN"
EXACT = "EXACT"
CONFLICT = "CONFLICT"
ALAKAZAM = "ALAKAZAM"
LUCARIO = "LUCARIO"

TARGET_MODES = frozenset({ALAKAZAM, LUCARIO})
VISIBLE_ZONES = ("active", "bench", "discard")

# The two target whitelists are the semantic line markers frozen in the first
# bronze-shot preregistration.  Every ID was 100% pure on the old-ref design
# decks, and the target classes were 12/12 correct by turn 2 on the new ref.
# Non-target entries retain the conservative final-card signatures from the
# live audit.  Only a target entry may activate manual-only behavior.
STRICT_SIGNATURES = {
    LUCARIO: frozenset({673, 674, 675, 676, 677, 678}),
    "GRIMMSNARL": frozenset({648}),
    ALAKAZAM: frozenset({741, 742, 743}),
    "DRAGAPULT": frozenset({121}),
    "ARCHALUDON": frozenset({190}),
    "GARDEVOIR": frozenset({747}),
    "CHARIZARD": frozenset({790, 928}),
    "GENGAR": frozenset({772}),
    "CRUSTLE": frozenset({345}),
    "CORNERSTONE": frozenset({117}),
    "GHOLDENGO": frozenset({700, 191}),
}


def _card_id(card: Any) -> int:
    if isinstance(card, int):
        return int(card)
    if not isinstance(card, dict):
        return 0
    try:
        return int(card.get("id", 0) or 0)
    except (TypeError, ValueError):
        return 0


def _add_public_card(card: Any, ids: set[int]) -> None:
    """Collect one public card and public attachments/evolution history."""
    card_id = _card_id(card)
    if card_id > 0:
        ids.add(card_id)
    if not isinstance(card, dict):
        return
    for key in ("preEvolution", "tools", "energyCards"):
        nested = card.get(key) or []
        if isinstance(nested, list):
            for item in nested:
                _add_public_card(item, ids)


def visible_signature_names(obs: dict[str, Any]) -> frozenset[str]:
    """Return strict archetype signatures visible on the opponent's board."""
    current = obs.get("current") or {}
    players = current.get("players") or []
    try:
        your_index = int(current.get("yourIndex", -1))
    except (TypeError, ValueError):
        return frozenset()
    if len(players) != 2 or your_index not in (0, 1):
        return frozenset()

    opponent = players[1 - your_index] or {}
    public_ids: set[int] = set()
    for zone in VISIBLE_ZONES:
        cards = opponent.get(zone) or []
        if not isinstance(cards, list):
            continue
        for card in cards:
            _add_public_card(card, public_ids)

    return frozenset(
        name
        for name, signature_ids in STRICT_SIGNATURES.items()
        if public_ids & signature_ids
    )


class MatchupRouter:
    """Episode-local, abstaining classifier with a one-decision activation lag."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.mode = UNKNOWN
        self.pending: str | None = None
        self.seen_signatures: set[str] = set()
        self.decisions = 0
        self.first_signature_decision: int | None = None
        self.switched_decision: int | None = None

    def observe(self, obs: dict[str, Any]) -> str:
        """Observe one public state and return the behavior mode for this call.

        A target first seen on decision N is only activated on decision N+1.
        Any multi-archetype evidence, including evidence revealed later, locks
        the episode back to exact-v22.
        """
        self.decisions += 1
        observed = visible_signature_names(obs)
        if observed and self.first_signature_decision is None:
            self.first_signature_decision = self.decisions
        self.seen_signatures.update(observed)

        if self.mode in (EXACT, CONFLICT):
            return self.mode
        if len(self.seen_signatures) > 1:
            self.mode = CONFLICT
            self.pending = None
            return self.mode
        if not self.seen_signatures:
            return self.mode

        label = next(iter(self.seen_signatures))
        if label not in TARGET_MODES:
            self.mode = EXACT
            self.pending = None
            return self.mode
        if self.mode == label:
            return self.mode
        if self.pending == label:
            self.mode = label
            self.pending = None
            self.switched_decision = self.decisions
            return self.mode
        if self.pending is None:
            self.pending = label
            return self.mode

        self.mode = CONFLICT
        self.pending = None
        return self.mode

    def snapshot(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "pending": self.pending,
            "seen_signatures": sorted(self.seen_signatures),
            "decisions": self.decisions,
            "first_signature_decision": self.first_signature_decision,
            "switched_decision": self.switched_decision,
        }
