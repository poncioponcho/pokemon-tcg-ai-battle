"""Produce controller metrics from the frozen test and rolling canary tensors."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import numpy as np
import torch

try:
    from .mlops_registry import (
        EpisodeCatalog,
        ensure_split_manifest,
        population_stability_index,
    )
    from . import train_bc
except ImportError:  # Direct script execution.
    from mlops_registry import EpisodeCatalog, ensure_split_manifest, population_stability_index  # type: ignore
    import train_bc  # type: ignore


def _load_arrays(data_dir: Path) -> dict[str, np.ndarray]:
    names = ('states_u8', 'scalars', 'opts_u8', 'labels', 'masks')
    return {name: np.load(data_dir / f'{name}.npy', mmap_mode='r') for name in names}


def _meta(data_dir: Path) -> dict[str, np.ndarray]:
    value = np.load(data_dir / 'meta.npy', mmap_mode='r')
    keys = ('ep', 'persp', 'reward', 'turn', 'ctx', 'nopts', 'rank_at_capture')
    return {
        key: value[:, index] if index < value.shape[1] else np.full(len(value), -1.0)
        for index, key in enumerate(keys)
    }


def _episode_indices(data_dir: Path, split_path: Path, canary_path: Path):
    episode_ids = np.asarray(np.load(data_dir / 'episode_ids.npy', allow_pickle=True)).astype(str)
    assignments = ensure_split_manifest(episode_ids, split_path)
    fixed = {episode_id for episode_id, split in assignments.items() if split == 'fixed_test'}
    canary_value = json.loads(canary_path.read_text(encoding='utf-8')) if canary_path.exists() else {}
    canary = set(str(value) for value in canary_value.get('episode_ids', []))
    return episode_ids, fixed, canary


def run(args) -> dict:
    data_dir = Path(args.data_dir)
    arrays = _load_arrays(data_dir)
    meta = _meta(data_dir)
    episode_ids, fixed_ids, canary_ids = _episode_indices(
        data_dir, Path(args.split_manifest), Path(args.canary_manifest)
    )
    fixed_idx = np.where(np.isin(episode_ids, list(fixed_ids)))[0]
    canary_idx = np.where(np.isin(episode_ids, list(canary_ids)))[0]
    if len(fixed_idx) == 0 or len(canary_idx) == 0:
        raise RuntimeError('Both fixed_test and rolling_canary must contain decisions')

    model = train_bc.Policy()
    model.load_state_dict(torch.load(args.model, map_location='cpu'))
    model.eval()
    fixed_eval, _, _ = train_bc.evaluate(model, arrays, fixed_idx, meta, 'cpu')
    canary_eval, _, _ = train_bc.evaluate(model, arrays, canary_idx, meta, 'cpu')

    # Scalar features are compact and cover the observable game-state drift.
    scalar_columns = (0, 1, 2, 3, 8, 9, 10, 23, 24, 29, 30)
    psi_by_column = {
        str(column): population_stability_index(
            arrays['scalars'][fixed_idx, column],
            arrays['scalars'][canary_idx, column],
        )
        for column in scalar_columns
    }
    return {
        'base_episode_count': len(fixed_ids) + len(set(episode_ids) - fixed_ids - canary_ids),
        'new_episode_count': int(args.new_episode_count),
        'canary_episode_count': len(canary_ids),
        'baseline_accuracy': fixed_eval['top1'],
        'canary_accuracy': canary_eval['top1'],
        'psi': max(psi_by_column.values()) if psi_by_column else 0.0,
        'psi_by_scalar_column': psi_by_column,
        'fixed_test_decisions': len(fixed_idx),
        'canary_decisions': len(canary_idx),
        'card_vocab_version': train_bc.VOCAB['version'],
    }


def main() -> int:
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description='Evaluate fixed test vs rolling canary')
    parser.add_argument('--data-dir', default=str(root / 'data'))
    parser.add_argument('--model', default=str(root / 'data' / 'model_awr.pt'))
    parser.add_argument('--split-manifest', default=str(root / 'splits' / 'episode_splits.jsonl'))
    parser.add_argument('--canary-manifest', default=str(root / 'splits' / 'rolling_canary.json'))
    parser.add_argument('--new-episode-count', type=int, default=0)
    parser.add_argument('--output', default=None)
    args = parser.parse_args()
    metrics = run(args)
    text = json.dumps(metrics, ensure_ascii=False, indent=2)
    print(text)
    if args.output:
        Path(args.output).write_text(text + '\n', encoding='utf-8')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
