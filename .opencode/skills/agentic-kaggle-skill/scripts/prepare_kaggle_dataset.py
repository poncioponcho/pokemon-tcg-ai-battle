#!/usr/bin/env python3
"""Create metadata and commands for a Kaggle artifact dataset."""

from __future__ import annotations

import argparse
import json
import re
import textwrap
import time
from pathlib import Path


EXCLUDE_NAMES = {
    "dataset-metadata.json",
    "artifact_dataset_manifest.json",
    "DATASET_COMMANDS.txt",
}


def _slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = value.strip("-")
    return value or "artifact-dataset"


def _iter_files(root: Path) -> list[Path]:
    files = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(part.startswith(".") for part in path.relative_to(root).parts):
            continue
        if path.name in EXCLUDE_NAMES:
            continue
        files.append(path)
    return files


def _resource_description(rel_path: str, artifact_kind: str = "auto") -> str:
    if artifact_kind == "model":
        return "Trained model or inference artifact for a Kaggle pipeline."
    if artifact_kind == "features":
        return "Feature engineering artifact for a Kaggle pipeline."
    if artifact_kind == "predictions":
        return "Prediction artifact for a Kaggle pipeline."
    lower = rel_path.lower()
    if "oof" in lower:
        return "Out-of-fold predictions or validation artifacts."
    if "test" in lower or "submission" in lower:
        return "Test predictions or submission-related artifact."
    if "feature" in lower:
        return "Feature engineering artifact."
    if "model" in lower or "checkpoint" in lower or lower.endswith((".pt", ".pth", ".ckpt", ".safetensors")):
        return "Model checkpoint or trained-model artifact."
    if "metric" in lower or "log" in lower or "manifest" in lower:
        return "Experiment log, metric, or manifest artifact."
    return "Intermediate Kaggle competition artifact."


def _validate_args(username: str, slug: str, title: str) -> None:
    if not username.strip():
        raise ValueError("--username is required")
    if not (3 <= len(slug) <= 50):
        raise ValueError("--slug must normalize to 3-50 characters")
    if not (6 <= len(title) <= 50):
        raise ValueError("--title must be 6-50 characters for Kaggle datasets")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, help="Dataset folder to create/update")
    parser.add_argument("--username", required=True, help="Kaggle username or organization slug")
    parser.add_argument("--slug", required=True, help="Dataset slug")
    parser.add_argument("--title", required=True, help="Dataset title")
    parser.add_argument("--description", required=True, help="Dataset description")
    parser.add_argument("--license", default="CC0-1.0", help="Kaggle license name")
    parser.add_argument("--source-run-id", default="", help="Source experiment or run ID")
    parser.add_argument("--source-kernel", default="", help="Source kernel ref, e.g. user/kernel")
    parser.add_argument(
        "--artifact-kind",
        choices=["auto", "model", "features", "predictions", "mixed"],
        default="auto",
        help="Primary artifact family for dataset metadata and pipeline manifests",
    )
    parser.add_argument("--version-notes", default="Update intermediate artifacts")
    parser.add_argument(
        "--public",
        action="store_true",
        help="Include public create command; use only after checking competition rules, data license, and third-party IP",
    )
    args = parser.parse_args()

    out_dir = Path(args.output).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    slug = _slugify(args.slug)
    _validate_args(args.username, slug, args.title)
    handle = f"{args.username}/{slug}"
    files = _iter_files(out_dir)
    resources = [
        {
            "path": str(path.relative_to(out_dir)),
            "description": _resource_description(str(path.relative_to(out_dir)), args.artifact_kind),
        }
        for path in files
    ]

    metadata = {
        "title": args.title,
        "id": handle,
        "licenses": [{"name": args.license}],
        "description": args.description,
    }
    if resources:
        metadata["resources"] = resources

    manifest = {
        "handle": handle,
        "created_at": time.time(),
        "source_run_id": args.source_run_id,
        "source_kernel": args.source_kernel,
        "artifact_kind": args.artifact_kind,
        "files": [
            {
                "path": str(path.relative_to(out_dir)),
                "size_bytes": path.stat().st_size,
            }
            for path in files
        ],
    }

    (out_dir / "dataset-metadata.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out_dir / "artifact_dataset_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    visibility = " --public" if args.public else ""
    commands = f"""\
    # Keep artifact datasets private unless the competition rules, data license,
    # and third-party IP checks allow public redistribution.

    # Create the dataset the first time.
    kaggle datasets create -p {out_dir} -t -r zip{visibility}

    # Create a new version after replacing or adding artifact files.
    kaggle datasets version -p {out_dir} -m {json.dumps(args.version_notes)} -t -r zip

    # Check processing status.
    kaggle datasets status {handle}

    # Python alternative inside notebooks/scripts.
    # import kagglehub
    # kagglehub.dataset_upload({json.dumps(handle)}, {json.dumps(str(out_dir))}, version_notes={json.dumps(args.version_notes)})
    """
    (out_dir / "DATASET_COMMANDS.txt").write_text(
        textwrap.dedent(commands),
        encoding="utf-8",
    )
    print(f"Prepared Kaggle artifact dataset {handle} at {out_dir}")


if __name__ == "__main__":
    main()
