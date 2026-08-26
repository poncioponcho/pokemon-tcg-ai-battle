#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""measure_tflops.py — 从 --profile 日志 + 模型参数估算 distill 阶段实测 TFLOP/s。

口径（M2 吞吐判据 AC-007）：
  distill 每 epoch 计算 FLOPs ≈ n_train × (2·P_teacher + 2·P_student·3)
    · teacher 前向 1x（no_grad，冻结）
    · student 前向+反向 ≈ 3x（fwd 1x + bwd 2x）
  TFLOP/s = epoch FLOPs / epoch compute 秒数
  其中 epoch compute 秒数 = 每 batch compute_ms/1000 × 每 epoch batch 数
  （--profile 输出里的 compute 段）

用法:
  python3 measure_tflops.py --report train_v2_report.json --log train_v2.log
  python3 measure_tflops.py --report ... --log ... --phase distill --epoch 1
"""
import argparse
import json
import re
import sys
from pathlib import Path


def parse_profile(log_text: str, phase: str) -> tuple[float, int] | None:
    """从日志提取某 phase 的 per-batch compute ms 与 batch 数。

    行格式: [profile] ep{n} {phase}: prepare X% transfer Y% compute Z%
             | per-batch prepare Ams transfer Bms compute Cms (n=N)
    """
    pat = re.compile(
        rf'\[profile\] ep\d+ {phase}: prepare .*?compute\s+\S+% \| per-batch '
        rf'prepare (\d+)ms transfer (\d+)ms compute (\d+)ms \(n=(\d+)\)')
    for line in log_text.splitlines():
        m = pat.search(line)
        if m:
            return float(m.group(3)) / 1000.0, int(m.group(4))  # ms -> s
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--report', required=True, help='train_v2_report.json')
    ap.add_argument('--log', required=True, help='--profile 输出的 train_v2.log')
    ap.add_argument('--phase', default='distill')
    ap.add_argument('--epoch', type=int, default=1)
    args = ap.parse_args()

    report = json.loads(Path(args.report).read_text(encoding='utf-8'))
    n_train = report.get('n_decisions', 0)
    p_teacher = report.get('teacher', {}).get('params', 0)
    p_student = report.get('student', {}).get('params', 0)
    log_text = Path(args.log).read_text(encoding='utf-8')

    parsed = parse_profile(log_text, args.phase)
    if parsed is None:
        print(f'ERROR: 日志中未找到 {args.phase} 的 --profile 行；'
              f'需用 --profile 重跑。', file=sys.stderr)
        sys.exit(1)
    compute_s_per_batch, n_batches = parsed

    flops_epoch = n_train * (2 * p_teacher + 2 * p_student * 3)
    epoch_compute_s = compute_s_per_batch * n_batches
    tflops = flops_epoch / epoch_compute_s / 1e12

    print(f'phase={args.phase}')
    print(f'  n_train           : {n_train:,}')
    print(f'  teacher params    : {p_teacher:,}')
    print(f'  student params    : {p_student:,}')
    print(f'  FLOPs/epoch (est) : {flops_epoch / 1e12:.3f} T')
    print(f'  compute/batch     : {compute_s_per_batch * 1000:.0f}ms x {n_batches} batches')
    print(f'  compute/epoch     : {epoch_compute_s:.1f}s')
    print(f'  => 实测 TFLOP/s   : {tflops:.2f}  (T4 fp16 峰值 ≈65 TFLOPS)')


if __name__ == '__main__':
    main()
