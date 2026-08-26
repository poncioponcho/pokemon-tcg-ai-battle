#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""bench_prefetch.py — 隔离测纯数据管道吞吐（不跑模型）。

目的：在本地 Mac 用全量 14GB mmap 复现 T4 上"GPU 等数据"的机制。
对比三种 batch 供应方式，测量每 batch 的 gather+pin 耗时与吞吐：
  A. legacy 全局随机 perm（现状）
  B. 物理连续块 + 块内 shuffle（设计修正版），单线程
  C. 物理连续块 + 块内 shuffle，多 worker（2/3/4）

用法:
  python3 bench_prefetch.py [--n 1000000] [--bs 16384] [--block 8] [--workers 2]
"""
import argparse
import queue
import sys
import threading
import time
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import train_v2  # noqa: E402  (make_blocked_perm, BatchPrefetcher)

DATA = Path(__file__).resolve().parent / 'data'


def load_arrays(n):
    arrays = {}
    for name in ('states_u8', 'scalars', 'opts_u8', 'labels', 'masks'):
        p = DATA / f'{name}.npy'
        arrays[name] = np.load(str(p), mmap_mode='r')
    return {k: v[:n] for k, v in arrays.items()}


def bench_mode(name, arrays, perm, bs, workers, depth):
    n = len(perm)
    meta = {}
    pref = train_v2.BatchPrefetcher(perm, n, bs, arrays, meta, 'bc', 'cpu',
                                    workers=workers, depth=depth)
    t0 = time.perf_counter()
    batches = 0
    for st, sc, op, lb, mk, _rw in pref:
        batches += 1
    dt = time.perf_counter() - t0
    gb = (st.numel() + op.numel() + sc.numel()) * 1  # bytes (uint8-ish est.)
    per_batch = dt / max(batches, 1) * 1000
    print(f'{name:36s} batches={batches:4d} total={dt:7.2f}s '
          f'per_batch={per_batch:7.1f}ms '
          f'thru={n / dt / 1e6:8.2f}Mrow/s', flush=True)
    pref.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--n', type=int, default=1_000_000)
    ap.add_argument('--bs', type=int, default=16384)
    ap.add_argument('--block', type=int, default=8)
    args = ap.parse_args()
    torch.set_num_threads(1)

    split = np.arange(args.n)
    arrays = load_arrays(args.n)
    print(f'data: {args.n} rows | states {arrays["states_u8"].nbytes/1e9:.1f}GB '
          f'opts {arrays["opts_u8"].nbytes/1e9:.1f}GB (mmap)', flush=True)

    # warm page cache once (read full states through once, sequential)
    t = time.perf_counter()
    _ = np.sum(arrays['states_u8'][::16])  # touch ~1/16 of file
    print(f'warm: touch states {time.perf_counter()-t:.1f}s', flush=True)

    perm_a = np.random.permutation(split)
    bench_mode('A legacy global-random', arrays, perm_a, args.bs, 1, 2)

    perm_b = train_v2.make_blocked_perm(split, args.bs, block_mult=args.block)
    bench_mode('B blocked (block=%d) w=1' % args.block, arrays, perm_b, args.bs, 1, 2)
    bench_mode('C blocked (block=%d) w=2' % args.block, arrays, perm_b, args.bs, 2, 4)
    bench_mode('C blocked (block=%d) w=4' % args.block, arrays, perm_b, args.bs, 4, 4)


if __name__ == '__main__':
    main()
