"""Use an official Kaggle replay dataset as a bulk source.

This deliberately uses the dataset artifact route, not the per-episode
``competitions replay`` endpoint.  It is a lower-request-count alternative,
not a way to bypass Kaggle access controls or rate limits.  The source dataset
is a dated snapshot and does not provide current leaderboard rank metadata.
"""
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


DEFAULT_DATASET = "kaggle/pokemon-tcg-ai-battle-episodes-2026-07-30"


def download(dataset: str, output: str | Path, unzip: bool = True) -> None:
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    command = ["kaggle", "datasets", "download", "-d", dataset, "-p", str(output)]
    if unzip:
        command.append("--unzip")
    subprocess.run(command, check=True)


def inspect(root: str | Path) -> dict[str, int]:
    root = Path(root)
    files = list(root.rglob("*.json"))
    return {
        "json_files": len(files),
        "bytes": sum(path.stat().st_size for path in files),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Official bulk replay dataset route")
    sub = parser.add_subparsers(dest="command", required=True)

    download_parser = sub.add_parser("download")
    download_parser.add_argument("--dataset", default=DEFAULT_DATASET)
    download_parser.add_argument("--output", required=True)
    download_parser.add_argument("--keep-zip", action="store_true")

    inspect_parser = sub.add_parser("inspect")
    inspect_parser.add_argument("--root", required=True)

    args = parser.parse_args()
    if args.command == "download":
        download(args.dataset, args.output, unzip=not args.keep_zip)
    else:
        print(inspect(args.root))


if __name__ == "__main__":
    main()
