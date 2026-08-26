#!/usr/bin/env python3
"""Pull public Kaggle episodes and replay JSON for one or more submissions.

The Kaggle CLI exposes episode metadata on stdout and writes replay payloads
to a directory.  This wrapper keeps one directory per submission, stores the
metadata atomically, skips completed downloads, and retries transient API/DNS
failures.  It is intended for read-only public-policy audits.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import random
import subprocess
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any


DEFAULT_KAGGLE = "/opt/homebrew/bin/kaggle"


def atomic_json(path: pathlib.Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def list_episodes(kaggle: str, ref: int) -> list[dict[str, Any]]:
    command = [
        kaggle,
        "competitions",
        "episodes",
        str(ref),
        "--format",
        "json",
        "--quiet",
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=120)
    if result.returncode:
        raise RuntimeError(f"episodes {ref} failed: {result.stderr[-500:]}")
    payload = json.loads(result.stdout)
    if not isinstance(payload, list):
        raise RuntimeError(f"episodes {ref} returned {type(payload).__name__}, not list")
    return payload


def replay_present(directory: pathlib.Path, episode: int) -> bool:
    return any(directory.glob(f"*{episode}*replay*.json"))


def pull_one(
    kaggle: str,
    directory: pathlib.Path,
    episode: int,
    retries: int,
) -> tuple[int, str, str]:
    if replay_present(directory, episode):
        return episode, "skip", ""
    last_error = ""
    for attempt in range(retries):
        command = [
            kaggle,
            "competitions",
            "replay",
            str(episode),
            "--path",
            str(directory),
            "--quiet",
        ]
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=180)
            last_error = (result.stderr or result.stdout)[-500:]
            if result.returncode == 0 and replay_present(directory, episode):
                return episode, "ok", ""
        except subprocess.TimeoutExpired as exc:
            last_error = f"timeout: {exc}"
        if attempt + 1 < retries:
            time.sleep(min(12.0, 1.5 * (2**attempt)) + random.random())
    return episode, "fail", last_error


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("refs", nargs="+", type=int)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--retries", type=int, default=4)
    parser.add_argument("--max-per-ref", type=int, default=0, help="0 downloads every public episode")
    parser.add_argument(
        "--sample",
        choices=("recent", "oldest", "even"),
        default="recent",
        help="deterministic subset when --max-per-ref is positive",
    )
    parser.add_argument("--kaggle", default=DEFAULT_KAGGLE)
    args = parser.parse_args()

    root = pathlib.Path(args.out_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    jobs: list[tuple[int, pathlib.Path, int]] = []
    summaries: dict[int, dict[str, Any]] = {}

    for ref in args.refs:
        directory = root / str(ref)
        directory.mkdir(parents=True, exist_ok=True)
        rows = list_episodes(args.kaggle, ref)
        atomic_json(directory / f"episodes-{ref}.json", rows)
        public_rows = [
            row
            for row in rows
            if str(row.get("type", "")).endswith("PUBLIC")
            and str(row.get("state", "")).endswith("COMPLETED")
        ]
        public_rows.sort(key=lambda row: (str(row.get("endTime") or ""), int(row["id"])))
        if args.max_per_ref and len(public_rows) > args.max_per_ref:
            if args.sample == "oldest":
                public_rows = public_rows[: args.max_per_ref]
            elif args.sample == "recent":
                public_rows = public_rows[-args.max_per_ref :]
            else:
                n = args.max_per_ref
                last = len(public_rows) - 1
                indices = sorted({round(index * last / max(1, n - 1)) for index in range(n)})
                public_rows = [public_rows[index] for index in indices]
        public = [int(row["id"]) for row in public_rows]
        summaries[ref] = {
            "listed": len(rows),
            "public_completed_total": sum(
                1
                for row in rows
                if str(row.get("type", "")).endswith("PUBLIC")
                and str(row.get("state", "")).endswith("COMPLETED")
            ),
            "selected": len(public),
            "ok": 0,
            "skip": 0,
            "fail": 0,
            "failures": [],
        }
        jobs.extend((ref, directory, episode) for episode in public)

    lock = threading.Lock()
    completed = 0
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        future_map = {
            pool.submit(pull_one, args.kaggle, directory, episode, args.retries): (ref, episode)
            for ref, directory, episode in jobs
        }
        for future in as_completed(future_map):
            ref, episode = future_map[future]
            try:
                _, status, error = future.result()
            except Exception as exc:  # retain audit trail and finish other downloads
                status, error = "fail", repr(exc)
            with lock:
                summaries[ref][status] += 1
                if status == "fail":
                    summaries[ref]["failures"].append({"episode": episode, "error": error})
                completed += 1
                if completed % 20 == 0 or completed == len(jobs):
                    print(f"[pull] {completed}/{len(jobs)}", flush=True)

    report = {
        "created_unix": time.time(),
        "refs": args.refs,
        "workers": args.workers,
        "retries": args.retries,
        "max_per_ref": args.max_per_ref,
        "sample": args.sample,
        "summaries": summaries,
    }
    atomic_json(root / "pull-summary.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if any(row["fail"] for row in summaries.values()) else 0


if __name__ == "__main__":
    raise SystemExit(main())
