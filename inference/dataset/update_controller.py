"""Decide whether to run a full retraining after incremental collection.

This controller never performs incremental model fine-tuning. When a trigger is
accepted it invokes ``train_bc.py --phase all`` over the complete current
dataset. Metric thresholds start as heuristics and are calibrated from prior
normal monitoring windows.

Example:
  python3 update_controller.py --metrics metrics.json --run-train
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    from .mlops_registry import (
        competition_phase,
        evaluate_retrain_trigger,
        load_config,
        utc_now,
    )
except ImportError:  # Direct script execution.
    from mlops_registry import (  # type: ignore
        competition_phase,
        evaluate_retrain_trigger,
        load_config,
        utc_now,
    )


def _load(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _save(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_controller(args) -> int:
    metrics = _load(Path(args.metrics), {})
    state_path = Path(args.state)
    state = _load(state_path, {})
    config = load_config(args.config)
    history = list(state.get("history", []))
    phase = args.phase
    if phase == "auto":
        phase = competition_phase(
            competition_start=args.competition_start,
            competition_end=args.competition_end,
            final_days=args.final_days,
        )

    decision = evaluate_retrain_trigger(
        monitoring_enabled=bool(state.get("monitoring_enabled", False)),
        bc_completed=bool(state.get("bc_completed", False)),
        metric_plateau=bool(state.get("metric_plateau", False)),
        monitor_sample_size=int(metrics.get("canary_episode_count", 0)),
        base_episode_count=int(metrics.get("base_episode_count", 0)),
        new_episode_count=int(metrics.get("new_episode_count", 0)),
        canary_episode_count=int(metrics.get("canary_episode_count", 0)),
        baseline_accuracy=metrics.get("baseline_accuracy"),
        canary_accuracy=metrics.get("canary_accuracy"),
        psi=metrics.get("psi"),
        phase=phase,
        last_retrain_at=state.get("last_retrain_at"),
        history=history,
        config=config,
    )
    result = {
        "observed_at": utc_now(),
        "phase": phase,
        "retrain": decision.retrain,
        "reason": decision.reason,
        "thresholds": decision.thresholds,
        "calibrated": decision.calibrated,
        "volume_trigger": decision.volume_trigger,
        "accuracy_trigger": decision.accuracy_trigger,
        "psi_trigger": decision.psi_trigger,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))

    # Store the observation even during warmup. It becomes calibration history,
    # but cannot trigger a run until the explicit baseline gate is opened.
    history.append({**metrics, "observed_at": result["observed_at"], "phase": phase})
    state["history"] = history[-int(args.history_limit):]
    state["last_decision"] = result

    if decision.retrain and args.run_train:
        train_script = Path(args.train_script)
        command = [
            sys.executable,
            str(train_script),
            "--phase", "all",
            "--epochs-bc", str(args.epochs_bc),
            "--epochs-awr", str(args.epochs_awr),
            "--bs", str(args.batch_size),
            "--early-stop-patience", str(args.early_stop_patience),
            "--early-stop-min-delta", str(args.early_stop_min_delta),
        ]
        print("running full retrain:", " ".join(command), flush=True)
        completed = subprocess.run(command, check=False)
        if completed.returncode != 0:
            state["last_retrain_error"] = {
                "at": utc_now(),
                "returncode": completed.returncode,
            }
            _save(state_path, state)
            return completed.returncode
        state["last_retrain_at"] = utc_now()
        state["last_retrain_mode"] = "full"
    _save(state_path, state)
    return 0


def main() -> int:
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description="Full-retraining controller for replay drift")
    parser.add_argument("--metrics", required=True, help="JSON metrics for the current canary window")
    parser.add_argument("--state", default=str(root / "mlops_state.json"))
    parser.add_argument("--config", default=str(root / "mlops_config.json"))
    parser.add_argument("--phase", choices=("auto", "early", "mid", "final"), default="auto")
    parser.add_argument("--competition-start")
    parser.add_argument("--competition-end")
    parser.add_argument("--final-days", type=int, default=2)
    parser.add_argument("--run-train", action="store_true", help="Run complete BC+AWR retraining when triggered")
    parser.add_argument("--train-script", default=str(root / "train_bc.py"))
    parser.add_argument("--epochs-bc", type=int, default=6)
    parser.add_argument("--epochs-awr", type=int, default=4)
    parser.add_argument("--batch-size", type=int, default=4096)
    parser.add_argument("--early-stop-patience", type=int, default=5)
    parser.add_argument("--early-stop-min-delta", type=float, default=0.0001)
    parser.add_argument("--history-limit", type=int, default=100)
    args = parser.parse_args()
    return run_controller(args)


if __name__ == "__main__":
    raise SystemExit(main())
