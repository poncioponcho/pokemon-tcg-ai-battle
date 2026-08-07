"""Small, single-machine MLOps registry for replay collection and retraining.

The registry deliberately uses append-only JSONL files.  Raw replay files are
immutable and keyed by episode_id; snapshots and split assignments are also
kept as history instead of being overwritten in place.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


EPISODE_RE = re.compile(r"episode[-_](\d+)", re.IGNORECASE)
DEFAULT_CONFIG = {
    "split": {"fixed_test_fraction": 0.10, "canary_episodes": 100},
    "thresholds": {
        "growth_fraction": 0.10,
        "minimum_new_episodes": 100,
        "minimum_canary_episodes": 100,
        "action_accuracy_drop": 0.05,
        "psi": 0.20,
    },
    "calibration": {
        "minimum_windows": 5,
        "quantile": 0.95,
        "safety_multiplier": 1.25,
    },
    "schedule": {
        "early_poll_hours": 24,
        "mid_poll_hours": 6,
        "final_poll_hours": 1,
        "early_retrain_cooldown_hours": 168,
        "mid_retrain_cooldown_hours": 24,
        "final_retrain_cooldown_hours": 6,
        "final_days": 2,
    },
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def episode_id_from_path(path: str | Path) -> str | None:
    match = EPISODE_RE.search(Path(path).name)
    return match.group(1) if match else None


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                rows.append(value)
    return rows


def _append_jsonl(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")


def _write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def sha256_file(path: str | Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


class EpisodeCatalog:
    """Unique episode catalog backed by append-only ``episode_catalog.jsonl``."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.raw_dir = self.root / "raw"
        self.path = self.root / "episode_catalog.jsonl"
        self._records: dict[str, dict[str, Any]] = {}
        self.reload()

    def reload(self) -> None:
        self._records = {}
        for record in _read_jsonl(self.path):
            episode_id = str(record.get("episode_id", ""))
            if episode_id:
                self._records[episode_id] = record

    def known_ids(self) -> set[str]:
        known = set(self._records)
        if self.raw_dir.exists():
            for path in self.raw_dir.glob("*.json"):
                episode_id = episode_id_from_path(path)
                if episode_id:
                    known.add(episode_id)
        return known

    def records(self) -> list[dict[str, Any]]:
        return list(self._records.values())

    def bootstrap_from_manifest(self, manifest_path: str | Path | None = None) -> int:
        """Register existing raw files once without changing their contents.

        Older manifests did not have ``rank_at_capture``.  Their ``rank`` is
        the best available capture-time value and is copied once; no historical
        minimum is computed.
        """
        if self.path.exists() and self._records:
            return 0
        manifest_rows = _read_jsonl(Path(manifest_path)) if manifest_path else []
        by_episode: dict[str, dict[str, Any]] = {}
        for row in manifest_rows:
            captured_at = row.get("captured_at") or row.get("date") or utc_now()
            for episode in row.get("episodes", []):
                episode_id = str(episode.get("episode_id", ""))
                if not episode_id:
                    continue
                path = self.raw_dir / str(episode.get("file", ""))
                if not path.exists():
                    continue
                candidate = self._make_record(
                    episode_id=episode_id,
                    path=path,
                    captured_at=captured_at,
                    team_id=row.get("team_id"),
                    team_name=row.get("team_name"),
                    submission_id=row.get("best_submission_id"),
                    rank_at_capture=row.get("rank_at_capture", row.get("rank")),
                    score_at_capture=row.get(
                        "score_at_capture", row.get("leaderboard_score")
                    ),
                )
                previous = by_episode.get(episode_id)
                if previous is None or str(candidate["captured_at"]) < str(previous["captured_at"]):
                    by_episode[episode_id] = candidate
        for path in sorted(self.raw_dir.glob("*.json")):
            episode_id = episode_id_from_path(path)
            if episode_id and episode_id not in by_episode:
                by_episode[episode_id] = self._make_record(
                    episode_id=episode_id,
                    path=path,
                    captured_at=utc_now(),
                    rank_at_capture=None,
                    score_at_capture=None,
                )
        for record in by_episode.values():
            _append_jsonl(self.path, record)
        self.reload()
        return len(by_episode)

    def _make_record(self, **kwargs: Any) -> dict[str, Any]:
        path = Path(kwargs.pop("path"))
        return {
            "episode_id": str(kwargs.pop("episode_id")),
            "file": path.name,
            "relative_path": str(path.relative_to(self.root))
            if path.is_relative_to(self.root)
            else str(path),
            "sha256": sha256_file(path) if path.exists() else None,
            "bytes": path.stat().st_size if path.exists() else None,
            "captured_at": kwargs.pop("captured_at") or utc_now(),
            "rank_at_capture": kwargs.pop("rank_at_capture", None),
            "score_at_capture": kwargs.pop("score_at_capture", None),
            "team_id": kwargs.pop("team_id", None),
            "team_name": kwargs.pop("team_name", None),
            "submission_id": kwargs.pop("submission_id", None),
            "schema_status": "ready" if path.exists() else "missing",
        }

    def register(
        self,
        episode_id: str,
        path: str | Path,
        *,
        captured_at: str | None = None,
        team_id: str | None = None,
        team_name: str | None = None,
        submission_id: str | None = None,
        rank_at_capture: int | float | str | None = None,
        score_at_capture: float | str | None = None,
    ) -> bool:
        """Append a new catalog row. Existing episode IDs are never replaced."""
        episode_id = str(episode_id)
        if episode_id in self._records:
            return False
        record = self._make_record(
            episode_id=episode_id,
            path=Path(path),
            captured_at=captured_at or utc_now(),
            team_id=team_id,
            team_name=team_name,
            submission_id=submission_id,
            rank_at_capture=rank_at_capture,
            score_at_capture=score_at_capture,
        )
        _append_jsonl(self.path, record)
        self._records[episode_id] = record
        return True


def append_leaderboard_snapshot(
    root: str | Path,
    teams: Iterable[dict[str, Any]],
    *,
    phase: str = "early",
    captured_at: str | None = None,
) -> dict[str, Any]:
    captured_at = captured_at or utc_now()
    # [bugfix] 旧顺序先 remove ":" 再替换 "+00:00"，导致 "+0000" 永远匹配不上 "Z"，
    # snapshot_id 在不同 captured_at 格式下产出不一致文件名。先做时区归一化。
    snapshot_id = (
        captured_at.replace(" ", "T")
        .replace("+00:00", "Z")
        .replace(":", "")
    )
    snapshot = {
        "snapshot_id": snapshot_id,
        "captured_at": captured_at,
        "phase": phase,
        "teams": list(teams),
    }
    root = Path(root)
    _append_jsonl(root / "leaderboard_snapshots.jsonl", snapshot)
    _write_json_atomic(root / "snapshots" / f"{snapshot_id}.json", snapshot)
    return snapshot


def stable_split(episode_id: str, fixed_test_fraction: float = 0.10) -> str:
    digest = hashlib.sha256(f"fixed-test-v1:{episode_id}".encode()).hexdigest()
    bucket = int(digest[:8], 16) / 0xFFFFFFFF
    return "fixed_test" if bucket < fixed_test_fraction else "train"


def ensure_split_manifest(
    episode_ids: Iterable[str],
    path: str | Path,
    *,
    fixed_test_fraction: float = 0.10,
) -> dict[str, str]:
    """Append stable train/fixed_test assignments for previously unseen IDs."""
    path = Path(path)
    existing = {
        str(row["episode_id"]): str(row["split"])
        for row in _read_jsonl(path)
        if row.get("episode_id") and row.get("split")
    }
    for episode_id in sorted({str(value) for value in episode_ids}):
        if episode_id in existing:
            continue
        split = stable_split(episode_id, fixed_test_fraction)
        _append_jsonl(
            path,
            {
                "episode_id": episode_id,
                "split": split,
                "assigned_at": utc_now(),
                "split_version": "fixed-test-v1",
            },
        )
        existing[episode_id] = split
    return existing


def refresh_rolling_canary(
    episode_records: Iterable[dict[str, Any]],
    assignments: dict[str, str],
    path: str | Path,
    *,
    limit: int = 100,
) -> list[str]:
    """Write the current temporal canary without mutating fixed assignments."""
    candidates = []
    for record in episode_records:
        episode_id = str(record.get("episode_id", ""))
        if not episode_id or assignments.get(episode_id) == "fixed_test":
            continue
        candidates.append(
            (
                str(record.get("captured_at") or ""),
                episode_id,
            )
        )
    selected = [episode_id for _, episode_id in sorted(candidates, reverse=True)[:limit]]
    _write_json_atomic(
        Path(path),
        {
            "generated_at": utc_now(),
            "split": "rolling_canary",
            "episode_ids": selected,
        },
    )
    return selected


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    config = json.loads(json.dumps(DEFAULT_CONFIG))
    if path is None or not Path(path).exists():
        return config
    user = json.loads(Path(path).read_text(encoding="utf-8"))
    for section, values in user.items():
        if isinstance(values, dict) and isinstance(config.get(section), dict):
            config[section].update(values)
        else:
            config[section] = values
    return config


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    value = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def competition_phase(
    now: datetime | None = None,
    *,
    competition_start: str | None = None,
    competition_end: str | None = None,
    final_days: int = 2,
) -> str:
    now = now or datetime.now(timezone.utc)
    start = _parse_time(competition_start)
    end = _parse_time(competition_end)
    if not start or not end:
        return "early"
    if now < start:
        return "early"
    if now >= end:
        return "complete"
    if (end - now).total_seconds() <= final_days * 86400:
        return "final"
    return "mid"


def phase_policy(phase: str, config: dict[str, Any]) -> dict[str, Any]:
    schedule = config["schedule"]
    if phase == "final":
        return {
            "phase": phase,
            "poll_hours": schedule["final_poll_hours"],
            "retrain_cooldown_hours": schedule["final_retrain_cooldown_hours"],
        }
    if phase == "mid":
        return {
            "phase": phase,
            "poll_hours": schedule["mid_poll_hours"],
            "retrain_cooldown_hours": schedule["mid_retrain_cooldown_hours"],
        }
    return {
        "phase": phase,
        "poll_hours": schedule["early_poll_hours"],
        "retrain_cooldown_hours": schedule["early_retrain_cooldown_hours"],
    }


def population_stability_index(reference: Iterable[float], current: Iterable[float], bins: int = 10) -> float:
    """Compute PSI for numeric feature samples; used as a drift signal only."""
    try:
        import numpy as np
    except ImportError as exc:  # pragma: no cover - project training already needs numpy
        raise RuntimeError("numpy is required for PSI") from exc
    ref = np.asarray(list(reference), dtype=float)
    cur = np.asarray(list(current), dtype=float)
    ref = ref[np.isfinite(ref)]
    cur = cur[np.isfinite(cur)]
    if ref.size == 0 or cur.size == 0:
        return 0.0
    edges = np.unique(np.quantile(ref, np.linspace(0, 1, bins + 1)))
    if edges.size < 2:
        return 0.0 if np.isclose(ref.mean(), cur.mean()) else 1.0
    expected, _ = np.histogram(ref, bins=edges)
    actual, _ = np.histogram(cur, bins=edges)
    expected = np.maximum(expected / max(expected.sum(), 1), 1e-6)
    actual = np.maximum(actual / max(actual.sum(), 1), 1e-6)
    return float(np.sum((actual - expected) * np.log(actual / expected)))


def _quantile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    index = min(len(values) - 1, max(0, math.ceil(q * len(values)) - 1))
    return values[index]


def calibrate_thresholds(
    history: Iterable[dict[str, Any]], config: dict[str, Any]
) -> tuple[dict[str, float], bool]:
    """Use prior normal windows to turn initial heuristics into local thresholds."""
    rows = list(history)
    calibration = config["calibration"]
    defaults = config["thresholds"]
    if len(rows) < int(calibration["minimum_windows"]):
        return {
            "action_accuracy_drop": float(defaults["action_accuracy_drop"]),
            "psi": float(defaults["psi"]),
        }, False
    drops = [
        max(0.0, float(row.get("baseline_accuracy", 0.0)) - float(row.get("canary_accuracy", 0.0)))
        for row in rows
    ]
    psis = [max(0.0, float(row.get("psi", 0.0))) for row in rows]
    multiplier = float(calibration["safety_multiplier"])
    return {
        "action_accuracy_drop": max(
            float(defaults["action_accuracy_drop"]),
            _quantile(drops, float(calibration["quantile"])) * multiplier,
        ),
        "psi": max(
            float(defaults["psi"]),
            _quantile(psis, float(calibration["quantile"])) * multiplier,
        ),
    }, True


@dataclass
class TriggerDecision:
    retrain: bool
    reason: str
    thresholds: dict[str, float]
    calibrated: bool
    volume_trigger: bool
    accuracy_trigger: bool
    psi_trigger: bool


def evaluate_retrain_trigger(
    *,
    monitoring_enabled: bool,
    bc_completed: bool,
    metric_plateau: bool,
    monitor_sample_size: int,
    base_episode_count: int,
    new_episode_count: int,
    canary_episode_count: int,
    baseline_accuracy: float | None,
    canary_accuracy: float | None,
    psi: float | None,
    phase: str,
    last_retrain_at: str | None = None,
    now: datetime | None = None,
    history: Iterable[dict[str, Any]] = (),
    config: dict[str, Any] | None = None,
) -> TriggerDecision:
    config = config or load_config()
    thresholds, calibrated = calibrate_thresholds(history, config)
    if not monitoring_enabled or not bc_completed or not metric_plateau:
        return TriggerDecision(False, "warmup", thresholds, calibrated, False, False, False)
    if monitor_sample_size < int(config["thresholds"]["minimum_canary_episodes"]):
        return TriggerDecision(False, "insufficient_canary_samples", thresholds, calibrated, False, False, False)

    minimum_new = int(config["thresholds"]["minimum_new_episodes"])
    growth_target = math.ceil(base_episode_count * float(config["thresholds"]["growth_fraction"]))
    volume_trigger = new_episode_count >= max(minimum_new, growth_target)
    accuracy_drop = (
        float(baseline_accuracy) - float(canary_accuracy)
        if baseline_accuracy is not None and canary_accuracy is not None
        else 0.0
    )
    accuracy_trigger = (
        canary_episode_count >= int(config["thresholds"]["minimum_canary_episodes"])
        and accuracy_drop >= thresholds["action_accuracy_drop"]
    )
    psi_trigger = psi is not None and float(psi) >= thresholds["psi"]
    policy = phase_policy(phase, config)
    cooldown_hours = float(policy["retrain_cooldown_hours"])
    if last_retrain_at:
        previous = _parse_time(last_retrain_at)
        current = now or datetime.now(timezone.utc)
        if previous and (current - previous).total_seconds() < cooldown_hours * 3600:
            return TriggerDecision(False, "phase_cooldown", thresholds, calibrated, volume_trigger, accuracy_trigger, bool(psi_trigger))
    if volume_trigger or accuracy_trigger or psi_trigger:
        reasons = []
        if volume_trigger:
            reasons.append("data_volume")
        if accuracy_trigger:
            reasons.append("canary_accuracy")
        if psi_trigger:
            reasons.append("feature_psi")
        return TriggerDecision(True, "+".join(reasons), thresholds, calibrated, volume_trigger, accuracy_trigger, bool(psi_trigger))
    return TriggerDecision(False, "no_signal", thresholds, calibrated, False, False, False)


def mark_baseline_ready(path: str | Path, *, sample_size: int, metric_plateau: bool) -> dict[str, Any]:
    state_path = Path(path)
    state = {}
    if state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))
    state.update(
        {
            "bc_completed": True,
            "metric_plateau": bool(metric_plateau),
            "monitor_sample_size": int(sample_size),
            "monitoring_enabled": bool(metric_plateau and sample_size >= 100),
            "baseline_ready_at": utc_now(),
        }
    )
    _write_json_atomic(state_path, state)
    return state


def _cli() -> int:
    parser = argparse.ArgumentParser(description="Replay MLOps registry utilities")
    sub = parser.add_subparsers(dest="command", required=True)

    phase = sub.add_parser("phase")
    phase.add_argument("--start")
    phase.add_argument("--end")
    phase.add_argument("--final-days", type=int, default=2)

    split = sub.add_parser("split")
    split.add_argument("--episode-ids", required=True)
    split.add_argument("--output", required=True)
    split.add_argument("--test-fraction", type=float, default=0.10)

    baseline = sub.add_parser("mark-baseline")
    baseline.add_argument("--state", required=True)
    baseline.add_argument("--sample-size", type=int, required=True)
    baseline.add_argument("--metric-plateau", action="store_true")

    bootstrap = sub.add_parser("bootstrap")
    bootstrap.add_argument("--root", required=True, help="leaderboard_replay directory")
    bootstrap.add_argument("--manifest", default=None)

    args = parser.parse_args()
    if args.command == "phase":
        phase_name = competition_phase(
            competition_start=args.start,
            competition_end=args.end,
            final_days=args.final_days,
        )
        print(json.dumps({"phase": phase_name, "policy": phase_policy(phase_name, load_config())}))
        return 0
    if args.command == "split":
        episode_ids = json.loads(Path(args.episode_ids).read_text(encoding="utf-8"))
        assignments = ensure_split_manifest(episode_ids, args.output, fixed_test_fraction=args.test_fraction)
        print(json.dumps({"episodes": len(assignments), "output": args.output}))
        return 0
    if args.command == "bootstrap":
        catalog = EpisodeCatalog(args.root)
        count = catalog.bootstrap_from_manifest(args.manifest)
        print(json.dumps({"registered": count, "catalog": str(catalog.path)}))
        return 0
    mark_baseline_ready(args.state, sample_size=args.sample_size, metric_plateau=args.metric_plateau)
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
