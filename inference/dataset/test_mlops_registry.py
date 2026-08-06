import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(PROJECT_ROOT / "inference"))

from card_vocab import create_vocab, load_vocab  # noqa: E402
from mlops_registry import (  # noqa: E402
    EpisodeCatalog,
    calibrate_thresholds,
    competition_phase,
    ensure_split_manifest,
    evaluate_retrain_trigger,
    refresh_rolling_canary,
)
from update_controller import run_controller  # noqa: E402


class RegistryTests(unittest.TestCase):
    def test_catalog_is_append_only_and_deduplicates_episode_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "raw"
            raw.mkdir()
            replay = raw / "episode-123-replay.json"
            replay.write_text("{}", encoding="utf-8")
            catalog = EpisodeCatalog(root)
            self.assertTrue(catalog.register("123", replay, rank_at_capture=7))
            self.assertFalse(catalog.register("123", replay, rank_at_capture=1))
            rows = [json.loads(line) for line in catalog.path.read_text().splitlines()]
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["rank_at_capture"], 7)

    def test_fixed_split_is_order_independent_and_canary_excludes_test(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ids = [str(i) for i in range(300)]
            split_path = root / "episode_splits.jsonl"
            first = ensure_split_manifest(ids, split_path, fixed_test_fraction=0.1)
            second = ensure_split_manifest(reversed(ids), split_path, fixed_test_fraction=0.1)
            self.assertEqual(first, second)
            records = [
                {"episode_id": episode_id, "captured_at": f"2026-08-{int(episode_id) % 28 + 1:02d}"}
                for episode_id in ids
            ]
            canary = refresh_rolling_canary(records, first, root / "canary.json", limit=20)
            self.assertEqual(len(canary), 20)
            self.assertTrue(all(first[episode_id] != "fixed_test" for episode_id in canary))

    def test_warmup_blocks_accuracy_and_psi_triggers(self):
        kwargs = dict(
            monitoring_enabled=True,
            bc_completed=False,
            metric_plateau=False,
            monitor_sample_size=200,
            base_episode_count=1000,
            new_episode_count=200,
            canary_episode_count=200,
            baseline_accuracy=0.52,
            canary_accuracy=0.40,
            psi=0.5,
            phase="final",
        )
        decision = evaluate_retrain_trigger(**kwargs)
        self.assertFalse(decision.retrain)
        self.assertEqual(decision.reason, "warmup")
        kwargs.update(bc_completed=True, metric_plateau=True)
        decision = evaluate_retrain_trigger(**kwargs)
        self.assertTrue(decision.retrain)
        self.assertTrue(decision.accuracy_trigger)
        self.assertTrue(decision.psi_trigger)

    def test_threshold_calibration_uses_history(self):
        config = {
            "thresholds": {"action_accuracy_drop": 0.05, "psi": 0.2},
            "calibration": {"minimum_windows": 3, "quantile": 0.95, "safety_multiplier": 1.25},
        }
        history = [
            {"baseline_accuracy": 0.52, "canary_accuracy": 0.51, "psi": 0.04},
            {"baseline_accuracy": 0.52, "canary_accuracy": 0.50, "psi": 0.06},
            {"baseline_accuracy": 0.52, "canary_accuracy": 0.49, "psi": 0.08},
        ]
        thresholds, calibrated = calibrate_thresholds(history, config)
        self.assertTrue(calibrated)
        self.assertGreaterEqual(thresholds["action_accuracy_drop"], 0.05)
        self.assertGreaterEqual(thresholds["psi"], 0.2)

    def test_competition_phase_reaches_final_window(self):
        now = datetime(2026, 8, 13, tzinfo=timezone.utc)
        phase = competition_phase(
            now,
            competition_start="2026-08-01T00:00:00Z",
            competition_end="2026-08-15T00:00:00Z",
            final_days=2,
        )
        self.assertEqual(phase, "final")

    def test_vocab_does_not_reorder_existing_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "card_vocab_v1.json"
            first = create_vocab([10, 20, 30], path)
            second = create_vocab([30, 10, 99], path)
            self.assertEqual(first["id_to_index"], second["id_to_index"])
            self.assertEqual(load_vocab(path)["size"], 4)
            self.assertNotIn("99", second["id_to_index"])

    def test_controller_records_warmup_without_running_training(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            metrics = root / "metrics.json"
            metrics.write_text(json.dumps({
                "base_episode_count": 1000,
                "new_episode_count": 200,
                "canary_episode_count": 200,
                "baseline_accuracy": 0.52,
                "canary_accuracy": 0.40,
                "psi": 0.5,
            }), encoding="utf-8")
            args = type("Args", (), {
                "metrics": str(metrics), "state": str(root / "state.json"),
                "config": str(PROJECT_ROOT / "inference/dataset/mlops_config.json"),
                "phase": "final", "competition_start": None,
                "competition_end": None, "final_days": 2, "run_train": False,
                "train_script": "unused", "epochs_bc": 1, "epochs_awr": 1,
                "batch_size": 1, "history_limit": 100,
            })()
            self.assertEqual(run_controller(args), 0)
            state = json.loads((root / "state.json").read_text())
            self.assertEqual(state["last_decision"]["reason"], "warmup")
            self.assertFalse(state["last_decision"]["retrain"])


class HarvesterTests(unittest.TestCase):
    def test_same_submission_still_polls_episode_ids(self):
        import ptcg_replay_harvester as harvester

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "raw"
            raw.mkdir()
            replay = raw / "episode-123-replay.json"
            replay.write_text("{}", encoding="utf-8")
            (root / "manifest.jsonl").write_text(
                json.dumps({
                    "team_id": "team-1",
                    "team_name": "team",
                    "rank": 2,
                    "best_submission_id": "submission-1",
                    "episodes": [{"episode_id": "123", "file": replay.name}],
                }) + "\n",
                encoding="utf-8",
            )
            args = type("Args", (), {
                "out": str(root), "comp": "test", "top": 1, "delay": 0,
                "min_score": None, "max_score": None, "max_episodes": 30,
                "force": False, "phase": "early", "competition_start": None,
                "competition_end": None, "final_days": 2,
            })()
            with patch.object(harvester, "check_prereqs"), \
                    patch.object(harvester, "get_leaderboard", return_value=[(2, "team-1", "team", "900")]), \
                    patch.object(harvester, "get_best_submission", return_value="submission-1"), \
                    patch.object(harvester, "get_episodes", return_value=["123"]) as get_eps, \
                    patch.object(harvester, "download_replay", return_value=replay):
                harvester.cmd_incremental(args)
            get_eps.assert_called_once()


if __name__ == "__main__":
    unittest.main()
