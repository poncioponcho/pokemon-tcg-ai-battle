#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_splits_selfplay.py — 为自对弈数据集生成 episode_splits + rolling_canary
格式与 mlops_registry 产出一致, train_v2 --split-manifest/--canary-manifest 直接吃。
fixed_test: md5(episode_id)%10==0 (稳定哈希 ~10%); canary: gid 最大 100 个 (剔除 fixed_test)。
用法: python3 experiments/make_splits_selfplay.py [data_dir] [out_dir]
"""
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np

EXP = Path(__file__).resolve().parent
PROJ = EXP.parent

data_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else PROJ / 'inference/dataset/data-selfplay'
out_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else PROJ / 'inference/dataset/splits-selfplay'
out_dir.mkdir(parents=True, exist_ok=True)

episode_ids = sorted(set(np.load(data_dir / 'episode_ids.npy', allow_pickle=True).astype(str).tolist()),
                     key=lambda s: int(s.replace('sp', '')))
now = time.strftime('%Y-%m-%dT%H:%M:%S+00:00', time.gmtime())

def is_test(ep):
    return int(hashlib.md5(ep.encode()).hexdigest(), 16) % 10 == 0

n_test = 0
with open(out_dir / 'episode_splits.jsonl', 'w') as f:
    for ep in episode_ids:
        split = 'fixed_test' if is_test(ep) else 'train'
        n_test += split == 'fixed_test'
        f.write(json.dumps({'assigned_at': now, 'episode_id': ep,
                            'split': split, 'split_version': 'selfplay-v1'}) + '\n')

canary = [ep for ep in episode_ids if not is_test(ep)][-100:]
with open(out_dir / 'rolling_canary.json', 'w') as f:
    json.dump({'generated_at': now, 'split': 'rolling_canary',
               'episode_ids': canary}, f, indent=1)
print(f'episodes={len(episode_ids)} fixed_test={n_test} canary={len(canary)} -> {out_dir}')
