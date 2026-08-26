#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""rule_ab_gate.py — 规则改动 A/B 闸 (同牌组镜像 + vs_first)

用途: 评估 main.py 的规则改动 (不动牌组), 对比基线旧 main。
  leg1 mirror  : new.agent vs old.agent, 双方同用现 deck.csv (同牌组, 纯规则差异)
  leg2 vs_first: new.agent vs builtin('first') (SAMPLE_DECK)
用法: /opt/homebrew/bin/python3 experiments/rule_ab_gate.py <n> <seed0> <old_main_basename> <tag>
例:   rule_ab_gate.py 8000 9000 main.py.bak-20260810-fg fg
产物: experiments/runs/rule_ab_gate_<tag>_<seed0>.json
"""
import json
import os
import sys
import time
from pathlib import Path

os.environ['PTCG_NN_MODE'] = 'off'  # 必须先于 load_module

EXP = Path(__file__).resolve().parent
PROJ = EXP.parent
sys.path.insert(0, str(EXP))
import arena_runner as ar  # noqa: E402

n = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
seed0 = int(sys.argv[2]) if len(sys.argv) > 2 else 9000
old_name = sys.argv[3] if len(sys.argv) > 3 else 'main.py.bak-20260810-fg'
tag = sys.argv[4] if len(sys.argv) > 4 else 'ab'

DECK = [int(l.strip()) for l in (PROJ / 'deck.csv').read_text().splitlines() if l.strip()]
assert len(DECK) == 60

new = ar.load_module(PROJ / 'main.py')
import shutil
# [2026-08-11] 旧 main 副本放独立小目录并配 deck.csv:
# _load_deck 按 __file__ 锚定找同目录 deck.csv, 缺了会打 stderr 脏字并回退内联牌组。
tmpd = EXP / 'runs' / f'_rule_ab_old_{tag}'
tmpd.mkdir(parents=True, exist_ok=True)
shutil.copyfile(PROJ / old_name, tmpd / 'main.py')
shutil.copyfile(PROJ / 'deck.csv', tmpd / 'deck.csv')  # 同牌组 A/B: 旧 main 也用现牌组
old = ar.load_module(tmpd / 'main.py')

out = {'n': n, 'seed0': seed0, 'tag': tag, 'old_main': old_name,
       'ts': time.strftime('%Y-%m-%dT%H:%M:%S')}

# ---- leg1: mirror 同牌组 (新规则 vs 旧规则) ----
r = ar.run_arena(new.agent, old.agent, DECK, DECK, n, seed0=seed0)
tot = r['wins'] + r['losses'] + r['draws']
wr = r['wins'] / tot if tot else 0.0
lo = ar.wilson_ci_lo(wr, tot)
out['mirror'] = {'wr': round(wr, 4), 'ci_lo': round(lo, 4), 'invalid': r['invalid'],
                 'avg_turns': r['avg_turns'], 'n': tot}
print(f'[leg1 mirror] wr={wr:.4f} ci_lo={lo:.4f} invalid={r["invalid"]} '
      f'avg_turns={r["avg_turns"]:.1f} (n={tot})', flush=True)
pass1 = lo > 0.5 and r['invalid'] == 0

# ---- leg2: vs_first (新规则) ----
first = ar.builtin_agent('first')
r2 = ar.run_arena(new.agent, first, DECK, ar.SAMPLE_DECK, n, seed0=seed0)
tot2 = r2['wins'] + r2['losses'] + r2['draws']
wr2 = r2['wins'] / tot2 if tot2 else 0.0
out['vs_first'] = {'wr': round(wr2, 4), 'ci_lo': round(ar.wilson_ci_lo(wr2, tot2), 4),
                   'invalid': r2['invalid'], 'avg_turns': r2['avg_turns'], 'n': tot2}
print(f'[leg2 vs_first] wr={wr2:.4f} invalid={r2["invalid"]} '
      f'avg_turns={r2["avg_turns"]:.1f} (n={tot2})', flush=True)
pass2 = r2['invalid'] == 0

out['verdict'] = 'PASS' if (pass1 and pass2) else 'FAIL'
out['gates'] = {'mirror': pass1, 'vs_first_valid': pass2}
print(f'verdict: {out["verdict"]}', flush=True)

with open(EXP / 'runs' / f'rule_ab_gate_{tag}_{seed0}.json', 'w') as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
sys.exit(0 if out['verdict'] == 'PASS' else 1)
