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

If ``--opponent`` is omitted, the immutable strongest live submission in
``submission_baseline`` is used.  This safe default prevents a weaker config A
mirror or a public-notebook score from silently becoming the acceptance gate.
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
BASELINE = ROOT / "submission_baseline"
BASELINE_MAIN_SHA256 = "411d9dff4c146e3bf5b8cbbb935f6c53c84742d670d41930d8315926a61ba480"
BASELINE_DECK_SHA256 = "2a541d7bf3d9e6b36037123f53f4dfef6348223f79fd27095dafc602a5357c19"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ENGINE))

from experiments import arena_runner as arena  # noqa: E402


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def assert_locked_baseline() -> None:
    actual_main = sha256(BASELINE / "main.py")
    actual_deck = sha256(BASELINE / "deck.csv")
    if actual_main != BASELINE_MAIN_SHA256 or actual_deck != BASELINE_DECK_SHA256:
        raise SystemExit(
            "submission_baseline lock mismatch; refusing to benchmark against "
            f"an unknown baseline (main={actual_main}, deck={actual_deck})"
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
        help="repeatable; defaults to the locked strongest retreat baseline",
    )
    parser.add_argument("--n", type=int, default=64, help="games per opponent")
    parser.add_argument("--seed", type=int, default=20260814)
    parser.add_argument("--out", default="")
    args = parser.parse_args()
    if args.n <= 0:
        raise SystemExit("--n must be positive")

    opponents = args.opponent
    using_default_baseline = not opponents
    if using_default_baseline:
        assert_locked_baseline()
        opponents = [("baseline", BASELINE)]

    candidate = CandidateAgent(pathlib.Path(args.candidate))
    results = []
    for index, (name, path) in enumerate(opponents):
        opponent = CandidateAgent(path)
        result = run_match(candidate, opponent, args.n, args.seed + index * 100000)
        result["opponent"] = name
        result["opponent_main"] = str(opponent.main)
        result["opponent_main_sha256"] = sha256(opponent.main)
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
        "candidate_deck_sha256": sha256(candidate.root / "deck.csv"),
        "candidate_loader": candidate.loader_name,
        "candidate_deck": candidate.deck(),
        "engine": str(ENGINE),
        "runner_sha256": sha256(pathlib.Path(__file__).resolve()),
        "module_isolation": "per-candidate-sys-modules-v1",
        "default_baseline": using_default_baseline,
        "baseline_lock": {
            "main_sha256": BASELINE_MAIN_SHA256,
            "deck_sha256": BASELINE_DECK_SHA256,
        } if using_default_baseline else None,
        "n_per_opponent": args.n,
        "seed": args.seed,
        "seed_scope": "python-agent-only; native-engine-shuffle-unseeded",
        "results": results,
    }
    if args.out:
        output = pathlib.Path(args.out).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8")
        print(f"report: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
