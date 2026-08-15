#!/usr/bin/env python3
"""Randomized trigger-level audit for two near-miss v22 tactical guards.

This is a discovery experiment, not a promotion gate.  Each episode is
assigned one of four seat-balanced factorial arms before the native shuffle:

* both target guards apply (exact-v22 behavior),
* only the Boss guard applies,
* only the Impidimp-preservation guard applies,
* both target guards are skipped and fall through to normal v22.

The original guard functions are still evaluated in every arm, so the report
can count actual trigger opportunities and attach the terminal outcome to the
state that caused the decision.  A signal requires sufficient opportunity
counts and same-direction evidence in at least two opponent legs.  Even a
signal cannot be submitted directly; it only authorizes a deterministic
contextual residual followed by the normal n>=256 exact-v22 gate.
"""

from __future__ import annotations

import argparse
import hashlib
import multiprocessing as mp
import pathlib
import random
import statistics
import sys
import time
from dataclasses import dataclass
from functools import wraps
from typing import Any


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiments import arena_runner as arena  # noqa: E402
from scripts.candidate_h2h import CandidateAgent, sha256  # noqa: E402
from scripts.safe_json_output import reserve_json_output  # noqa: E402


V22 = ROOT / "candidates" / "grim_v22_final"
MANUAL_GUARDS_MODULE = "policies.v22.manual_guards"
TARGETS = (
    "boss_damaged_basic_stall_guard",
    "energized_impidimp_preservation_guard",
)


@dataclass(frozen=True)
class Leg:
    name: str
    path: str
    games: int


def parse_leg(raw: str) -> Leg:
    """Parse NAME=PATH,GAMES."""
    if "=" not in raw:
        raise argparse.ArgumentTypeError("leg must be NAME=PATH,GAMES")
    name, rest = raw.split("=", 1)
    try:
        path_raw, games_raw = rest.rsplit(",", 1)
        games = int(games_raw)
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError("leg must be NAME=PATH,GAMES") from exc
    path = pathlib.Path(path_raw).expanduser()
    if not path.is_absolute():
        path = ROOT / path
    if not name.strip() or not path.exists() or games <= 0:
        raise argparse.ArgumentTypeError(f"invalid leg: {raw}")
    return Leg(name.strip(), str(path.resolve()), games)


def _card_id(card: Any) -> int:
    if not isinstance(card, dict):
        return 0
    try:
        return int(card.get("id", 0) or 0)
    except (TypeError, ValueError):
        return 0


def _energy_count(card: Any) -> int:
    if not isinstance(card, dict):
        return 0
    cards = card.get("energyCards") or card.get("energies") or []
    return len(cards)


def _card_snapshot(card: Any) -> dict[str, int]:
    if not isinstance(card, dict):
        return {"id": 0, "hp": 0, "max_hp": 0, "energy": 0}
    return {
        "id": _card_id(card),
        "hp": int(card.get("hp", 0) or 0),
        "max_hp": int(card.get("maxHp", 0) or 0),
        "energy": _energy_count(card),
    }


def _state_snapshot(obs: dict[str, Any]) -> dict[str, Any]:
    select = obs.get("select") or {}
    current = obs.get("current") or {}
    players = current.get("players") or []
    try:
        your = int(current.get("yourIndex", 0) or 0)
    except (TypeError, ValueError):
        your = 0
    me = players[your] if len(players) == 2 and your in (0, 1) else {}
    opponent = players[1 - your] if len(players) == 2 and your in (0, 1) else {}
    return {
        "turn": int(current.get("turn", 0) or 0),
        "context": int(select.get("context", -1) if select.get("context") is not None else -1),
        "effect_id": _card_id(select.get("effect")),
        "me_prizes": len(me.get("prize") or []),
        "opponent_prizes": len(opponent.get("prize") or []),
        "me_active": [_card_snapshot(card) for card in (me.get("active") or [])],
        "me_bench": [_card_snapshot(card) for card in (me.get("bench") or [])],
        "opponent_active": [
            _card_snapshot(card) for card in (opponent.get("active") or [])
        ],
        "opponent_bench": [
            _card_snapshot(card) for card in (opponent.get("bench") or [])
        ],
    }


def _guard_name(fn: Any) -> str:
    return str(fn.__module__).rsplit(".", 1)[-1]


def _arm_assignment(seed: int, game: int) -> int:
    """Give every arm one game in each candidate seat per block of eight."""
    block, position = divmod(game, 8)
    seat = position % 2
    seat_position = position // 2
    arms = [0, 1, 2, 3]
    random.Random(seed + block * 1_000_003 + seat * 100_000_007).shuffle(arms)
    return arms[seat_position]


def _arm_flags(arm: int) -> dict[str, bool]:
    return {
        TARGETS[0]: bool(arm & 1),
        TARGETS[1]: bool(arm & 2),
    }


def _arm_name(arm: int) -> str:
    return {
        0: "both_skip",
        1: "boss_apply_imp_skip",
        2: "boss_skip_imp_apply",
        3: "both_apply",
    }[arm]


class FactorialGuardAgent(CandidateAgent):
    def __init__(self, source: pathlib.Path):
        super().__init__(source)
        self.game = -1
        self.arm = 3
        self.flags = _arm_flags(self.arm)
        self.events: list[dict[str, Any]] = []
        self._pending: list[int] = []

        manual = self._private_modules.get(MANUAL_GUARDS_MODULE)
        if manual is None:
            raise SystemExit("candidate is not the expected modular v22 policy")
        found = {_guard_name(fn) for fn in manual.GUARDS if _guard_name(fn) in TARGETS}
        if found != set(TARGETS):
            raise SystemExit(f"target guard mismatch: found={sorted(found)}")
        manual.GUARDS = tuple(self._wrap(fn) for fn in manual.GUARDS)

    def _wrap(self, fn: Any):
        name = _guard_name(fn)
        if name not in TARGETS:
            return fn

        @wraps(fn)
        def wrapped(obs: dict[str, Any]):
            action, semantics = fn(obs)
            if action is None:
                return action, semantics
            event = {
                "game": self.game,
                "guard": name,
                "apply": self.flags[name],
                "guard_action": list(action),
                "state": _state_snapshot(obs),
            }
            self.events.append(event)
            self._pending.append(len(self.events) - 1)
            return (action, semantics) if self.flags[name] else (None, semantics)

        return wrapped

    def begin_episode(self, game: int, arm: int) -> list[int]:
        self.game = game
        self.arm = arm
        self.flags = _arm_flags(arm)
        self.events = []
        self._pending = []
        return super().deck()

    def __call__(self, obs: dict[str, Any]) -> list[int]:
        self._pending = []
        action = super().__call__(obs)
        for index in self._pending:
            self.events[index]["final_action"] = list(action)
        self._pending = []
        return action


def _run_chunk(task: dict[str, Any]) -> list[dict[str, Any]]:
    source = pathlib.Path(task["source"])
    opponent_path = pathlib.Path(task["opponent_path"])
    leg = str(task["leg"])
    games = int(task["games"])
    global_offset = int(task["global_offset"])
    leg_offset = int(task["leg_offset"])
    arm_seed = int(task["arm_seed"])
    python_seed = int(task["python_seed"])

    candidate = FactorialGuardAgent(source)
    opponent = CandidateAgent(opponent_path)
    candidate_deck = candidate.deck()
    opponent_deck = opponent.deck()
    records: list[dict[str, Any]] = []

    for local_game in range(games):
        leg_game = leg_offset + local_game
        game = global_offset + leg_game
        arm = _arm_assignment(arm_seed, leg_game)
        if candidate.begin_episode(game, arm) != candidate_deck:
            raise SystemExit("candidate deck changed between episodes")
        if opponent.deck() != opponent_deck:
            raise SystemExit("opponent deck changed between episodes")
        swap = leg_game % 2 == 1
        agents = (candidate, opponent) if not swap else (opponent, candidate)
        decks = (
            (candidate_deck, opponent_deck)
            if not swap
            else (opponent_deck, candidate_deck)
        )
        random.seed(python_seed + game)
        result = arena.play(agents, decks)
        candidate_position = 1 if swap else 0
        winner = int(result["winner"])
        outcome = None if winner < 0 else int(winner == candidate_position)
        events = []
        for event in candidate.events:
            copied = dict(event)
            copied["outcome"] = outcome
            events.append(copied)
        records.append({
            "leg": leg,
            "game": game,
            "leg_game": leg_game,
            "arm": arm,
            "arm_name": _arm_name(arm),
            "flags": _arm_flags(arm),
            "candidate_seat": candidate_position,
            "winner": winner,
            "outcome": outcome,
            "steps": int(result["steps"]),
            "candidate_fault": result.get("fault") == candidate_position,
            "opponent_fault": (
                result.get("fault") is not None
                and result.get("fault") != candidate_position
            ),
            "error": result.get("err"),
            "events": events,
        })
    return records


def _split_tasks(
    source: pathlib.Path,
    legs: list[Leg],
    workers: int,
    seed: int,
) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    global_offset = 0
    for leg_index, leg in enumerate(legs):
        chunks = min(workers, leg.games)
        base, extra = divmod(leg.games, chunks)
        leg_offset = 0
        for chunk in range(chunks):
            games = base + int(chunk < extra)
            tasks.append({
                "source": str(source),
                "opponent_path": leg.path,
                "leg": leg.name,
                "games": games,
                "global_offset": global_offset,
                "leg_offset": leg_offset,
                "arm_seed": seed + leg_index * 10_000_019,
                "python_seed": seed + leg_index * 100_000_007 + chunk * 1_000_003,
            })
            leg_offset += games
        global_offset += leg.games
    return tasks


def _rate(records: list[dict[str, Any]]) -> dict[str, Any]:
    wins = sum(record["outcome"] == 1 for record in records)
    losses = sum(record["outcome"] == 0 for record in records)
    draws = sum(record["outcome"] is None for record in records)
    decisive = wins + losses
    return {
        "games": len(records),
        "wins": wins,
        "losses": losses,
        "draws": draws,
        "win_rate": round(wins / decisive, 6) if decisive else None,
    }


def _first_guard_event(record: dict[str, Any], guard: str) -> dict[str, Any] | None:
    return next((event for event in record["events"] if event["guard"] == guard), None)


def _summarize(
    records: list[dict[str, Any]],
    *,
    min_opportunities_per_arm: int,
    min_skip_advantage: float,
    min_consistent_legs: int,
    min_leg_opportunities_per_arm: int,
) -> dict[str, Any]:
    arms = {
        _arm_name(arm): _rate([record for record in records if record["arm"] == arm])
        for arm in range(4)
    }
    legs = {
        leg: _rate([record for record in records if record["leg"] == leg])
        for leg in sorted({record["leg"] for record in records})
    }
    arms_by_seat = {
        _arm_name(arm): {
            "seat_0": sum(
                record["arm"] == arm and record["candidate_seat"] == 0
                for record in records
            ),
            "seat_1": sum(
                record["arm"] == arm and record["candidate_seat"] == 1
                for record in records
            ),
        }
        for arm in range(4)
    }
    guard_summaries: dict[str, Any] = {}
    discoveries: list[str] = []

    for guard in TARGETS:
        enabled = [record for record in records if record["flags"][guard]]
        skipped = [record for record in records if not record["flags"][guard]]
        enabled_itt = _rate(enabled)
        skipped_itt = _rate(skipped)

        opportunity_records = [
            record for record in records if _first_guard_event(record, guard) is not None
        ]
        opportunity_apply = [
            record for record in opportunity_records if record["flags"][guard]
        ]
        opportunity_skip = [
            record for record in opportunity_records if not record["flags"][guard]
        ]
        apply_rate = _rate(opportunity_apply)
        skip_rate = _rate(opportunity_skip)
        apply_wr = float(apply_rate["win_rate"] or 0.0)
        skip_wr = float(skip_rate["win_rate"] or 0.0)
        skip_advantage = skip_wr - apply_wr

        per_leg: dict[str, Any] = {}
        consistent_legs = 0
        eligible_legs = 0
        for leg in sorted({record["leg"] for record in records}):
            leg_records = [record for record in opportunity_records if record["leg"] == leg]
            leg_apply = _rate([record for record in leg_records if record["flags"][guard]])
            leg_skip = _rate([record for record in leg_records if not record["flags"][guard]])
            leg_apply_wr = float(leg_apply["win_rate"] or 0.0)
            leg_skip_wr = float(leg_skip["win_rate"] or 0.0)
            eligible = (
                leg_apply["games"] >= min_leg_opportunities_per_arm
                and leg_skip["games"] >= min_leg_opportunities_per_arm
            )
            positive = eligible and leg_skip_wr > leg_apply_wr
            eligible_legs += int(eligible)
            consistent_legs += int(positive)
            per_leg[leg] = {
                "apply": leg_apply,
                "skip": leg_skip,
                "skip_minus_apply": round(leg_skip_wr - leg_apply_wr, 6),
                "eligible": eligible,
                "positive": positive,
            }

        eligible_counts = (
            apply_rate["games"] >= min_opportunities_per_arm
            and skip_rate["games"] >= min_opportunities_per_arm
        )
        gate_evaluable = (
            eligible_counts and eligible_legs >= min_consistent_legs
        )
        signal = (
            gate_evaluable
            and skip_advantage >= min_skip_advantage
            and consistent_legs >= min_consistent_legs
        )
        gate_verdict = (
            "SIGNAL"
            if signal
            else "NO_SIGNAL"
            if gate_evaluable
            else "INSUFFICIENT_OPPORTUNITIES"
        )
        if signal:
            discoveries.append(guard)
        guard_summaries[guard] = {
            "assigned_itt": {
                "apply": enabled_itt,
                "skip": skipped_itt,
                "skip_minus_apply": round(
                    float(skipped_itt["win_rate"] or 0.0)
                    - float(enabled_itt["win_rate"] or 0.0),
                    6,
                ),
            },
            "opportunity_games": len(opportunity_records),
            "trigger_events": sum(
                len([event for event in record["events"] if event["guard"] == guard])
                for record in records
            ),
            "opportunity_outcome": {
                "apply": apply_rate,
                "skip": skip_rate,
                "skip_minus_apply": round(skip_advantage, 6),
            },
            "consistent_positive_legs": consistent_legs,
            "eligible_legs": eligible_legs,
            "gate_evaluable": gate_evaluable,
            "per_leg": per_leg,
            "signal": signal,
            "verdict": gate_verdict,
        }

    steps = [record["steps"] for record in records]
    overall_verdict = (
        "SIGNAL"
        if discoveries
        else "INSUFFICIENT_OPPORTUNITIES"
        if any(
            row["verdict"] == "INSUFFICIENT_OPPORTUNITIES"
            for row in guard_summaries.values()
        )
        else "NO_SIGNAL"
    )
    return {
        "overall": _rate(records),
        "candidate_faults": sum(bool(record["candidate_fault"]) for record in records),
        "opponent_faults": sum(bool(record["opponent_fault"]) for record in records),
        "avg_steps": round(statistics.mean(steps), 2) if steps else 0.0,
        "arms": arms,
        "arms_by_candidate_seat": arms_by_seat,
        "legs": legs,
        "guards": guard_summaries,
        "discovery_gate": {
            "min_opportunities_per_arm": min_opportunities_per_arm,
            "min_skip_advantage": min_skip_advantage,
            "min_consistent_legs": min_consistent_legs,
            "min_leg_opportunities_per_arm": min_leg_opportunities_per_arm,
        },
        "discoveries": discoveries,
        "verdict": overall_verdict,
    }


def _tree_sha256(root: pathlib.Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(
        path for path in root.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    ):
        digest.update(str(path.relative_to(root)).encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default=str(V22))
    parser.add_argument("--leg", action="append", type=parse_leg)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--seed", type=int, default=2026081512)
    parser.add_argument("--min-opportunities-per-arm", type=int, default=30)
    parser.add_argument("--min-skip-advantage", type=float, default=0.10)
    parser.add_argument("--min-consistent-legs", type=int, default=2)
    parser.add_argument("--min-leg-opportunities-per-arm", type=int, default=8)
    parser.add_argument("--out", required=True)
    parser.add_argument("--overwrite-output", action="store_true")
    args = parser.parse_args()

    source = pathlib.Path(args.source).resolve()
    if not source.is_dir():
        raise SystemExit(f"source candidate missing: {source}")
    legs = args.leg or [Leg("v22", str(source), 128)]
    if args.workers <= 0:
        raise SystemExit("--workers must be positive")
    if len({leg.name for leg in legs}) != len(legs):
        raise SystemExit("--leg names must be unique")
    if any(leg.games % 8 for leg in legs):
        raise SystemExit(
            "each leg game count must be divisible by 8 for exact arm/seat balance"
        )
    output = pathlib.Path(args.out).resolve()
    reservation = reserve_json_output(output, overwrite=args.overwrite_output)

    tasks = _split_tasks(source, legs, args.workers, args.seed)
    print(
        f"[factorial] games={sum(leg.games for leg in legs)} "
        f"legs={len(legs)} chunks={len(tasks)} workers={args.workers}",
        flush=True,
    )
    started = time.time()
    if args.workers == 1:
        chunks = [_run_chunk(task) for task in tasks]
    else:
        context = mp.get_context("spawn")
        with context.Pool(processes=args.workers) as pool:
            chunks = list(pool.imap_unordered(_run_chunk, tasks, chunksize=1))
    records = sorted(
        [record for chunk in chunks for record in chunk],
        key=lambda record: (record["leg"], record["game"]),
    )
    summary = _summarize(
        records,
        min_opportunities_per_arm=args.min_opportunities_per_arm,
        min_skip_advantage=args.min_skip_advantage,
        min_consistent_legs=args.min_consistent_legs,
        min_leg_opportunities_per_arm=args.min_leg_opportunities_per_arm,
    )
    report = {
        "created_unix": time.time(),
        "method": "balanced-randomized-2x2-trigger-factorial-by-seat-v2",
        "purpose": "contextual residual discovery only; never a promotion result",
        "source": str(source),
        "source_tree_sha256": _tree_sha256(source),
        "source_main_sha256": sha256(source / "main.py"),
        "source_deck_sha256": sha256(source / "deck.csv"),
        "targets": list(TARGETS),
        "legs": [leg.__dict__ for leg in legs],
        "seed": args.seed,
        "seed_scope": "factorial/Python only; native shuffle is unseeded",
        "episode_reset": "select-none-before-every-game-v1",
        "output_protocol": "exclusive-lock+atomic-replace-v1",
        "summary": summary,
        "records": records,
        "elapsed_s": round(time.time() - started, 3),
    }
    reservation.write(report)
    print(
        f"[done] verdict={summary['verdict']} discoveries={summary['discoveries']} "
        f"faults={summary['candidate_faults']} elapsed={report['elapsed_s']}s "
        f"-> {output}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
