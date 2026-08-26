#!/usr/bin/env python3
"""Read-only pre-deadline watcher for the two frozen exact-v22 refs.

This script never calls a submission endpoint.  It records submission status,
latest-2 composition, and public W/L snapshots at the four final checkpoints.
Any non-COMPLETE/error condition is emitted as an ALERT for human review.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import subprocess
import tempfile
import time
from typing import Any
from zoneinfo import ZoneInfo


ROOT = pathlib.Path(__file__).resolve().parents[1]
PYTHON = "/opt/homebrew/bin/python3"
KAGGLE = "/opt/homebrew/bin/kaggle"
TEAM_ID = "16640688"
REFS = (55547740, 55539446)
EXPECTED = set(REFS)
TZ = ZoneInfo("Asia/Shanghai")
TARGETS = (
    dt.datetime(2026, 8, 16, 22, 30, tzinfo=TZ),
    dt.datetime(2026, 8, 17, 0, 30, tzinfo=TZ),
    dt.datetime(2026, 8, 17, 2, 30, tzinfo=TZ),
    dt.datetime(2026, 8, 17, 5, 30, tzinfo=TZ),
)
OUT_DIR = ROOT / "experiments" / "runs" / "final_predeadline_watch"
SUMMARY = OUT_DIR / "watch.jsonl"


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


def run(command: list[str], attempts: int = 3) -> subprocess.CompletedProcess[str]:
    last: subprocess.CompletedProcess[str] | None = None
    for attempt in range(attempts):
        last = subprocess.run(
            command,
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=180,
        )
        if last.returncode == 0:
            return last
        if attempt + 1 < attempts:
            time.sleep(5 * (attempt + 1))
    assert last is not None
    return last


def parse_json(result: subprocess.CompletedProcess[str]) -> Any:
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout)[-1000:])
    return json.loads(result.stdout)


def episode_summary(path: pathlib.Path) -> dict[str, Any]:
    rows = json.loads(path.read_text(encoding="utf-8"))
    public = [
        row for row in rows
        if row.get("opp_sub") is not None and row.get("reward") in (-1, 1)
    ]
    wins = sum(row["reward"] == 1 for row in public)
    losses = sum(row["reward"] == -1 for row in public)
    return {
        "public": len(public),
        "wins": wins,
        "losses": losses,
        "win_rate": round(wins / len(public), 6) if public else None,
        "newest_end": max((row.get("end") or "" for row in public), default=None),
    }


def checkpoint(label: str) -> dict[str, Any]:
    captured = dt.datetime.now(TZ)
    failures: list[str] = []
    statuses: dict[str, Any] = {}
    episodes: dict[str, Any] = {}

    for ref in REFS:
        try:
            statuses[str(ref)] = parse_json(run([
                PYTHON,
                "scripts/candidate_delivery.py",
                "inspect",
                "--ref",
                str(ref),
            ]))
        except Exception as exc:
            failures.append(f"inspect {ref}: {exc!r}")

        episode_path = OUT_DIR / f"live_episodes_{ref}_{label}.json"
        probe = run([
            PYTHON,
            "experiments/live_episodes_probe.py",
            "--ref",
            str(ref),
            "--out",
            str(episode_path),
        ])
        if probe.returncode:
            failures.append(f"probe {ref}: {(probe.stderr or probe.stdout)[-1000:]}")
        elif episode_path.is_file():
            episodes[str(ref)] = episode_summary(episode_path)

    latest2: list[dict[str, Any]] = []
    try:
        latest2 = parse_json(run([
            KAGGLE,
            "competitions",
            "team-submissions",
            TEAM_ID,
            "--format",
            "json",
        ]))
    except Exception as exc:
        failures.append(f"team-submissions: {exc!r}")

    latest_ids = {int(row["id"]) for row in latest2 if row.get("id") is not None}
    if latest_ids and latest_ids != EXPECTED:
        failures.append(f"latest-2 drift: {sorted(latest_ids)} != {sorted(EXPECTED)}")
    for ref in REFS:
        row = statuses.get(str(ref)) or {}
        if row and row.get("status") != "COMPLETE":
            failures.append(f"ref {ref} status={row.get('status')}")
        if row.get("error_description"):
            failures.append(f"ref {ref} error={row['error_description']}")

    payload = {
        "label": label,
        "captured_cst": captured.isoformat(),
        "mode": "READ_ONLY_NO_SUBMISSION_ENDPOINT",
        "statuses": statuses,
        "latest2": latest2,
        "episodes": episodes,
        "verdict": "ALERT" if failures else "HEALTHY",
        "failures": failures,
    }
    atomic_json(OUT_DIR / f"checkpoint_{label}.json", payload)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with SUMMARY.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
        stream.flush()
        os.fsync(stream.fileno())

    sentinel = {
        "prompt": (
            "Review the final PTCG pre-deadline checkpoint. Do not submit unless a "
            "frozen ref has a confirmed runtime/COMPLETE failure; score or WR movement "
            "alone never authorizes submission."
        ),
        "label": label,
        "verdict": payload["verdict"],
        "failures": failures,
    }
    print(
        "AGENT_LOOP_TICK_PTCG_FINAL "
        + json.dumps(sentinel, ensure_ascii=False, separators=(",", ":")),
        flush=True,
    )
    return payload


def wait_until(target: dt.datetime) -> None:
    while True:
        remaining = (target - dt.datetime.now(TZ)).total_seconds()
        if remaining <= 0:
            return
        time.sleep(min(30.0, remaining))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="run one immediate smoke checkpoint")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if args.once:
        payload = checkpoint("smoke_" + dt.datetime.now(TZ).strftime("%Y%m%d_%H%M%S"))
        return 1 if payload["verdict"] == "ALERT" else 0

    now = dt.datetime.now(TZ)
    pending = [target for target in TARGETS if target > now]
    print(
        json.dumps({
            "pid": os.getpid(),
            "mode": "READ_ONLY_NO_SUBMISSION_ENDPOINT",
            "targets": [target.isoformat() for target in pending],
        }, ensure_ascii=False),
        flush=True,
    )
    for target in pending:
        wait_until(target)
        checkpoint(target.strftime("%Y%m%d_%H%M"))
    print("AGENT_LOOP_TICK_PTCG_FINAL_DONE", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
