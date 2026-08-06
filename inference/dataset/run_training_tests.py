"""Run repeatable BC+RL validation rounds before formal training.

Each round contains:
1. unit tests for registry, vocabulary, warmup, and crawler diff behavior;
2. integration tests for raw -> archive -> archive verification;
3. an end-to-end smoke run: feature extraction followed by one BC and one AWR
   epoch on an isolated temporary dataset.

No Kaggle CLI command is called by this runner.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DATASET = ROOT / "inference" / "dataset"


def command(args: list[str], timeout: int = 600) -> dict:
    started = time.time()
    completed = subprocess.run(
        args,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
    )
    return {
        "command": args,
        "returncode": completed.returncode,
        "seconds": round(time.time() - started, 2),
        "output_tail": completed.stdout[-4000:],
    }


def run_round(round_number: int, raw_dir: Path, archive: Path | None) -> dict:
    result = {"round": round_number, "unit": None, "integration": None, "e2e": None}
    unit = command([
        sys.executable, "-m", "unittest", "-v",
        "inference.dataset.test_mlops_registry",
        "inference.dataset.test_train_bc",
        "inference.dataset.test_quality_subset",
    ])
    if unit["returncode"] != 0:
        raise RuntimeError(f"unit tests failed in round {round_number}: {unit}")
    result["unit"] = unit

    with tempfile.TemporaryDirectory(prefix=f"ptcg-test-{round_number}-") as tmp_name:
        tmp = Path(tmp_name)
        sample_raw = tmp / "raw"
        sample_raw.mkdir()
        raw_files = sorted(raw_dir.glob("episode-*-replay.json")) if raw_dir.exists() else []
        if raw_files:
            for path in raw_files[:3]:
                shutil.copy2(path, sample_raw / path.name)
        elif archive and archive.exists():
            restored = command([
                sys.executable, str(DATASET / "replay_archive.py"), "extract",
                "--archive", str(archive), "--raw-dir", str(sample_raw), "--limit", "3",
            ])
            if restored["returncode"] != 0:
                raise RuntimeError(f"archive restore failed in round {round_number}: {restored}")
        else:
            raise RuntimeError("neither raw replay directory nor archive is available")

        sample_archive = tmp / "sample.jsonl.zst"
        integration = command([
            sys.executable, str(DATASET / "replay_archive.py"), "finalize",
            "--raw-dir", str(sample_raw), "--output", str(sample_archive), "--level", "1",
        ])
        if integration["returncode"] != 0:
            raise RuntimeError(f"integration archive test failed in round {round_number}: {integration}")
        result["integration"] = integration

        extracted = tmp / "data"
        extraction = command([
            sys.executable, str(DATASET / "extract.py"),
            "--raw-dir", str(sample_raw), "--out", str(extracted),
            "--workers", "1",
        ])
        if extraction["returncode"] != 0:
            raise RuntimeError(f"feature extraction failed in round {round_number}: {extraction}")

        training = command([
            sys.executable, str(DATASET / "train_bc.py"),
            "--data-dir", str(extracted),
            "--logs-dir", str(tmp / "logs"),
            "--split-manifest", str(tmp / "episode_splits.jsonl"),
            "--canary-manifest", str(tmp / "rolling_canary.json"),
            "--canary-episodes", "1",
            "--mlops-state", str(tmp / "mlops_state.json"),
            "--device", "cpu",
            "--epochs-bc", "1",
            "--epochs-awr", "1",
            "--bs", "64",
        ], timeout=900)
        if training["returncode"] != 0:
            raise RuntimeError(f"end-to-end training failed in round {round_number}: {training}")
        result["e2e"] = {"extract": extraction, "train": training}
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Three-round BC+RL test runner")
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--raw-dir", default=str(ROOT / "inference/leaderboard_replay/raw"))
    parser.add_argument("--archive", default=str(ROOT / "inference/leaderboard_replay/archive/raw_replays.jsonl.zst"))
    parser.add_argument("--output", default=str(DATASET / "logs/test_rounds.json"))
    args = parser.parse_args()
    raw_dir = Path(args.raw_dir)
    archive = Path(args.archive) if args.archive else None
    results = []
    for round_number in range(1, args.rounds + 1):
        results.append(run_round(round_number, raw_dir, archive))
        print(f"round {round_number}/{args.rounds}: PASS", flush=True)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"status": "passed", "rounds": results}, indent=2) + "\n", encoding="utf-8")
    print(f"all {args.rounds} rounds passed; report={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
