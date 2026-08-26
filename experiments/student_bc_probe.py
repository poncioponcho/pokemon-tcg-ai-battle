#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""student_bc_probe.py — student 直接 BC 探针（跳过 teacher 蒸馏的二次损失）
=========================================================================
动机: v3 链路 data→teacher(0.77)→student(0.65) 蒸馏保真崩盘 (-12pp)。
假设: student 直接在胜方数据上 BC, 保真上限可能高于经 teacher 中转。
复用 train_v2.run_phase ('bc' 相位), 评估 fixed_test/canary top1。

用法: /opt/homebrew/bin/python3 experiments/student_bc_probe.py [--hidden 384] [--epochs 16]
"""
import argparse
import re
import sys
import tempfile
from pathlib import Path

import numpy as np
import torch

EXP = Path(__file__).resolve().parent
PROJ = EXP.parent
DS = PROJ / 'inference' / 'dataset'
sys.path.insert(0, str(DS))
sys.path.insert(0, str(EXP))

import train_bc  # noqa: E402
import train_v2  # noqa: E402
from model_v2 import PolicyStudent  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--hidden', type=int, default=384)
    ap.add_argument('--epochs', type=int, default=16)
    ap.add_argument('--bs', type=int, default=8192)
    ap.add_argument('--lr', type=float, default=1e-3)
    ap.add_argument('--device', default='auto')
    ap.add_argument('--tag', default='')
    args_cli = ap.parse_args()

    device = train_v2.resolve_device(args_cli.device)
    print(f'device: {device}', flush=True)

    data_dir = DS / 'data-selfplay'
    arrays, meta, episode_ids, n = train_v2.load_arrays(data_dir, 0)

    ns = argparse.Namespace(
        split_manifest=str(DS / 'splits-selfplay' / 'episode_splits.jsonl'),
        canary_manifest=str(DS / 'splits-selfplay' / 'rolling_canary.json'),
        canary_episodes=100)
    train_idx, eval_idx, canary_idx = train_v2.split_indices(ns, episode_ids)
    si = np.asarray(np.load(DS / 'data-selfplay-quality' / 'sample_indices.npy'), dtype=np.int64)
    bc_idx = train_bc.restrict_split_to_samples(train_idx, si)
    print(f'total {n} | train {len(train_idx)} | bc(winner) {len(bc_idx)} | '
          f'fixed {len(eval_idx)} | canary {len(canary_idx)}', flush=True)

    div = train_bc.DIV.clone()
    student = PolicyStudent(train_v2.ST_DIM, train_v2.SC_DIM, train_v2.O_DIM, train_v2.K,
                            hidden=args_cli.hidden, div=div).to(device)
    print(f'student params (hidden={args_cli.hidden}): '
          f'{sum(p.numel() for p in student.parameters()):,}', flush=True)

    opt = torch.optim.Adam(student.parameters(), lr=args_cli.lr, weight_decay=1e-4)
    scaler = torch.amp.GradScaler('cuda', enabled=(device == 'cuda'))
    run_args = argparse.Namespace(
        bs=args_cli.bs, early_stop_patience=3, eval_every=1,
        distill_temp=3.0, distill_alpha=0.3, tau=0.5, wcap=20.0,
        prefetch_workers=1, prefetch_depth=2, prefetch_block=8,
        profile=False)
    tag = args_cli.tag or f'h{args_cli.hidden}'
    safe_tag = re.sub(r'[^A-Za-z0-9_.-]+', '_', tag)[:64] or 'run'
    run_dir = Path(tempfile.mkdtemp(prefix=f'student_bc_probe_{safe_tag}_'))
    ckpt = run_dir / 'checkpoint.pt'
    best = run_dir / 'best.pt'

    with (run_dir / 'train.log').open('w', encoding='utf-8') as logf:
        h, _stopper = train_v2.run_phase(
            student, opt, scaler, arrays, meta, bc_idx, args_cli.epochs, 'bc',
            run_args, device, logf, canary_idx, ckpt, best,
            start_epoch=0, teacher=None)
    for r in h:
        print(f"[bc] ep{r['epoch']} loss {r['loss']:.4f} "
              f"canary {r.get('monitor', {}).get('top1', 0):.4f}", flush=True)

    student.load_state_dict(torch.load(best, map_location=device, weights_only=True))
    ev_fixed, _, _ = train_bc.evaluate(student, arrays, eval_idx, meta, device)
    ev_can, _, _ = train_bc.evaluate(student, arrays, canary_idx, meta, device)
    print(f'RESULT tag={tag} hidden={args_cli.hidden} '
          f'fixed_top1={ev_fixed["top1"]:.4f} canary_top1={ev_can["top1"]:.4f} '
          f'best={best} run_dir={run_dir}', flush=True)


if __name__ == '__main__':
    main()
