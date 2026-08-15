#!/usr/bin/env python3
"""Run candidate-directory H2H checks with the official local engine.

Unlike ``experiments/arena_runner.py``, this runner does not copy the dirty
repository root as the tested strategy.  Every agent is loaded and called with
its own directory as cwd, matching Kaggle's relative-file behavior.

Example:

  python3 scripts/candidate_h2h.py \
    --candidate /private/tmp/router \
    --opponent baseline=submission_baseline \
    --n 64 --out reports/router_h2h.json

If ``--opponent`` is omitted, the immutable exact Grim v22 submission is used.
This safe default follows the user's "strongest submission is the baseline"
rule and prevents the now-weaker retreat/config-A line or a public-notebook
score from silently becoming the acceptance gate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import random
import statistics
import sys
import time
from contextlib import contextmanager
from typing import Any


ROOT = pathlib.Path(__file__).resolve().parents[1]
ENGINE = ROOT / "inference/comp_data/sample_submission/sample_submission"
BASELINE = ROOT / "candidates" / "grim_v22_final"
BASELINE_MAIN_SHA256 = "d80d33c570ba5dff445f3be60bcbd038598bd418eeb44c1120f3fbea893cba98"
BASELINE_DECK_SHA256 = "92b92bac9f9163ecff933b3dc39294d2cc154c8684f3c8497877661419ebc59d"
BASELINE_TREE_SHA256 = "0319fee37419983ad7137c1db9d1ac7d67024cc692eb495d73e6f46fedd12ecc"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ENGINE))

from experiments import arena_runner as arena  # noqa: E402
from scripts.safe_json_output import reserve_json_output  # noqa: E402


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def tree_sha256(root: pathlib.Path) -> str:
    """Hash every runtime file while ignoring interpreter cache artifacts."""
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


def assert_locked_baseline() -> None:
    actual_main = sha256(BASELINE / "main.py")
    actual_deck = sha256(BASELINE / "deck.csv")
    actual_tree = tree_sha256(BASELINE)
    if (
        actual_main != BASELINE_MAIN_SHA256
        or actual_deck != BASELINE_DECK_SHA256
        or actual_tree != BASELINE_TREE_SHA256
    ):
        raise SystemExit(
            "exact-v22 baseline lock mismatch; refusing to benchmark against "
            "an unknown baseline "
            f"(main={actual_main}, deck={actual_deck}, tree={actual_tree})"
        )


@contextmanager
def agent_runtime(root: pathlib.Path):
    old_cwd = pathlib.Path.cwd()
    old_path = list(sys.path)
    sys.path.insert(0, str(root))
    sys.path.insert(0, str(ENGINE))
    try:
        os.chdir(root)
        yield
    finally:
        os.chdir(old_cwd)
        sys.path[:] = old_path


def _module_from_root(module: Any, root: pathlib.Path) -> bool:
    """Return whether a cached module was imported from one candidate root."""
    raw = getattr(module, "__file__", None)
    if not raw:
        return False
    try:
        pathlib.Path(raw).resolve().relative_to(root)
    except (OSError, ValueError):
        return False
    return True


class CandidateAgent:
    def __init__(self, source: pathlib.Path):
        source = source.resolve()
        self.main = source / "main.py" if source.is_dir() else source
        self.root = self.main.parent
        if not self.main.is_file():
            raise SystemExit(f"candidate main.py missing: {self.main}")
        # Candidate packages often use generic names such as ``policies``.
        # Keeping them in the process-wide import cache lets the second agent
        # silently reuse the first agent's package.  Preserve a private cache
        # per CandidateAgent and swap it in only while loading/calling it.
        self._module_prefixes = {
            path.stem for path in self.root.glob("*.py") if path.stem != "__init__"
        }
        self._module_prefixes.update(
            path.name for path in self.root.iterdir()
            if path.is_dir() and (path / "__init__.py").is_file()
        )
        # ``cg`` is the common official runtime already used by arena_runner;
        # it is deliberately shared, not candidate-owned.
        self._module_prefixes.discard("cg")
        self._private_modules: dict[str, Any] = {}
        with self._module_scope(), agent_runtime(self.root):
            namespace = {
                "__name__": f"__candidate_h2h_{time.time_ns()}__",
                "__builtins__": __builtins__,
            }
            source = self.main.read_text(encoding="utf-8")
            exec(compile(source, "main.py", "exec"), namespace)
        callables = [
            (key, value) for key, value in namespace.items()
            if not key.startswith("__") and callable(value)
        ]
        if not callables:
            raise SystemExit(f"candidate exposes no public callable: {self.main}")
        self.loader_name, self.fn = callables[-1]

    def _matches_private_namespace(self, name: str) -> bool:
        return name.partition(".")[0] in self._module_prefixes

    @contextmanager
    def _module_scope(self):
        """Temporarily install only this candidate's import-cache entries."""
        previous = {
            name: module for name, module in list(sys.modules.items())
            if self._matches_private_namespace(name)
        }
        for name in previous:
            sys.modules.pop(name, None)
        sys.modules.update(self._private_modules)
        try:
            yield
        finally:
            cached_names = self._private_modules.keys()
            self._private_modules = {
                name: module for name, module in list(sys.modules.items())
                if self._matches_private_namespace(name)
                and (name in cached_names or _module_from_root(module, self.root))
            }
            for name in list(sys.modules):
                if self._matches_private_namespace(name):
                    sys.modules.pop(name, None)
            sys.modules.update(previous)

    def __call__(self, obs: dict[str, Any]) -> list[int]:
        with self._module_scope(), agent_runtime(self.root):
            return self.fn(obs)

    def deck(self) -> list[int]:
        obs = {"select": None, "logs": [], "current": None,
               "search_begin_input": None}
        deck = self(obs)
        if not isinstance(deck, list) or len(deck) != 60:
            raise SystemExit(f"startup deck invalid for {self.main}: {deck!r}")
        return [int(card) for card in deck]


def parse_opponent(value: str) -> tuple[str, pathlib.Path]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("opponent must be NAME=PATH")
    name, raw_path = value.split("=", 1)
    if not name.strip() or not raw_path.strip():
        raise argparse.ArgumentTypeError("opponent must be NAME=PATH")
    return name.strip(), pathlib.Path(raw_path).expanduser()


def run_match(candidate: CandidateAgent, opponent: CandidateAgent, n: int,
              seed: int) -> dict[str, Any]:
    candidate_deck = candidate.deck()
    opponent_deck = opponent.deck()
    wins = losses = draws = candidate_faults = opponent_faults = 0
    steps: list[int] = []
    fault_samples: list[dict[str, Any]] = []
    started = time.time()
    for game in range(n):
        # Kaggle asks every submission for its deck at the start of every
        # episode.  That ``select=None`` call is also the documented reset
        # signal used by stateful policies (v22 clears its short action
        # history and strategic memory there).  The local engine receives
        # decks out-of-band, so reproduce the reset explicitly; otherwise
        # the final actions from game N leak into the opening of game N+1.
        if candidate.deck() != candidate_deck:
            raise SystemExit("candidate deck changed between episodes")
        if opponent.deck() != opponent_deck:
            raise SystemExit("opponent deck changed between episodes")
        swap = game % 2 == 1
        agents = (candidate, opponent) if not swap else (opponent, candidate)
        decks = (candidate_deck, opponent_deck) if not swap else (opponent_deck, candidate_deck)
        # This controls Python-side stochastic agents only.  The released
        # native battle engine exposes no shuffle seed, so repeated runs with
        # the same value are independent batches rather than exact replays.
        random.seed(seed + game)
        result = arena.play(agents, decks)
        steps.append(int(result["steps"]))
        fault = result.get("fault")
        if fault is not None:
            candidate_position = 1 if swap else 0
            if fault == candidate_position:
                candidate_faults += 1
                who = "candidate"
            else:
                opponent_faults += 1
                who = "opponent"
            if len(fault_samples) < 10:
                fault_samples.append({
                    "game": game,
                    "who": who,
                    "error": result.get("err"),
                })
        winner = result["winner"]
        if winner == -1:
            draws += 1
        else:
            candidate_position = 1 if swap else 0
            if winner == candidate_position:
                wins += 1
            else:
                losses += 1
    decisive = wins + losses
    return {
        "games": n,
        "wins": wins,
        "losses": losses,
        "draws": draws,
        "win_rate": round(wins / decisive, 6) if decisive else None,
        "candidate_faults": candidate_faults,
        "opponent_faults": opponent_faults,
        "avg_steps": round(statistics.mean(steps), 2) if steps else 0.0,
        "elapsed_s": round(time.time() - started, 3),
        "fault_samples": fault_samples,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", required=True)
    parser.add_argument(
        "--opponent", action="append", type=parse_opponent, metavar="NAME=PATH",
        help="repeatable; defaults to the locked strongest exact-v22 baseline",
    )
    parser.add_argument("--n", type=int, default=64, help="games per opponent")
    parser.add_argument("--seed", type=int, default=20260814)
    parser.add_argument("--out", default="")
    parser.add_argument(
        "--overwrite-output",
        action="store_true",
        help="explicitly replace an existing report; concurrent writers remain locked out",
    )
    args = parser.parse_args()
    if args.n <= 0:
        raise SystemExit("--n must be positive")

    opponents = args.opponent
    using_default_baseline = not opponents
    if using_default_baseline:
        assert_locked_baseline()
        opponents = [("baseline", BASELINE)]

    output_reservation = (
        reserve_json_output(args.out, overwrite=args.overwrite_output)
        if args.out else None
    )
    candidate = CandidateAgent(pathlib.Path(args.candidate))
    if candidate.root == BASELINE.resolve():
        assert_locked_baseline()
    candidate_deck_sha256 = sha256(candidate.root / "deck.csv")
    planned_opponent_decks = [
        sha256((path.resolve() if path.resolve().is_dir() else path.resolve().parent) / "deck.csv")
        for _, path in opponents
        if ((path.resolve() if path.resolve().is_dir() else path.resolve().parent) / "deck.csv").is_file()
    ]
    has_cross_deck_leg = any(
        deck_sha != candidate_deck_sha256 for deck_sha in planned_opponent_decks
    )
    coverage_warning = None
    if not has_cross_deck_leg:
        coverage_warning = (
            "same-deck/single-family coverage only; this is a primary H2H gate, "
            "not a cross-meta regression gate. Add explicit --opponent legs "
            "before promotion"
        )
        print(f"COVERAGE WARNING: {coverage_warning}", flush=True)
    results = []
    for index, (name, path) in enumerate(opponents):
        opponent = CandidateAgent(path)
        if opponent.root == BASELINE.resolve():
            assert_locked_baseline()
        result = run_match(candidate, opponent, args.n, args.seed + index * 100000)
        result["opponent"] = name
        result["opponent_main"] = str(opponent.main)
        result["opponent_main_sha256"] = sha256(opponent.main)
        result["opponent_tree_sha256"] = tree_sha256(opponent.root)
        opponent_deck_path = opponent.root / "deck.csv"
        result["opponent_deck_sha256"] = (
            sha256(opponent_deck_path) if opponent_deck_path.is_file() else None
        )
        results.append(result)
        print(
            f"vs {name}: {result['wins']}-{result['losses']}-{result['draws']} "
            f"WR={result['win_rate']} faults={result['candidate_faults']}/"
            f"{result['opponent_faults']} elapsed={result['elapsed_s']}s",
            flush=True,
        )

    report = {
        "candidate_main": str(candidate.main),
        "candidate_main_sha256": sha256(candidate.main),
        "candidate_deck_sha256": candidate_deck_sha256,
        "candidate_tree_sha256": tree_sha256(candidate.root),
        "candidate_loader": candidate.loader_name,
        "candidate_deck": candidate.deck(),
        "engine": str(ENGINE),
        "runner_sha256": sha256(pathlib.Path(__file__).resolve()),
        "module_isolation": "per-candidate-sys-modules-v1",
        "episode_reset": "select-none-before-every-game-v1",
        "default_baseline": using_default_baseline,
        "coverage": {
            "has_cross_deck_leg": has_cross_deck_leg,
            "warning": coverage_warning,
        },
        "baseline_lock": {
            "main_sha256": BASELINE_MAIN_SHA256,
            "deck_sha256": BASELINE_DECK_SHA256,
            "tree_sha256": BASELINE_TREE_SHA256,
        } if using_default_baseline else None,
        "n_per_opponent": args.n,
        "seed": args.seed,
        "seed_scope": "python-agent-only; native-engine-shuffle-unseeded",
        "output_protocol": "exclusive-lock+atomic-replace-v1" if args.out else None,
        "results": results,
    }
    if args.out:
        output = pathlib.Path(args.out).resolve()
        assert output_reservation is not None
        output_reservation.write(report)
        print(f"report: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
