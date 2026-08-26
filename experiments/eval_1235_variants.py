# -*- coding: utf-8 -*-
"""eval_1235_variants.py — ② 1235 入组定向筛选 (peer 2026-08-10 12:33 方案)。

问题: v4 候选面含 1235 却收敛到 -674+1152 — 单卡置换没捞到 1235。
本脚本定向测: v4 FINAL - {每张冗余训练家} + 1235×1, 配对同进程 baseline,
筛出最优变体供 3 种子闸。纯只读: 直接 arena 调用, 不碰 deck.csv/main.py。
"""
import os as _os
import sys as _sys
if _os.environ.get('PYTHONHASHSEED') != '0':
    _os.environ['PYTHONHASHSEED'] = '0'
    _os.execv(_sys.executable, [_sys.executable] + _sys.argv)

import json
import sys
import time
from pathlib import Path

EXP = Path('/Users/seyonmacbook/Desktop/Pokemon_TCG_AI_Battle_Challenge/experiments')
sys.path.insert(0, str(EXP))
import arena_runner as ar  # noqa: E402

PROJ = ar.PROJ
FINAL = sorted(int(l) for l in (PROJ / 'deck.csv').read_text().splitlines() if l.strip())
OLD_DECK = [int(l.strip()) for l in (PROJ / 'deck.csv.bak-2026-08-09').read_text().splitlines() if l.strip()]

N = 2000
SEED = 7000
REMOVALS = [1229, 1102, 1121, 1142, 1097, 1141, 1205, 1145, 1123, 1213, 1182]


def evaluate(rules, old, first, deck, tag):
    rm = ar.run_arena(rules, old, deck, OLD_DECK, N, seed0=SEED)
    tm = rm['wins'] + rm['losses'] + rm['draws']
    m = rm['wins'] / tm
    rf = ar.run_arena(rules, first, deck, ar.SAMPLE_DECK, N, seed0=SEED + 777)
    tf = rf['wins'] + rf['losses'] + rf['draws']
    f = rf['wins'] / tf
    print(f'  {tag}: mirror={m:.4f} vs_first={f:.4f} '
          f'(invalid {rm["invalid"]}/{rf["invalid"]})', flush=True)
    return {'tag': tag, 'mirror': round(m, 4), 'vs_first': round(f, 4),
            'invalid_m': rm['invalid'], 'invalid_f': rf['invalid'],
            'deck': sorted(deck)}


def main():
    rules = ar.load_module(PROJ / 'main.py').agent
    # 备份无 .py 后缀, spec_from_file_location 拒载 → 复制临时 .py (同 verify_v4 模式)
    import shutil
    tmp = EXP / 'runs' / '_eval1235_old_main.py'
    shutil.copyfile(PROJ / 'main.py.bak-2026-08-09-tune', tmp)
    old = ar.load_module(tmp).agent
    first = ar.builtin_agent('first')

    results = [evaluate(rules, old, first, FINAL, 'BASELINE=v4FINAL')]
    base = results[0]
    for r in REMOVALS:
        var = list(FINAL)
        var.remove(r)
        var.append(1235)
        results.append(evaluate(rules, old, first, var, f'-{r}+1235'))

    out = {'ts': time.time(), 'n': N, 'seed': SEED, 'baseline': base,
           'variants': results[1:]}
    p = EXP / 'runs' / 'eval_1235_variants.json'
    p.write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print(f'\nwritten: {p}', flush=True)
    # 排序提示 (联合: mirror 与 vs_first 均不差于 baseline 者, 按 vs_first 排)
    ok = [v for v in results[1:]
          if v['mirror'] >= base['mirror'] - 0.017 and v['invalid_m'] == 0 and v['invalid_f'] == 0]
    ok.sort(key=lambda v: v['vs_first'], reverse=True)
    print('候选 (mirror 不差于 baseline-1.7pp, 按 vs_first):', flush=True)
    for v in ok[:4]:
        print(f"  {v['tag']}: mirror={v['mirror']} vs_first={v['vs_first']} "
              f"(Δvf {v['vs_first']-base['vs_first']:+.4f}, Δm {v['mirror']-base['mirror']:+.4f})",
              flush=True)


if __name__ == '__main__':
    main()
