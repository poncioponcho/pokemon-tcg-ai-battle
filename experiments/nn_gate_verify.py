#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""nn_gate_verify.py — 主线B 重训 student 的四道门核验
=====================================================
门①: teacher canary top1 > 0.55 (数据对齐有效性; 读 train_v2_report.json)
门②: student vs teacher canary top1 损失 < 3pp (蒸馏 fidelity)
门③: 本地 nn_first 模式 vs 纯规则 mirror wr > 0.50 (NN 须在分布内超规则;
     先后手轮换, n=8000, seed0=9000, 与复验同口径)
门④: hybrid(rerank) mirror ci_lo>0.5 且 invalid=0, vs_first 不回退
     (对照 vs_first 基线 0.3414, 容差 2pp)

用法:
  python3 experiments/nn_gate_verify.py [report=reports/kerr_selfplay/output/data/train_v2_report.json]
  前置: model_student.npz 已放仓库根目录
"""
import importlib.util
import json
import os
import sys
from pathlib import Path

EXP = Path(__file__).resolve().parent
PROJ = EXP.parent
sys.path.insert(0, str(EXP))
import arena_runner as ar  # noqa: E402

report_path = Path(sys.argv[1]) if len(sys.argv) > 1 else \
    PROJ / 'reports/kerr_selfplay/output/data/train_v2_report.json'
N = int(os.environ.get('GATE_N', '8000'))
SEED0 = int(os.environ.get('GATE_SEED0', '9000'))

OUR_DECK = [int(l.strip()) for l in (PROJ / 'deck.csv').read_text().splitlines() if l.strip()]


def load_main(nn_mode):
    os.environ['PTCG_NN_MODE'] = nn_mode
    spec = importlib.util.spec_from_file_location(f'main_{nn_mode}_{id(nn_mode)}',
                                                  PROJ / 'main.py')
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def wr_of(r):
    tot = r['wins'] + r['losses'] + r['draws']
    wr = r['wins'] / tot if tot else 0.0
    return wr, ar.wilson_ci_lo(wr, tot), tot


def main():
    gates = {}
    # ---- 门①②: 训练报告 ----
    if report_path.exists():
        rep = json.loads(report_path.read_text())
        t_top1 = rep['teacher']['canary']['top1']
        s_top1 = rep['student']['canary']['top1']
        gates['g1_teacher_top1'] = {'value': round(t_top1, 4), 'pass': t_top1 > 0.55}
        gates['g2_distill_loss'] = {'value': round(t_top1 - s_top1, 4),
                                    'pass': (t_top1 - s_top1) < 0.03}
        print(f'[门①] teacher canary top1={t_top1:.4f} (>0.55?) -> {gates["g1_teacher_top1"]["pass"]}')
        print(f'[门②] distill loss={t_top1 - s_top1:.4f} (<0.03?) -> {gates["g2_distill_loss"]["pass"]}')
    else:
        print(f'[门①②] 报告缺失: {report_path} — 跳过', flush=True)
        gates['g1_teacher_top1'] = {'value': None, 'pass': None}
        gates['g2_distill_loss'] = {'value': None, 'pass': None}

    assert (PROJ / 'model_student.npz').exists(), 'model_student.npz 不在仓库根目录'

    # ---- 门③: nn_first vs 纯规则 ----
    m_nn = load_main('nn_first')
    m_off = load_main('off')
    r = ar.run_arena(m_nn.agent, m_off.agent, OUR_DECK, OUR_DECK, N, seed0=SEED0)
    wr, lo, tot = wr_of(r)
    gates['g3_nn_first_mirror'] = {'wr': round(wr, 4), 'ci_lo': round(lo, 4),
                                   'invalid': r['invalid'], 'n': tot,
                                   'pass': wr > 0.50 and r['invalid'] == 0}
    print(f'[门③] nn_first vs rules mirror: wr={wr:.4f} ci_lo={lo:.4f} '
          f'invalid={r["invalid"]} (n={tot}) -> {gates["g3_nn_first_mirror"]["pass"]}',
          flush=True)

    # ---- 门④: hybrid rerank 双对局 ----
    m_hyb = load_main('rerank')
    r1 = ar.run_arena(m_hyb.agent, m_off.agent, OUR_DECK, OUR_DECK, N, seed0=SEED0)
    wr1, lo1, tot1 = wr_of(r1)
    first = ar.builtin_agent('first')
    r2 = ar.run_arena(m_hyb.agent, first, OUR_DECK, ar.SAMPLE_DECK, N, seed0=SEED0)
    wr2, lo2, tot2 = wr_of(r2)
    g4a = lo1 > 0.5 and r1['invalid'] == 0
    g4b = r2['invalid'] == 0 and wr2 >= 0.3414 - 0.02
    gates['g4_hybrid'] = {'mirror_wr': round(wr1, 4), 'mirror_ci_lo': round(lo1, 4),
                          'mirror_invalid': r1['invalid'],
                          'vs_first_wr': round(wr2, 4), 'vs_first_invalid': r2['invalid'],
                          'pass': g4a and g4b}
    print(f'[门④] hybrid mirror wr={wr1:.4f} ci_lo={lo1:.4f} inv={r1["invalid"]} | '
          f'vs_first wr={wr2:.4f} inv={r2["invalid"]} -> {gates["g4_hybrid"]["pass"]}',
          flush=True)

    verdict = all(g['pass'] for g in gates.values() if g['pass'] is not None)
    print(f'verdict: {"PASS" if verdict else "FAIL"}', flush=True)
    out = EXP / 'runs' / 'nn_gate_verify.json'
    out.write_text(json.dumps({'gates': gates, 'verdict': verdict,
                               'n': N, 'seed0': SEED0}, ensure_ascii=False, indent=1))
    sys.exit(0 if verdict else 1)


if __name__ == '__main__':
    main()
