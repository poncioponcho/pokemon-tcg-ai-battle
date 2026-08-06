import tempfile
import unittest
from pathlib import Path

import torch

from .train_bc import (
    EarlyStopper,
    Policy,
    load_checkpoint_into_model,
    restrict_split_to_samples,
)


class TrainControlTests(unittest.TestCase):
    def test_resume_loader_accepts_raw_model_state_dict(self):
        model = Policy()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "model.pt"
            torch.save(model.state_dict(), path)
            restored = Policy()
            checkpoint = load_checkpoint_into_model(restored, path)
        self.assertEqual(checkpoint["format"], "state_dict")

    def test_resume_loader_accepts_training_checkpoint(self):
        model = Policy()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "checkpoint.pt"
            torch.save({"model": model.state_dict(), "epoch": 4, "phase": "bc"}, path)
            restored = Policy()
            checkpoint = load_checkpoint_into_model(restored, path)
        self.assertEqual(checkpoint["format"], "checkpoint")
        self.assertEqual(checkpoint["epoch"], 4)

    def test_early_stopper_stops_after_patience_without_improvement(self):
        stopper = EarlyStopper(patience=2, mode="max")
        self.assertFalse(stopper.update(0.50, 1))
        self.assertFalse(stopper.update(0.49, 2))
        self.assertTrue(stopper.update(0.48, 3))
        self.assertEqual(stopper.best_epoch, 1)
        self.assertEqual(stopper.best_value, 0.50)

    def test_sample_index_restricts_only_training_rows(self):
        selected = restrict_split_to_samples([1, 2, 3, 4], [0, 2, 4, 8])
        self.assertEqual(selected.tolist(), [2, 4])


if __name__ == "__main__":
    unittest.main()
