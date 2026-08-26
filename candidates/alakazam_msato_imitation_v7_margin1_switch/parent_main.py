"""Strong contextual residual with parent fallbacks for three proven families."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path


STARMIE_LINE = {1030, 1031}


def _find_base() -> Path:
    candidates = [
        Path("/kaggle_simulations/agent/strongguard_main.py"),
        Path("strongguard_main.py"),
    ]
    if "__file__" in globals():
        here = Path(__file__).resolve().parent
        candidates.extend(
            [
                here / "strongguard_main.py",
                here.parent
                / "meta_i_alakazam_3f_contextprior_strongguard_v28"
                / "main.py",
            ]
        )
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise ImportError("strongguard_main.py not found")


_BASE_PATH = _find_base()
_SPEC = importlib.util.spec_from_file_location("_ptcg_contextprior_triguard", _BASE_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError(_BASE_PATH)
_BASE = importlib.util.module_from_spec(_SPEC)
_PREVIOUS_CWD = Path.cwd()
try:
    os.chdir(_BASE_PATH.parent)
    _SPEC.loader.exec_module(_BASE)
finally:
    os.chdir(_PREVIOUS_CWD)

_CONTEXTUAL_HEURISTIC = _BASE.heuristic_scores


def heuristic_scores(obs):
    if obs.current is not None:
        opponent = obs.current.players[1 - obs.current.yourIndex]
        opponent_ids = {
            card.id for card in opponent.active + opponent.bench if card is not None
        }
        if opponent_ids & STARMIE_LINE:
            return _BASE._V24._ORIGINAL_HEURISTIC_SCORES(obs)
    return _CONTEXTUAL_HEURISTIC(obs)


_BASE._BASE.heuristic_scores = heuristic_scores
_BASE._V24.heuristic_scores = heuristic_scores
agent = _BASE.agent
