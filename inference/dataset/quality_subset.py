"""Quality filtering and weighting for replay decision samples.

The rank belongs to the team whose replay was captured. A replay contains both
players' views, so rank filtering must also select the captured team's side;
filtering an episode while retaining both perspectives would reintroduce the
opponent's lower-quality actions.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import numpy as np


RANK_COLUMN = 6
CAPTURE_TEAM_INDEX_COLUMN = 7
IS_CAPTURE_TEAM_COLUMN = 8


def normalize_team_name(value) -> str:
    value = str(value or '').strip().lower()
    value = value.lstrip('@')
    return re.sub(r'[^a-z0-9]+', '', value)


def captured_team_index(agent_names, captured_team_name) -> int:
    target = normalize_team_name(captured_team_name)
    if not target:
        return -1
    for index, name in enumerate(agent_names or []):
        if normalize_team_name(name) == target:
            return index
    return -1


def _rank_cutoff(episode_ids, ranks, top_ratio):
    rank_by_episode = {}
    for episode_id, rank in zip(episode_ids, ranks):
        if float(rank) > 0:
            rank_by_episode.setdefault(str(episode_id), float(rank))
    ordered = sorted(set(rank_by_episode.values()))
    if not ordered:
        return None
    count = max(1, int(np.ceil(len(ordered) * float(top_ratio))))
    return float(ordered[min(count, len(ordered)) - 1])


def build_sample_selection(
    episode_ids,
    meta,
    *,
    top_ratio=0.5,
    captured_team_only=True,
    win_bonus=1.5,
    late_turn_start=10,
    late_turn_bonus=1.25,
):
    episode_ids = np.asarray(episode_ids).astype(str)
    meta = np.asarray(meta)
    if len(episode_ids) != len(meta):
        raise ValueError('episode_ids and meta must have the same length')
    if meta.ndim != 2 or meta.shape[1] <= IS_CAPTURE_TEAM_COLUMN:
        raise ValueError(
            'meta lacks captured-team columns; re-run extract.py before quality filtering'
        )
    ranks = meta[:, RANK_COLUMN]
    cutoff = _rank_cutoff(episode_ids, ranks, top_ratio)
    if cutoff is None:
        raise ValueError('no valid rank_at_capture values found')
    selected = (ranks > 0) & (ranks <= cutoff)
    if captured_team_only:
        selected &= meta[:, IS_CAPTURE_TEAM_COLUMN] == 1
    indices = np.flatnonzero(selected).astype(np.int64)
    weights = np.ones(len(indices), dtype=np.float32)
    if len(indices):
        rewards = meta[indices, 2]
        turns = meta[indices, 3]
        weights *= np.where(rewards > 0, float(win_bonus), 1.0).astype(np.float32)
        weights *= np.where(turns >= late_turn_start, float(late_turn_bonus), 1.0).astype(np.float32)
    report = {
        'top_ratio': float(top_ratio),
        'rank_cutoff': cutoff,
        'captured_team_only': bool(captured_team_only),
        'win_bonus': float(win_bonus),
        'late_turn_start': int(late_turn_start),
        'late_turn_bonus': float(late_turn_bonus),
        'input_decisions': int(len(meta)),
        'input_episodes': int(len(set(episode_ids.tolist()))),
        'selected_decisions': int(len(indices)),
        'selected_episodes': int(len(set(episode_ids[indices].tolist()))) if len(indices) else 0,
        'captured_team_samples': int((selected).sum()),
        'winner_samples': int((meta[indices, 2] > 0).sum()) if len(indices) else 0,
        'mean_weight': float(weights.mean()) if len(weights) else 0.0,
    }
    return indices, weights, report


def main() -> int:
    parser = argparse.ArgumentParser(description='Build a rank-filtered AWR sample index')
    parser.add_argument('--data-dir', required=True)
    parser.add_argument('--output-dir', required=True)
    parser.add_argument('--top-ratio', type=float, default=0.5)
    parser.add_argument('--win-bonus', type=float, default=1.5)
    parser.add_argument('--late-turn-start', type=int, default=10)
    parser.add_argument('--late-turn-bonus', type=float, default=1.25)
    parser.add_argument('--include-opponent-side', action='store_true')
    args = parser.parse_args()
    data_dir = Path(args.data_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    episode_ids = np.asarray(np.load(data_dir / 'episode_ids.npy', allow_pickle=True)).astype(str)
    meta = np.load(data_dir / 'meta.npy', mmap_mode='r')
    indices, weights, report = build_sample_selection(
        episode_ids,
        meta,
        top_ratio=args.top_ratio,
        captured_team_only=not args.include_opponent_side,
        win_bonus=args.win_bonus,
        late_turn_start=args.late_turn_start,
        late_turn_bonus=args.late_turn_bonus,
    )
    np.save(output_dir / 'sample_indices.npy', indices)
    full_weights = np.zeros(len(episode_ids), dtype=np.float32)
    full_weights[indices] = weights
    np.save(output_dir / 'sample_weights.npy', full_weights)
    (output_dir / 'sample_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8'
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
