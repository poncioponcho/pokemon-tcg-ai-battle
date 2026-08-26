#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""eval_lb_student.py — C-0 决定性复验（v2, 无 canary 突变）
=================================================================
独立复验 kerr_selfplay 云端 ckpt 在 LB human canary 上的 top1。
v2 改动: canary 从显式 JSON 快照读取, 不走 refresh_rolling_canary
（该函数会按最新捕获剧集重写 live manifest——08-13 已发生一次非预期
滚动, 新旧 canary 0/100 重叠, 两版快照均已存 experiments/bc_fidelity/）。
用法:
  /opt/homebrew/bin/python3 experiments/bc_fidelity/eval_lb_student.py \
      --arch student --ckpt reports/kerr_selfplay/ckpt/student_best.pt \
      --canary-json experiments/bc_fidelity/canary_snapshot_20260809_cloud.json
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import torch

EXP = Path(__file__).resolve().parent
PROJ = EXP.parent.parent
DS = PROJ / 'inference' / 'dataset'
sys.path.insert(0, str(DS))

import train_bc  # noqa: E402
import train_v2  # noqa: E402
from mlops_registry import ensure_split_manifest  # noqa: E402
from model_v2 import PolicyStudent, PolicyTeacher  # noqa: E402

EXPECT = {'student': 1_993_537, 'teacher': 9_532_033}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--arch', choices=['student', 'teacher'], default='student')
    ap.add_argument('--ckpt', required=True)
    ap.add_argument('--canary-json', required=True)
    args = ap.parse_args()
    device = 'cpu'

    arrays, meta, episode_ids, n = train_v2.load_arrays(DS / 'data', 0)
    # fixed_test: 直接调 ensure_split_manifest（manifest 已存在时只读, 已实证不改写）
    assignments = ensure_split_manifest(episode_ids, str(DS / 'splits/episode_splits.jsonl'))
    fixed_ids = {eid for eid, s in assignments.items() if s == 'fixed_test'}
    eval_idx = np.where(np.isin(episode_ids, list(fixed_ids)))[0]
    # canary: 显式快照, 零写副作用
    canary_ids = set(str(v) for v in json.loads(Path(args.canary_json).read_text())['episode_ids'])
    canary_idx = np.where(np.isin(episode_ids, list(canary_ids)))[0]
    print(f'n_decisions={n} fixed={len(eval_idx)} canary={len(canary_idx)}', flush=True)

    div = train_bc.DIV.clone()
    if args.arch == 'student':
        model = PolicyStudent(train_v2.ST_DIM, train_v2.SC_DIM, train_v2.O_DIM, train_v2.K,
                              hidden=384, div=div).to(device)
    else:
        model = PolicyTeacher(train_v2.ST_DIM, train_v2.SC_DIM, train_v2.O_DIM, train_v2.K,
                              hidden=1024, blocks=2, dropout=0.10, div=div).to(device)
    n_params = sum(p.numel() for p in model.parameters())
    print(f'{args.arch} params={n_params:,} (expect {EXPECT[args.arch]:,})', flush=True)
    assert n_params == EXPECT[args.arch], '参数量不符=架构与训练时不一致, 结果不可比'

    payload = torch.load(args.ckpt, map_location=device, weights_only=False)
    sd = payload.get('model', payload) if isinstance(payload, dict) else payload
    model.load_state_dict(sd)
    model.eval()

    ev_fixed, _, _ = train_bc.evaluate(model, arrays, eval_idx, meta, device)
    print(f'fixed_top1={ev_fixed["top1"]:.4f} recall={ev_fixed["recall"]:.4f}', flush=True)
    ev_can, _, _ = train_bc.evaluate(model, arrays, canary_idx, meta, device)
    print(f'RESULT arch={args.arch} ckpt={args.ckpt} canary={Path(args.canary_json).name} '
          f'canary_top1={ev_can["top1"]:.4f} fixed_top1={ev_fixed["top1"]:.4f}', flush=True)


if __name__ == '__main__':
    main()
