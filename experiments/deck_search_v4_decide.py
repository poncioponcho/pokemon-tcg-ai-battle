#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""deck_search_v4_decide.py — v4 FINAL 的 3 种子标准闸决策报告 (不提交)。

peer 2026-08-10 09:50 设计要点:
  ⚠️ 不信 deck_final_verify_v4.py 自带 verdict (它的门禁 lo>0.5 / wr>=0.3214
     比 3 种子标准闸松得多, 直接读会给假阳性 PASS)。本脚本只取它每颗种子的
     原始指标 JSON, 闸门自己判 (ledger#76):
       硬闸 = 卡池快败(verify 脚本 exit 1) + mirror invalid==0
              + vs_first invalid==0 + mirror ci_lo>0.5
       接受 = mirror.wr ≥ 0.7465  OR  (vs_first.wr ≥ 0.4564 AND mirror.wr ≥ 0.7095)
       3 种子 (9000/9001/9002) 全过 → 总闸 PASS
  标杆 = 55390992 闸值: mirror 0.7679-0.7788 / vs_first 0.5009-0.5122 (同口径 leg)。
  分类 = STRONG / MARGINAL / REGRESS / GATE-FAIL。
  幂等安全: deck.csv 备份-写入-finally恢复; 绝不提交, 绝不改 main.py。

用法: python3 experiments/deck_search_v4_decide.py [--log deck_search_v5.jsonl]
       [--bench-mirror lo,hi] [--bench-vf lo,hi] [--bench-name NAME]
  标杆默认 55390992 闸值; 对 v4 FINAL 之后的搜索, 应传现役标杆:
  v4 FINAL (ledger#82): --bench-mirror 0.7943,0.8084 --bench-vf 0.5234,0.5258 --bench-name v4FINAL
退出码: 0=报告已生成(任何分类)  2=v4 未跑完/无 FINAL
"""
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

EXP = Path(__file__).resolve().parent
PROJ = EXP.parent
RUNS = EXP / 'runs'
PY = '/opt/homebrew/bin/python3'

LOG_NAME = sys.argv[sys.argv.index('--log') + 1] if '--log' in sys.argv else 'deck_search_v4.jsonl'


def _arg_pair(flag):
    """解析 --flag lo,hi 形式的浮点区间参数; 未传返回 None"""
    if flag in sys.argv:
        lo, hi = sys.argv[sys.argv.index(flag) + 1].split(',')
        return (float(lo), float(hi))
    return None


BENCH_NAME = (sys.argv[sys.argv.index('--bench-name') + 1]
              if '--bench-name' in sys.argv else '55390992')

SEEDS = [9000, 9001, 9002]
N = 8000
# 3 种子标准闸阈值 (ledger#76)
MIRROR_ACC = 0.7465
VF_ACC = 0.4564
VF_ACC_MIRROR_FLOOR = 0.7095
# 标杆 (3 种子范围): 默认 55390992; 现役标杆用 --bench-* 传入 (M1 修复 08-10)
BENCH_MIRROR = _arg_pair('--bench-mirror') or (0.7679, 0.7788)
BENCH_VF = _arg_pair('--bench-vf') or (0.5009, 0.5122)
NOISE = 0.017


def fail(msg, code=2):
    print(f'[decide] {msg}', flush=True)
    sys.exit(code)


def main():
    log = RUNS / LOG_NAME
    if not log.exists():
        fail(f'{LOG_NAME} 不存在 — 搜索未点火?')

    final = None
    for ln in log.read_text(encoding='utf-8').splitlines():
        try:
            ev = json.loads(ln)
        except Exception:
            continue
        if ev.get('ev') == 'final' and isinstance(ev.get('deck'), list):
            final = ev
    if final is None:
        # 进程还活着?
        pid_f = RUNS / (LOG_NAME.replace('.jsonl', '.pid'))
        alive = False
        if pid_f.exists():
            try:
                import os
                os.kill(int(pid_f.read_text().strip()), 0)
                alive = True
            except Exception:
                pass
        fail(f'无 FINAL 事件 (v4 进程{"仍在运行" if alive else "已退出但未产 FINAL — 查日志"})')

    deck = final['deck']
    if len(deck) != 60:
        fail(f'FINAL deck 长度 {len(deck)} != 60 — 数据异常')
    print(f'[decide] v4 FINAL deck: {sorted(deck)}', flush=True)
    print(f'[decide] 搜索尺度指标: vs_orig_mirror={final.get("vs_orig_mirror_wr")} '
          f'vs_first={final.get("vs_first_wr")} — 仅供参考, 以 3 种子闸为准', flush=True)

    # ---- 换牌组 (备份/finally恢复) ----
    deck_csv = PROJ / 'deck.csv'
    ts = time.strftime('%Y%m%d-%H%M%S')
    bak = PROJ / f'deck.csv.bak-decide-{ts}'
    orig_text = deck_csv.read_text()
    shutil.copyfile(deck_csv, bak)
    deck_csv.write_text('\n'.join(str(c) for c in deck) + '\n')
    print(f'[decide] deck.csv 已备份 {bak.name} 并写入 v4 FINAL', flush=True)

    per_seed = {}
    try:
        for seed in SEEDS:
            print(f'[decide] --- seed {seed}: verify n={N} ---', flush=True)
            r = subprocess.run(
                [PY, str(EXP / 'deck_final_verify_v4.py'), str(N), str(seed)],
                cwd=str(PROJ), capture_output=True, text=True, timeout=1800)
            print(r.stdout.strip(), flush=True)
            if r.stderr.strip():
                print(f'[stderr] {r.stderr.strip()[:400]}', flush=True)
            src = RUNS / 'deck_final_verify_v4.json'
            dst = RUNS / f'deck_final_verify_v4_seed{seed}.json'
            if src.exists():
                shutil.copyfile(src, dst)
                res = json.loads(src.read_text())
            else:
                res = {'verdict': 'NO_JSON', 'exit': r.returncode}
            res['exit_code'] = r.returncode
            per_seed[seed] = res
    finally:
        deck_csv.write_text(orig_text)
        assert deck_csv.read_text() == orig_text
        print('[decide] deck.csv 已恢复现役牌组 (校验一致)', flush=True)

    # ---- 自判 3 种子标准闸 (不信 verify 自带 verdict) ----
    lines = []
    all_pass = True
    for seed in SEEDS:
        res = per_seed[seed]
        m = res.get('mirror') or {}
        f_ = res.get('vs_first') or {}
        card_pool_ok = not (res.get('gates', {}).get('card_pool') is False)
        hard = (card_pool_ok
                and m.get('invalid', 1) == 0
                and f_.get('invalid', 1) == 0
                and m.get('ci_lo', 0) > 0.5)
        accept = (m.get('wr', 0) >= MIRROR_ACC
                  or (f_.get('wr', 0) >= VF_ACC and m.get('wr', 0) >= VF_ACC_MIRROR_FLOOR))
        ok = hard and accept
        all_pass = all_pass and ok
        lines.append({'seed': seed, 'mirror_wr': m.get('wr'), 'mirror_ci_lo': m.get('ci_lo'),
                      'vs_first_wr': f_.get('wr'), 'invalid_m': m.get('invalid'),
                      'invalid_f': f_.get('invalid'), 'card_pool_ok': card_pool_ok,
                      'hard': hard, 'accept': accept, 'pass': ok})

    # ---- 标杆对比分类 ----
    if not all_pass:
        cls = 'GATE-FAIL'
    else:
        strong = all(l['mirror_wr'] >= BENCH_MIRROR[1] and l['vs_first_wr'] >= BENCH_VF[1]
                     for l in lines)
        regress = any(l['mirror_wr'] < BENCH_MIRROR[0] - NOISE
                      or l['vs_first_wr'] < BENCH_VF[0] - NOISE for l in lines)
        cls = 'STRONG' if strong else ('REGRESS' if regress else 'MARGINAL')

    advice = {
        'STRONG': f'三种子双指标全超 {BENCH_NAME} 标杆上限 — 建议提交 (仍需用户显式确认)',
        'MARGINAL': '过闸但落在标杆噪声带内 — 改进不可证, 建议 HOLD 保额度',
        'REGRESS': f'过绝对闸但低于 {BENCH_NAME} 标杆 (超噪声带) — 建议 HOLD, 不提交',
        'GATE-FAIL': '未过 3 种子标准闸 — 不提交, 分析失败腿',
    }[cls]

    # ---- markdown 报告 ----
    tag = LOG_NAME.replace('.jsonl', '')
    md = [f'# {tag} 决策报告', '',
          f'- 生成: {time.strftime("%Y-%m-%d %H:%M:%S")}',
          f'- v4 FINAL deck: `{sorted(deck)}`',
          f'- 搜索尺度 (参考): vs_orig_mirror={final.get("vs_orig_mirror_wr")} '
          f'vs_first={final.get("vs_first_wr")}',
          f'- 标杆 {BENCH_NAME}: mirror {BENCH_MIRROR[0]}-{BENCH_MIRROR[1]} / '
          f'vs_first {BENCH_VF[0]}-{BENCH_VF[1]}', '',
          '| seed | mirror_wr | mirror_ci_lo | vs_first_wr | invalid(m/f) | 硬闸 | 接受 | PASS |',
          '|---|---|---|---|---|---|---|---|']
    for l in lines:
        md.append(f"| {l['seed']} | {l['mirror_wr']} | {l['mirror_ci_lo']} | "
                  f"{l['vs_first_wr']} | {l['invalid_m']}/{l['invalid_f']} | "
                  f"{'✓' if l['hard'] else '✗'} | {'✓' if l['accept'] else '✗'} | "
                  f"{'✓' if l['pass'] else '✗'} |")
    md += ['', f'## 分类: **{cls}**', '', advice, '',
           '⚠️ 本报告不提交、不改 main.py。提交需用户显式确认 (ledger#76, '
           '08:00 免确认窗口已过)。', '']
    rpt = RUNS / f'{tag}_decision.md'
    rpt.write_text('\n'.join(md), encoding='utf-8')

    entry = {'ts': time.time(), 'event': f'{tag}_gate_report',
             'final_deck': sorted(deck),
             'search_scale': {'vs_orig_mirror': final.get('vs_orig_mirror_wr'),
                              'vs_first': final.get('vs_first_wr')},
             'seeds': lines, 'gate_pass': all_pass, 'classification': cls,
             'advice': advice, 'report': str(rpt),
             'note': 'awaiting 用户显式确认, 未提交'}
    with open(EXP / 'ledger.jsonl', 'a', encoding='utf-8') as f:
        f.write(json.dumps(entry, ensure_ascii=False) + '\n')

    print(f'\n[decide] === 分类: {cls} === {advice}', flush=True)
    print(f'[decide] 报告: {rpt}', flush=True)
    print('[decide] deck.csv 现役牌组完好, 未提交。 awaiting 用户显式确认。', flush=True)


if __name__ == '__main__':
    main()
