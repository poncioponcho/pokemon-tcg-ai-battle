#!/usr/bin/env python3
"""Create a Kaggle kernel folder with retrievable experiment logs."""

from __future__ import annotations

import argparse
import json
import re
import textwrap
from pathlib import Path


LOGGER_CODE = r'''"""Small logging helper for Kaggle experiment outputs."""

from __future__ import annotations

import json
import os
import platform
import subprocess
import time
import traceback
from pathlib import Path


class ExperimentLogger:
    def __init__(self, run_id: str, output_dir: str | Path = ".") -> None:
        self.run_id = run_id
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.started_at = time.time()
        self.events_path = self.output_dir / "metrics.jsonl"
        self.log = {
            "run_id": run_id,
            "status": "running",
            "started_at": self.started_at,
            "platform": platform.platform(),
            "python": platform.python_version(),
            "kaggle_kernel_run_type": os.environ.get("KAGGLE_KERNEL_RUN_TYPE"),
            "kaggle_url_base": os.environ.get("KAGGLE_URL_BASE"),
            "git_commit": self._git_commit(),
            "config": {},
            "metrics": {},
            "artifacts": [],
            "error": None,
        }
        self.flush()

    def _git_commit(self) -> str | None:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                check=False,
                capture_output=True,
                text=True,
            )
            commit = result.stdout.strip()
            return commit or None
        except Exception:
            return None

    def set_config(self, **config) -> None:
        self.log["config"].update(config)
        self.flush()

    def metric(self, name: str, value, **context) -> None:
        event = {
            "time": time.time(),
            "run_id": self.run_id,
            "name": name,
            "value": value,
            **context,
        }
        with self.events_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, sort_keys=True) + "\n")
        self.log["metrics"][name] = value
        self.flush()

    def artifact(self, path: str | Path, kind: str = "file", **metadata) -> None:
        p = Path(path)
        record = {
            "path": str(p),
            "kind": kind,
            "exists": p.exists(),
            "size_bytes": p.stat().st_size if p.exists() and p.is_file() else None,
            **metadata,
        }
        self.log["artifacts"].append(record)
        self.flush()

    def fail(self, exc: BaseException) -> None:
        self.log["status"] = "failed"
        self.log["error"] = {
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exc(),
        }
        self.flush()
        debug_record = {
            "time": time.time(),
            "run_id": self.run_id,
            "attempt": 1,
            "submission_status": "kernel_failed_before_submission",
            "observed_error": f"{type(exc).__name__}: {exc}",
            "suspected_failure_class": "unknown",
            "patch": None,
            "result": "failed",
        }
        with (self.output_dir / "debug_attempts.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(debug_record, sort_keys=True) + "\n")

    def finish(self) -> None:
        self.log["status"] = "complete"
        self.log["finished_at"] = time.time()
        self.log["elapsed_seconds"] = self.log["finished_at"] - self.started_at
        self.flush()
        self.write_manifest()

    def flush(self) -> None:
        self.log["updated_at"] = time.time()
        with (self.output_dir / "experiment_log.json").open("w", encoding="utf-8") as f:
            json.dump(self.log, f, indent=2, sort_keys=True)

    def write_manifest(self) -> None:
        manifest = {
            "run_id": self.run_id,
            "created_at": time.time(),
            "artifacts": self.log["artifacts"],
            "standard_logs": [
                "experiment_log.json",
                "metrics.jsonl",
                "artifacts_manifest.json",
            ],
        }
        with (self.output_dir / "artifacts_manifest.json").open("w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, sort_keys=True)
'''


RUN_SCRIPT = r'''"""Kaggle remote experiment entry point.

Replace the placeholder training block with the real experiment. Keep the logger
calls so `kaggle kernels output` can retrieve enough information to decide the
next run without opening the notebook UI.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

from experiment_logger import ExperimentLogger


RUN_ID = os.environ.get("RUN_ID", "{run_id}")
OUTPUT_DIR = Path("/kaggle/working") if Path("/kaggle/working").exists() else Path(".")


def main() -> None:
    logger = ExperimentLogger(run_id=RUN_ID, output_dir=OUTPUT_DIR)
    logger.set_config(
        experiment="{title}",
        competition="{competition}",
        accelerator="{accelerator}",
    )
    try:
        # Replace this block with training/inference code.
        # Required outputs for real runs usually include:
        # - OOF predictions
        # - test predictions
        # - submission file
        # - model/checkpoint files when useful
        time.sleep(1)
        placeholder = OUTPUT_DIR / "submission.csv"
        placeholder.write_text("id,target\n0,0\n", encoding="utf-8")
        logger.metric("placeholder_metric", 0.0, stage="smoke")
        logger.artifact(placeholder, kind="submission", note="replace with real output")
        logger.finish()
    except Exception as exc:
        logger.fail(exc)
        raise


if __name__ == "__main__":
    main()
'''


def _slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = value.strip("-")
    return value or "kaggle-experiment"


def _split_csv(values: str | None) -> list[str]:
    if not values:
        return []
    return [v.strip() for v in values.split(",") if v.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, help="Folder to create")
    parser.add_argument("--username", required=True, help="Kaggle username slug")
    parser.add_argument("--slug", required=True, help="Kernel slug")
    parser.add_argument("--title", required=True, help="Kernel title")
    parser.add_argument("--competition", default="", help="Competition slug")
    parser.add_argument("--datasets", default="", help="Comma-separated dataset sources")
    parser.add_argument("--kernels", default="", help="Comma-separated kernel sources")
    parser.add_argument("--models", default="", help="Comma-separated model sources")
    parser.add_argument("--accelerator", default="", help="Kaggle accelerator machine shape")
    parser.add_argument("--internet", action="store_true", help="Enable internet access")
    parser.add_argument(
        "--public",
        action="store_true",
        help="Make kernel public; use only after checking competition rules, data license, and third-party IP",
    )
    args = parser.parse_args()

    out_dir = Path(args.output).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    slug = _slugify(args.slug)
    run_id = slug.replace("-", "_")
    code_file = "run_experiment.py"
    metadata = {
        "id": f"{args.username}/{slug}",
        "title": args.title,
        "code_file": code_file,
        "language": "python",
        "kernel_type": "script",
        "is_private": not args.public,
        "enable_gpu": bool(args.accelerator),
        "enable_internet": bool(args.internet),
        "machine_shape": args.accelerator,
        "dataset_sources": _split_csv(args.datasets),
        "competition_sources": [args.competition] if args.competition else [],
        "kernel_sources": _split_csv(args.kernels),
        "model_sources": _split_csv(args.models),
    }

    (out_dir / "kernel-metadata.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (out_dir / "experiment_logger.py").write_text(LOGGER_CODE, encoding="utf-8")
    (out_dir / code_file).write_text(
        RUN_SCRIPT.format(
            run_id=run_id,
            title=args.title.replace('"', '\\"'),
            competition=args.competition.replace('"', '\\"'),
            accelerator=args.accelerator.replace('"', '\\"'),
        ),
        encoding="utf-8",
    )
    competition_slug = args.competition or "COMPETITION_SLUG"
    (out_dir / "RUN_COMMANDS.txt").write_text(
        textwrap.dedent(
            f"""\
            # Keep kernels private unless the competition rules, data license,
            # and third-party IP checks allow public sharing.

            # Push and run on Kaggle
            kaggle kernels push -p {out_dir}{" --accelerator " + args.accelerator if args.accelerator else ""}

            # Poll status
            kaggle kernels status {args.username}/{slug}

            # Retrieve outputs
            kaggle kernels output {args.username}/{slug} -p remote_outputs/{run_id} -o

            # If this is the final consumer for a classic competition, submit the produced file.
            kaggle competitions submit {competition_slug} -f remote_outputs/{run_id}/submission.csv -m "{run_id}"
            kaggle competitions submissions {competition_slug} -v -q

            # If this is a code competition, submit the final kernel/version instead.
            kaggle competitions submit {competition_slug} -f submission.csv -k {args.username}/{slug} -v KERNEL_VERSION -m "{run_id}"
            kaggle competitions submissions {competition_slug} -v -q
            """
        ),
        encoding="utf-8",
    )
    print(f"Created Kaggle kernel experiment at {out_dir}")


if __name__ == "__main__":
    main()
