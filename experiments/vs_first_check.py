#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""vs_first_check.py — 旧默认参数 vs first 基线补测 (对照 incumbent final 的 vs_first=0.3534)
用法: python3 experiments/vs_first_check.py [n=8000] [seed0=9000] [bak=main.py.bak-2026-08-09-tune]"""
import os, sys
from pathlib import Path
os.environ['PTCG_NN_MODE'] = 'off'
EXP = Path(__file__).resolve().parent
PROJ = EXP.parent
sys.path.insert(0, str(EXP))
import arena_runner as ar  # noqa: E402

n = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
seed0 = int(sys.argv[2]) if len(sys.argv) > 2 else 9000
bak = sys.argv[3] if len(sys.argv) > 3 else 'main.py.bak-2026-08-09-tune'

bak_path = PROJ / bak
if bak_path.suffix != '.py':
    import shutil
    tmp = EXP / 'runs' / '_verify_old_main.py'
    shutil.copyfile(bak_path, tmp)
    bak_path = tmp
old = ar.load_module(bak_path)

OUR_DECK = [int(l.strip()) for l in (PROJ / 'deck.csv').read_text().splitlines() if l.strip()]
SAMPLE = ar.SAMPLE_DECK
r = ar.run_arena(old.agent, ar.builtin_agent('first'), OUR_DECK, SAMPLE, n, seed0=seed0)
tot = r['wins'] + r['losses'] + r['draws']
wr = r['wins'] / tot if tot else 0.0
lo = ar.wilson_ci_lo(wr, tot)
print(f'旧默认 vs first: wr={wr:.4f} ci_lo={lo:.4f} invalid={r["invalid"]} (n={tot}, seed0={seed0})')
print('对照: 新 incumbent final vs_first=0.3534 → 若旧默认>=0.3534 则新参数在先手位有退步')
