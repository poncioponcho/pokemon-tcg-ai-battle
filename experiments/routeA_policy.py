#!/usr/bin/env python3
"""Runtime-safe primitives for the Route-A single-intervention policy.

The frozen exact-v22 tree is never edited.  Local experiments subclass the
isolated CandidateAgent and wrap only ``policies.v22.main.choose``.  That hook
is reached only after manual guards decline; main.py's legality guard and
episode reset remain downstream/upstream respectively.
"""

from __future__ import annotations

import math
import pathlib
import time
from dataclasses import dataclass
from typing import Any

from scripts.candidate_h2h import CandidateAgent


MAIN_MODULE = "policies.v22.main"
FALLBACK_MODULE = "policies.v22.validated_fallback_policy"
TURN_BUCKETS = ("turn<=2", "turn3-4", "turn5-8", "turn>=9")
PROPOSER_THRESHOLDS = (25, 50, 100, 200, 300, 500, 800, 1200)
DECISION_THRESHOLDS = (0.0, 0.01, 0.02, 0.03, 0.05, 0.08)

FEATURE_NAMES = (
    "turn",
    "turn_action_count",
    "first_player_relative",
    "flag_energy_attached",
    "flag_supporter_played",
    "flag_stadium_played",
    "flag_retreated",
    "own_prize_count",
    "opponent_prize_count",
    "own_hand_count",
    "opponent_hand_count",
    "own_deck_count",
    "opponent_deck_count",
    "own_bench_count",
    "opponent_bench_count",
    "own_active_hp_ratio",
    "own_active_energy",
    "opponent_active_hp_ratio",
    "opponent_active_energy",
    "board_impidimp",
    "board_morgrem",
    "board_grimmsnarl",
    "board_munkidori",
    "board_snorunt_froslass",
    "exact_fallback_score",
    "alternative_fallback_score",
    "absolute_score_gap",
    "alternative_is_play",
    "alternative_is_evolve",
    "alternative_is_attach",
    "alternative_is_ability",
    "same_action_type",
)

if len(FEATURE_NAMES) != 32:
    raise RuntimeError("Route-A feature contract must remain exactly 32 dimensions")


def _clip(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return min(high, max(low, float(value)))


def turn_bucket(turn: int) -> str:
    if turn <= 2:
        return "turn<=2"
    if turn <= 4:
        return "turn3-4"
    if turn <= 8:
        return "turn5-8"
    return "turn>=9"


def semantic_key(option: dict[str, Any]) -> tuple[int, ...]:
    """Collapse interchangeable source copies while preserving target identity.

    Two copies of the same Trainer/Energy in hand have different simulator
    serials but produce the same action.  Counting those as policy divergence
    makes every episode look eligible.  Target serial remains because choosing
    between two same-ID in-play Pokemon can change energy/HP continuity.
    """
    keys = (
        "type", "source_id", "source_zone", "source_rel",
        "target_id", "target_serial", "target_area", "target_rel",
        "attack_id", "area",
    )
    return tuple(int(option.get(key, 0) or 0) for key in keys)


def _active_metrics(player: dict[str, Any]) -> tuple[float, float]:
    active = (player.get("active") or [{}])[0] or {}
    hp = float(active.get("hp", 0) or 0)
    max_hp = float(active.get("maxHp", 0) or 0)
    energy = float(active.get("en", 0) or 0)
    return ((_clip(hp / max_hp) if max_hp > 0 else 0.0), _clip(energy / 4.0))


def make_features(
    state: dict[str, Any],
    exact_option: dict[str, Any],
    alternative_option: dict[str, Any],
    exact_score: float,
    alternative_score: float,
) -> list[float]:
    me = state.get("me") or {}
    op = state.get("op") or {}
    flags = state.get("flags") or {}
    me_active_hp, me_active_energy = _active_metrics(me)
    op_active_hp, op_active_energy = _active_metrics(op)
    own_board = [
        int((card or {}).get("id", 0) or 0)
        for card in (me.get("active") or []) + (me.get("bench") or [])
        if isinstance(card, dict)
    ]
    exact_type = int(exact_option.get("type", -1))
    alternative_type = int(alternative_option.get("type", -1))
    gap = abs(float(exact_score) - float(alternative_score))
    features = [
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
        me_active_hp,
        me_active_energy,
        op_active_hp,
        op_active_energy,
        _clip(own_board.count(646) / 4.0),
        _clip(own_board.count(647) / 3.0),
        _clip(own_board.count(648) / 3.0),
        _clip(own_board.count(112) / 4.0),
        _clip((own_board.count(860) + own_board.count(104)) / 4.0),
        _clip(float(exact_score) / 10000.0, -1.0, 1.5),
        _clip(float(alternative_score) / 10000.0, -1.0, 1.5),
        _clip(gap / 1200.0),
        float(alternative_type == 7),
        float(alternative_type == 9),
        float(alternative_type == 8),
        float(alternative_type == 10),
        float(alternative_type == exact_type),
    ]
    if len(features) != len(FEATURE_NAMES):
        raise RuntimeError(f"Route-A feature width changed: {len(features)}")
    return features


@dataclass(frozen=True)
class Proposal:
    exact_action: tuple[int, ...]
    alternative_action: tuple[int, ...]
    exact_score: float
    alternative_score: float
    score_gap: float
    bucket: str
    features: tuple[float, ...]
    exact_semantic: tuple[int, ...]
    alternative_semantic: tuple[int, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "exact_action": list(self.exact_action),
            "alternative_action": list(self.alternative_action),
            "exact_score": round(self.exact_score, 6),
            "alternative_score": round(self.alternative_score, 6),
            "score_gap": round(self.score_gap, 6),
            "bucket": self.bucket,
            "features": list(self.features),
            "exact_semantic": list(self.exact_semantic),
            "alternative_semantic": list(self.alternative_semantic),
        }


def propose_safe_alternative(
    fallback_module: Any,
    state: dict[str, Any],
    options: list[dict[str, Any]],
    history: list[dict[str, Any]],
    exact_action: list[int],
    max_score_gap: float,
) -> Proposal | None:
    if int(state.get("context", -1)) != 0 or len(exact_action) != 1:
        return None
    exact_index = int(exact_action[0])
    if not 0 <= exact_index < len(options):
        return None
    exact_option = options[exact_index]
    exact_semantic = semantic_key(exact_option)
    exact_score = float(fallback_module.main_score(state, exact_option, history))
    candidates: list[tuple[float, int, dict[str, Any]]] = []
    for index, option in enumerate(options):
        if index == exact_index or semantic_key(option) == exact_semantic:
            continue
        action_type = int(option.get("type", -1))
        source_id = int(option.get("source_id", 0) or 0)
        if action_type not in (7, 8, 9, 10):
            continue
        if action_type == 7 and source_id == 1182:  # Boss is not a safe random action.
            continue
        score = float(fallback_module.main_score(state, option, history))
        candidates.append((score, -index, option))
    if not candidates:
        return None
    alternative_score, neg_index, alternative_option = max(candidates)
    alternative_index = -neg_index
    gap = abs(exact_score - alternative_score)
    if gap > float(max_score_gap):
        return None
    return Proposal(
        exact_action=(exact_index,),
        alternative_action=(alternative_index,),
        exact_score=exact_score,
        alternative_score=alternative_score,
        score_gap=gap,
        bucket=turn_bucket(int(state.get("turn", 0) or 0)),
        features=tuple(make_features(
            state, exact_option, alternative_option, exact_score, alternative_score
        )),
        exact_semantic=exact_semantic,
        alternative_semantic=semantic_key(alternative_option),
    )


@dataclass(frozen=True)
class LinearResponseModel:
    intercept: float
    coefficients: tuple[float, ...]
    decision_threshold: float

    def _probability(self, features: tuple[float, ...], treatment: int) -> float:
        if len(features) != len(FEATURE_NAMES) or len(self.coefficients) != 65:
            raise ValueError("Route-A model shape mismatch")
        design = list(features) + [float(treatment)]
        design.extend(float(treatment) * value for value in features)
        logit = self.intercept + sum(w * x for w, x in zip(self.coefficients, design))
        if logit >= 0:
            exp_neg = math.exp(-min(logit, 60.0))
            return 1.0 / (1.0 + exp_neg)
        exp_pos = math.exp(max(logit, -60.0))
        return exp_pos / (1.0 + exp_pos)

    def advantage(self, features: tuple[float, ...]) -> float:
        return self._probability(features, 1) - self._probability(features, 0)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "LinearResponseModel":
        return cls(
            intercept=float(payload["intercept"]),
            coefficients=tuple(float(value) for value in payload["coefficients"]),
            decision_threshold=float(payload["decision_threshold"]),
        )


class SingleInterventionController:
    def __init__(
        self,
        fallback_module: Any,
        *,
        max_score_gap: float,
        mode: str = "randomized",
        model: LinearResponseModel | None = None,
    ) -> None:
        if mode not in ("randomized", "trained", "exact"):
            raise ValueError(f"unknown Route-A mode: {mode}")
        self.fallback_module = fallback_module
        self.max_score_gap = float(max_score_gap)
        self.mode = mode
        self.model = model
        self.reset()

    def reset(self) -> None:
        self.target_bucket: str | None = None
        self.assigned_treatment = 0
        self.opportunity_consumed = False
        self.intervened = False
        self.record: dict[str, Any] | None = None
        self.internal_errors: list[str] = []
        self.latencies_s: list[float] = []

    def configure_randomized(self, bucket: str, treatment: int) -> None:
        if bucket not in TURN_BUCKETS or treatment not in (0, 1):
            raise ValueError("invalid randomized Route-A assignment")
        self.target_bucket = bucket
        self.assigned_treatment = int(treatment)

    def choose(
        self,
        state: dict[str, Any],
        options: list[dict[str, Any]],
        history: list[dict[str, Any]],
        exact_action: list[int],
    ) -> list[int]:
        started = time.perf_counter()
        try:
            if self.mode == "exact" or self.opportunity_consumed:
                return list(exact_action)
            proposal = propose_safe_alternative(
                self.fallback_module,
                state,
                options,
                history,
                exact_action,
                self.max_score_gap,
            )
            if proposal is None:
                return list(exact_action)
            if self.mode == "randomized":
                if proposal.bucket != self.target_bucket:
                    return list(exact_action)
                treatment = self.assigned_treatment
                advantage = None
                self.opportunity_consumed = True
            else:
                if self.model is None:
                    raise RuntimeError("trained Route-A controller missing model")
                advantage = self.model.advantage(proposal.features)
                treatment = int(advantage >= self.model.decision_threshold)
                if not treatment:
                    return list(exact_action)
                self.opportunity_consumed = True
            self.intervened = bool(treatment)
            self.record = {
                **proposal.as_dict(),
                "treatment": int(treatment),
                "mode": self.mode,
                "predicted_advantage": advantage,
            }
            return (
                list(proposal.alternative_action)
                if treatment
                else list(proposal.exact_action)
            )
        except Exception as exc:  # Runtime policy must fail closed to exact.
            if len(self.internal_errors) < 10:
                self.internal_errors.append(f"{type(exc).__name__}: {exc}")
            return list(exact_action)
        finally:
            self.latencies_s.append(time.perf_counter() - started)


class RouteAAgent(CandidateAgent):
    """An isolated exact-v22 instance with one process-local Route-A hook."""

    def __init__(
        self,
        source: pathlib.Path,
        *,
        max_score_gap: float,
        mode: str = "randomized",
        model: LinearResponseModel | None = None,
    ) -> None:
        super().__init__(source)
        main = self._private_modules.get(MAIN_MODULE)
        fallback = self._private_modules.get(FALLBACK_MODULE)
        if main is None or fallback is None:
            raise SystemExit("Route-A requires the modular exact-v22 policy")
        self.controller = SingleInterventionController(
            fallback,
            max_score_gap=max_score_gap,
            mode=mode,
            model=model,
        )
        original_choose = main.choose
        controller = self.controller

        def routeA_choose(
            state: dict[str, Any],
            options: list[dict[str, Any]],
            history: list[dict[str, Any]],
            memory: Any = None,
        ) -> list[int]:
            exact = original_choose(state, options, history, memory)
            return controller.choose(state, options, history, list(exact))

        main.choose = routeA_choose

    def __call__(self, obs: dict[str, Any]) -> list[int]:
        if obs.get("select") is None:
            self.controller.reset()
        return super().__call__(obs)

    def configure_randomized_episode(self, bucket: str, treatment: int) -> None:
        self.controller.configure_randomized(bucket, treatment)

    def episode_record(self) -> dict[str, Any] | None:
        return None if self.controller.record is None else dict(self.controller.record)
