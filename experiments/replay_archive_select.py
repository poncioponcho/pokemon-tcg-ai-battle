#!/usr/bin/env python3
"""Selectively restore replay JSON records from a stream archive.

Target episode IDs may be supplied directly or selected from the leaderboard
catalog by submission ID/team name.  The scan stops as soon as all requested
records have been found, avoiding a full archive extraction.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from inference.dataset.replay_archive import iter_records  # noqa: E402


def catalog_ids(
    catalog: pathlib.Path,
    submission_id: int | None,
    team_name: str | None,
) -> set[str]:
    selected: set[str] = set()
    with catalog.open(encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            row = json.loads(line)
            if submission_id is not None and int(row.get("submission_id") or -1) != submission_id:
                continue
            if team_name is not None and str(row.get("team_name") or "") != team_name:
                continue
            selected.add(str(row["episode_id"]))
    return selected


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--catalog")
    parser.add_argument("--submission-id", type=int)
    parser.add_argument("--team-name")
    parser.add_argument("--episode", action="append", default=[])
    args = parser.parse_args()

    wanted = {str(value) for value in args.episode}
    if args.catalog:
        wanted |= catalog_ids(
            pathlib.Path(args.catalog).expanduser().resolve(),
            args.submission_id,
            args.team_name,
        )
    if not wanted:
        raise SystemExit("no target episode IDs")

    output = pathlib.Path(args.out_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    remaining = set(wanted)
    found: list[str] = []
    scanned = 0
    started = time.time()
    for row in iter_records(pathlib.Path(args.archive).expanduser().resolve()):
        scanned += 1
        episode = str(row["episode_id"])
        if episode not in remaining:
            continue
        filename = pathlib.Path(str(row["file"])).name
        if filename != str(row["file"]):
            raise ValueError(f"unsafe archive filename: {row['file']}")
        raw = row.get("raw_json")
        if raw is None:
            raw = json.dumps(row["replay"], ensure_ascii=False, separators=(",", ":"))
        target = output / filename
        target.write_text(str(raw), encoding="utf-8")
        json.loads(target.read_text(encoding="utf-8"))
        found.append(episode)
        remaining.remove(episode)
        if not remaining:
            break

    report = {
        "requested": len(wanted),
        "found": len(found),
        "missing": sorted(remaining, key=int),
        "scanned_records": scanned,
        "elapsed_s": round(time.time() - started, 3),
        "out_dir": str(output),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if remaining else 0


if __name__ == "__main__":
    raise SystemExit(main())
