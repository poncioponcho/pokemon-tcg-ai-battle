import unittest

import numpy as np

from .quality_subset import (
    build_sample_selection,
    captured_team_index,
    normalize_team_name,
)


class QualitySubsetTests(unittest.TestCase):
    def test_team_name_matching_is_case_and_prefix_tolerant(self):
        names = ["Opponent", "@TopPlayer"]
        self.assertEqual(captured_team_index(names, "topplayer"), 1)
        self.assertEqual(normalize_team_name(" @TopPlayer "), "topplayer")

    def test_top_ratio_and_captured_side_filter(self):
        episode_ids = np.array(["a", "a", "b", "b", "c", "c"])
        # ep, perspective, reward, turn, ctx, nopts, rank, captured_side, is_captured
        meta = np.array([
            [0, 0, 1, 12, 0, 2, 1, 1, 1],
            [0, 1, -1, 12, 0, 2, 1, 1, 0],
            [1, 0, 1, 4, 0, 2, 10, 0, 0],
            [1, 1, -1, 4, 0, 2, 10, 0, 1],
            [2, 0, 1, 15, 0, 2, 20, 1, 1],
            [2, 1, -1, 15, 0, 2, 20, 1, 0],
        ], dtype=np.float32)
        indices, weights, report = build_sample_selection(
            episode_ids,
            meta,
            top_ratio=0.5,
            captured_team_only=True,
            win_bonus=1.5,
            late_turn_start=10,
            late_turn_bonus=2.0,
        )
        self.assertEqual(indices.tolist(), [0, 3])
        self.assertEqual(weights.tolist(), [3.0, 1.0])
        self.assertEqual(report["rank_cutoff"], 10.0)
        self.assertEqual(report["captured_team_samples"], 2)


if __name__ == "__main__":
    unittest.main()
