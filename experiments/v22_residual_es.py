#!/usr/bin/env python3
"""Conservative on-policy residual search around the frozen Grim v22 agent.

This is episodic black-box reinforcement learning (an evolutionary strategy),
not replay imitation:

* a genome disables a small set of v22 residual guards/planner layers;
* the lower, already validated v22 policy remains the fallback;
* every genome generates its own games against a frozen opponent population;
* terminal wins/losses are the only optimization reward;
* a separate confirmation batch is used after population selection.

The script never edits or packages the incumbent.  It writes a JSON report
whose winning genome, if any, must still pass the larger isolated gate before
it can be materialized as a challenger.

Example smoke run::

  /opt/homebrew/bin/python3 -B experiments/v22_residual_es.py \
    --singletons 0 --random-genomes 1 --top-k 1 \
    --leg v22=candidates/grim_v22_final,2,1.0 \
    --out /private/tmp/v22_es_smoke.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import multiprocessing as mp
import pathlib
import random
import sys
import time
from dataclasses import dataclass
from typing import Any


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.candidate_h2h import (  # noqa: E402
    CandidateAgent,
    run_match,
    sha256,
)
from scripts.safe_json_output import reserve_json_output  # noqa: E402


V22 = ROOT / "candidates" / "grim_v22_final"
MANUAL_GUARDS_MODULE = "policies.v22.manual_guards"
HIERARCHICAL_MODULE = "policies.v22.hierarchical_policy"
LAYER_HOOKS = {
    "layer:processing_queue": "plan_main_action",
    "layer:turn_dag": "plan_turn_dag",
    "layer:deadline_scheduler": "plan_lexicographic_deadline",
    "layer:continuity_scheduler": "plan_continuity",
}


def _return_none(*_args, **_kwargs):
    return None


def _tree_sha256(root: pathlib.Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file() and "__pycache__" not in p.parts):
        digest.update(str(path.relative_to(root)).encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _guard_feature(fn: Any) -> str:
    return "guard:" + str(fn.__module__).rsplit(".", 1)[-1]


class ResidualV22Agent(CandidateAgent):
    """A v22 instance with a deterministic, process-local residual genome."""

    def __init__(self, source: pathlib.Path, disabled: tuple[str, ...]):
        super().__init__(source)
        disabled_set = set(disabled)
        manual = self._private_modules.get(MANUAL_GUARDS_MODULE)
        hierarchical = self._private_modules.get(HIERARCHICAL_MODULE)
        if manual is None or hierarchical is None:
            raise SystemExit("candidate is not the expected modular v22 policy")

        known_guards = {_guard_feature(fn) for fn in manual.GUARDS}
        unknown = disabled_set - known_guards - set(LAYER_HOOKS)
        if unknown:
            raise SystemExit(f"unknown residual features: {sorted(unknown)}")

        manual.GUARDS = tuple(
            fn for fn in manual.GUARDS if _guard_feature(fn) not in disabled_set
        )
        for feature, hook in LAYER_HOOKS.items():
            if feature in disabled_set:
                setattr(hierarchical, hook, _return_none)


@dataclass(frozen=True)
class Leg:
    name: str
    path: str
    games: int
    weight: float


def parse_leg(raw: str) -> Leg:
    """Parse NAME=PATH,GAMES,WEIGHT."""
    if "=" not in raw:
        raise argparse.ArgumentTypeError("leg must be NAME=PATH,GAMES,WEIGHT")
    name, rest = raw.split("=", 1)
    try:
        path_raw, games_raw, weight_raw = rest.rsplit(",", 2)
        games = int(games_raw)
        weight = float(weight_raw)
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError(
            "leg must be NAME=PATH,GAMES,WEIGHT"
        ) from exc
    path = pathlib.Path(path_raw).expanduser()
    if not path.is_absolute():
        path = ROOT / path
    if not name.strip() or not path.exists() or games <= 0 or weight <= 0:
        raise argparse.ArgumentTypeError(
            f"invalid leg (name/path/games/weight): {raw}"
        )
    return Leg(name.strip(), str(path.resolve()), games, weight)


def discover_features(source: pathlib.Path) -> tuple[str, ...]:
    agent = CandidateAgent(source)
    manual = agent._private_modules.get(MANUAL_GUARDS_MODULE)
    if manual is None:
        raise SystemExit("manual guard module missing from v22")
    guards = tuple(_guard_feature(fn) for fn in manual.GUARDS)
    return guards + tuple(LAYER_HOOKS)


def genome_id(disabled: tuple[str, ...]) -> str:
    if not disabled:
        return "incumbent"
    payload = "\n".join(disabled).encode("utf-8")
    return "g-" + hashlib.sha256(payload).hexdigest()[:10]


def generate_genomes(
    features: tuple[str, ...],
    *,
    singletons: bool,
    random_genomes: int,
    max_disabled: int,
    seed: int,
    fixed_genomes: tuple[tuple[str, ...], ...] = (),
) -> list[tuple[str, ...]]:
    genomes: list[tuple[str, ...]] = [()]
    seen: set[tuple[str, ...]] = {()}
    genome: tuple[str, ...]
    if singletons:
        for feature in features:
            genome = (feature,)
            genomes.append(genome)
            seen.add(genome)

    rng = random.Random(seed)
    attempts = 0
    while len(genomes) < 1 + (len(features) if singletons else 0) + random_genomes:
        attempts += 1
        if attempts > max(1000, random_genomes * 100):
            break
        count = rng.randint(2 if max_disabled >= 2 else 1, max_disabled)
        genome = tuple(sorted(rng.sample(features, min(count, len(features)))))
        if genome not in seen:
            seen.add(genome)
            genomes.append(genome)
    for genome in fixed_genomes:
        normalized = tuple(sorted(genome))
        if normalized not in seen:
            seen.add(normalized)
            genomes.append(normalized)
    return genomes


def _evaluate_one(task: dict[str, Any]) -> dict[str, Any]:
    source = pathlib.Path(task["source"])
    disabled = tuple(task["disabled"])
    legs = [Leg(**leg) for leg in task["legs"]]
    multiplier = int(task["multiplier"])
    seed = int(task["seed"])

    candidate = ResidualV22Agent(source, disabled)
    results: list[dict[str, Any]] = []
    started = time.time()
    for index, leg in enumerate(legs):
        opponent = CandidateAgent(pathlib.Path(leg.path))
        result = run_match(
            candidate,
            opponent,
            leg.games * multiplier,
            seed + index * 100_000,
        )
        result.update({"opponent": leg.name, "weight": leg.weight})
        results.append(result)

    weight_total = sum(leg.weight for leg in legs)
    weighted_wr = sum(
        leg.weight * float(result["win_rate"] or 0.0)
        for leg, result in zip(legs, results)
    ) / weight_total
    return {
        "genome": genome_id(disabled),
        "disabled": list(disabled),
        "weighted_wr": round(weighted_wr, 6),
        "faults": sum(
            int(result["candidate_faults"]) for result in results
        ),
        "games": sum(int(result["games"]) for result in results),
        "elapsed_s": round(time.time() - started, 3),
        "results": results,
    }


def evaluate_population(
    genomes: list[tuple[str, ...]],
    source: pathlib.Path,
    legs: list[Leg],
    *,
    multiplier: int,
    seed: int,
    workers: int,
) -> list[dict[str, Any]]:
    tasks = [
        {
            "source": str(source),
            "disabled": list(genome),
            "legs": [leg.__dict__ for leg in legs],
            "multiplier": multiplier,
            "seed": seed + index * 1_000_000,
        }
        for index, genome in enumerate(genomes)
    ]
    if workers == 1:
        results = [_evaluate_one(task) for task in tasks]
    else:
        context = mp.get_context("spawn")
        with context.Pool(processes=workers) as pool:
            results = list(pool.imap_unordered(_evaluate_one, tasks, chunksize=1))
    return sorted(results, key=lambda row: (-row["weighted_wr"], row["genome"]))


def _by_leg(result: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {row["opponent"]: row for row in result["results"]}


def promotion_assessment(
    result: dict[str, Any],
    baseline: dict[str, Any],
    *,
    min_delta: float,
    max_leg_drop: float,
    min_v22_wr: float,
    min_v22_games: int,
) -> dict[str, Any]:
    result_legs = _by_leg(result)
    baseline_legs = _by_leg(baseline)
    deltas: dict[str, float] = {}
    weighted_delta = 0.0
    total_weight = 0.0
    for name, row in result_legs.items():
        base = baseline_legs[name]
        delta = float(row["win_rate"] or 0.0) - float(base["win_rate"] or 0.0)
        deltas[name] = round(delta, 6)
        weighted_delta += float(row["weight"]) * delta
        total_weight += float(row["weight"])
    weighted_delta /= total_weight

    v22 = result_legs.get("v22")
    enough_v22 = bool(v22 and int(v22["games"]) >= min_v22_games)
    v22_ok = bool(v22 and float(v22["win_rate"] or 0.0) >= min_v22_wr)
    leg_floor_ok = all(delta >= -max_leg_drop for delta in deltas.values())
    passed = bool(
        result["genome"] != "incumbent"
        and result["faults"] == 0
        and enough_v22
        and v22_ok
        and weighted_delta >= min_delta
        and leg_floor_ok
    )
    return {
        "passed": passed,
        "eligible_sample_size": enough_v22,
        "v22_ok": v22_ok,
        "leg_floor_ok": leg_floor_ok,
        "weighted_delta": round(weighted_delta, 6),
        "per_leg_delta": deltas,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default=str(V22))
    parser.add_argument("--leg", action="append", type=parse_leg)
    parser.add_argument("--singletons", type=int, choices=(0, 1), default=1)
    parser.add_argument("--random-genomes", type=int, default=16)
    parser.add_argument(
        "--fixed-genome",
        action="append",
        default=[],
        help="comma-separated residual features to include verbatim; repeatable",
    )
    parser.add_argument("--max-disabled", type=int, default=3)
    parser.add_argument("--top-k", type=int, default=4)
    parser.add_argument("--confirm-multiplier", type=int, default=4)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--seed", type=int, default=2026081509)
    parser.add_argument("--min-delta", type=float, default=0.03)
    parser.add_argument("--max-leg-drop", type=float, default=0.03)
    parser.add_argument("--min-v22-wr", type=float, default=0.53)
    parser.add_argument("--min-v22-games", type=int, default=256)
    parser.add_argument("--out", required=True)
    parser.add_argument(
        "--overwrite-output",
        action="store_true",
        help="explicitly replace an existing report; concurrent writers remain locked out",
    )
    args = parser.parse_args()

    output = pathlib.Path(args.out).resolve()
    output_reservation = reserve_json_output(
        output,
        overwrite=args.overwrite_output,
    )

    source = pathlib.Path(args.source).resolve()
    if not source.is_dir():
        raise SystemExit(f"source candidate missing: {source}")
    legs = args.leg or [Leg("v22", str(source), 16, 1.0)]
    if not any(leg.name == "v22" for leg in legs):
        raise SystemExit("one opponent leg must be named 'v22'")
    if args.max_disabled <= 0 or args.top_k <= 0 or args.confirm_multiplier <= 0:
        raise SystemExit("max-disabled/top-k/confirm-multiplier must be positive")

    features = discover_features(source)
    fixed_genomes = tuple(
        tuple(feature.strip() for feature in raw.split(",") if feature.strip())
        for raw in args.fixed_genome
    )
    unknown_fixed = sorted({
        feature
        for genome in fixed_genomes
        for feature in genome
        if feature not in features
    })
    if unknown_fixed:
        raise SystemExit(f"unknown --fixed-genome features: {unknown_fixed}")
    genomes = generate_genomes(
        features,
        singletons=bool(args.singletons),
        random_genomes=args.random_genomes,
        max_disabled=min(args.max_disabled, len(features)),
        seed=args.seed,
        fixed_genomes=fixed_genomes,
    )
    print(
        f"[screen] genomes={len(genomes)} legs={len(legs)} workers={args.workers}",
        flush=True,
    )
    started = time.time()
    screen = evaluate_population(
        genomes,
        source,
        legs,
        multiplier=1,
        seed=args.seed,
        workers=args.workers,
    )
    for rank, row in enumerate(screen[: max(args.top_k + 1, 5)], 1):
        print(
            f"  {rank:>2}. {row['genome']} wr={row['weighted_wr']:.3f} "
            f"faults={row['faults']} disabled={row['disabled']}",
            flush=True,
        )

    selected = [row for row in screen if row["genome"] != "incumbent"][: args.top_k]
    selected_genomes = [()] + [tuple(row["disabled"]) for row in selected]
    print(
        f"[confirm] genomes={len(selected_genomes)} multiplier={args.confirm_multiplier}",
        flush=True,
    )
    confirm = evaluate_population(
        selected_genomes,
        source,
        legs,
        multiplier=args.confirm_multiplier,
        seed=args.seed + 900_000_000,
        workers=min(args.workers, len(selected_genomes)),
    )
    baseline = next(row for row in confirm if row["genome"] == "incumbent")
    assessments = {
        row["genome"]: promotion_assessment(
            row,
            baseline,
            min_delta=args.min_delta,
            max_leg_drop=args.max_leg_drop,
            min_v22_wr=args.min_v22_wr,
            min_v22_games=args.min_v22_games,
        )
        for row in confirm
    }
    passing = [
        row for row in confirm if assessments[row["genome"]]["passed"]
    ]
    winner = passing[0] if passing else None

    report = {
        "created_unix": time.time(),
        "method": "episodic-black-box-residual-es-v1",
        "reward": "terminal win/loss from locally generated on-policy games",
        "replay_training": False,
        "source": str(source),
        "source_tree_sha256": _tree_sha256(source),
        "source_main_sha256": sha256(source / "main.py"),
        "source_deck_sha256": sha256(source / "deck.csv"),
        "runner": str(ROOT / "scripts" / "candidate_h2h.py"),
        "runner_sha256": sha256(ROOT / "scripts" / "candidate_h2h.py"),
        "module_isolation": "per-candidate-sys-modules-v1",
        "episode_reset": "select-none-before-every-game-v1",
        "native_shuffle_seed": "unavailable; stages are independent stochastic batches",
        "output_protocol": "exclusive-lock+atomic-replace-v1",
        "features": list(features),
        "legs": [leg.__dict__ for leg in legs],
        "search": {
            "singletons": bool(args.singletons),
            "random_genomes": args.random_genomes,
            "fixed_genomes": [list(genome) for genome in fixed_genomes],
            "max_disabled": args.max_disabled,
            "population_size": len(genomes),
            "top_k": args.top_k,
            "confirm_multiplier": args.confirm_multiplier,
            "seed": args.seed,
        },
        "promotion_gate": {
            "min_weighted_delta": args.min_delta,
            "max_per_leg_drop": args.max_leg_drop,
            "min_v22_wr": args.min_v22_wr,
            "min_v22_games": args.min_v22_games,
            "zero_candidate_faults": True,
        },
        "screen": screen,
        "confirmation": confirm,
        "assessments": assessments,
        "winner": None if winner is None else {
            "genome": winner["genome"],
            "disabled": winner["disabled"],
            "weighted_wr": winner["weighted_wr"],
            "assessment": assessments[winner["genome"]],
        },
        "elapsed_s": round(time.time() - started, 3),
    }
    output_reservation.write(report)
    print(f"[done] winner={report['winner']} elapsed={report['elapsed_s']}s -> {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
