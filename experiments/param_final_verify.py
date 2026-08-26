#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""param_final_verify.py — 调权 incumbent 写入 main.py 后的独立复验
=================================================================
对照: 当前 main.py(已写入新参数) vs 指定备份(旧默认) 的镜像对局。
门  : Wilson ci_lo > 0.5 且 invalid == 0 (与 param_tune final 同种子 seed0=9000)。

用法: python3 experiments/param_final_verify.py [n=8000] [seed0=9000] [bak=main.py.bak-2026-08-09-tune]
"""
import os
import sys
from pathlib import Path

os.environ['PTCG_NN_MODE'] = 'off'  # 必须先于 load_module (对齐 param_tune worker)

EXP = Path(__file__).resolve().parent
PROJ = EXP.parent
sys.path.insert(0, str(EXP))
import arena_runner as ar  # noqa: E402

n = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
seed0 = int(sys.argv[2]) if len(sys.argv) > 2 else 9000
bak = sys.argv[3] if len(sys.argv) > 3 else 'main.py.bak-2026-08-09-tune'

new = ar.load_module(PROJ / 'main.py')
bak_path = PROJ / bak
if bak_path.suffix != '.py':
    # importlib 只能加载 .py 后缀: 备份(.bak-*)拷到 runs/ 下临时 .py 再加载
    import shutil
    tmp = EXP / 'runs' / '_verify_old_main.py'
    shutil.copyfile(bak_path, tmp)
    bak_path = tmp
old = ar.load_module(bak_path)
diff = {k: (old._PARAMS.get(k), new._PARAMS.get(k))
        for k in new._PARAMS if old._PARAMS.get(k) != new._PARAMS.get(k)}
print(f'参数差异 (旧→新): {diff}')
assert diff, '未发现参数差异 —— 检查是否已写入 incumbent 或备份选错'

OUR_DECK = [int(l.strip()) for l in (PROJ / 'deck.csv').read_text().splitlines() if l.strip()]
r = ar.run_arena(new.agent, old.agent, OUR_DECK, OUR_DECK, n, seed0=seed0)
tot = r['wins'] + r['losses'] + r['draws']
wr = r['wins'] / tot if tot else 0.0
lo = ar.wilson_ci_lo(wr, tot)
print(f'mirror(新 vs 旧默认): wr={wr:.4f} ci_lo={lo:.4f} invalid={r["invalid"]} '
      f'avg_turns={r["avg_turns"]:.1f} (n={tot}, seed0={seed0})')
verdict = 'PASS' if lo > 0.5 and r['invalid'] == 0 else 'FAIL'
print(f'verdict: {verdict}')
sys.exit(0 if verdict == 'PASS' else 1)
