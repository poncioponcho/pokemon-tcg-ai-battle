# -*- coding: utf-8 -*-
"""gate_1235_variants.py — ② 后半场: 1235 变体 3 批复验闸 (不提交)。

设计: 每颗种子同进程内跑 baseline(v4 FINAL) + 变体A(-1141+1235) + 变体B(-1229+1235),
seed 只固定 Python 侧，native shuffle 不可注种；逐 seed Δ 不是
paired/CRN 差值，只能按 3 个独立随机批次解读。绝对值走 3 批标准闸口径
(硬闸=卡池+invalid+ci_lo>0.5; 接受=mirror≥0.7465 或 vs_first≥0.4564 且 mirror≥0.7095)。
纯只读: 直接 arena 调用, 不碰 deck.csv/main.py/Kaggle。
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

N = 8000
SEEDS = [9000, 9001, 9002]


def make_variant(rm):
    d = list(FINAL)
    d.remove(rm)
    d.append(1235)
    return d


DECKS = [('baseline_v4final', FINAL),
         ('variantA_-1141+1235', make_variant(1141)),
         ('variantB_-1229+1235', make_variant(1229))]


def legs(rules, old, first, deck, seed):
    rm = ar.run_arena(rules, old, deck, OLD_DECK, N, seed0=seed)
    tm = rm['wins'] + rm['losses'] + rm['draws']
    m = rm['wins'] / tm
    mlo = ar.wilson_ci_lo(m, tm)
    rf = ar.run_arena(rules, first, deck, ar.SAMPLE_DECK, N, seed0=seed)
    tf = rf['wins'] + rf['losses'] + rf['draws']
    f = rf['wins'] / tf
    return {'mirror': round(m, 4), 'mirror_ci_lo': round(mlo, 4),
            'vs_first': round(f, 4),
            'invalid_m': rm['invalid'], 'invalid_f': rf['invalid']}


def main():
    rules_mod = ar.load_module(PROJ / 'main.py')
    # 卡池快败 (复刻 verify 脚本): 变体含 1235, 必须先验
    for name, d in DECKS:
        unknown = [c for c in set(d)
                   if c not in rules_mod._CARD_DB and c not in rules_mod._TRAINER_IDS]
        if unknown:
            print(f'[card-pool] {name} FAIL: {sorted(unknown)} 不在卡池', flush=True)
            sys.exit(1)
    print('[card-pool] OK: 全部牌组卡 ID 在卡池', flush=True)

    import shutil
    tmp = EXP / 'runs' / '_gate1235_old_main.py'
    shutil.copyfile(PROJ / 'main.py.bak-2026-08-09-tune', tmp)
    rules = rules_mod.agent
    old = ar.load_module(tmp).agent
    first = ar.builtin_agent('first')

    out = {'ts': time.time(), 'n': N, 'seeds': {}}
    for seed in SEEDS:
        print(f'--- seed {seed} ---', flush=True)
        per = {}
        for name, d in DECKS:
            r = legs(rules, old, first, d, seed)
            per[name] = r
            print(f'  {name}: mirror={r["mirror"]} (ci_lo={r["mirror_ci_lo"]}) '
                  f'vs_first={r["vs_first"]} invalid={r["invalid_m"]}/{r["invalid_f"]}',
                  flush=True)
        out['seeds'][str(seed)] = per

    # 汇总: 逐变体 vs baseline 的逐种子 Δ + 闸判定
    summ = {}
    for name, _ in DECKS[1:]:
        rows = []
        for seed in SEEDS:
            b = out['seeds'][str(seed)]['baseline_v4final']
            v = out['seeds'][str(seed)][name]
            hard = (v['invalid_m'] == 0 and v['invalid_f'] == 0 and v['mirror_ci_lo'] > 0.5)
            accept = (v['mirror'] >= 0.7465
                      or (v['vs_first'] >= 0.4564 and v['mirror'] >= 0.7095))
            rows.append({'seed': seed, 'dm': round(v['mirror'] - b['mirror'], 4),
                         'dvf': round(v['vs_first'] - b['vs_first'], 4),
                         'hard': hard, 'accept': accept})
        summ[name] = rows
        ok = all(r['hard'] and r['accept'] for r in rows)
        dvf_min = min(r['dvf'] for r in rows)
        dm_min = min(r['dm'] for r in rows)
        print(f'\n=== {name}: gate={"PASS" if ok else "FAIL"} '
              f'min_Δvf={dvf_min:+.4f} min_Δm={dm_min:+.4f}', flush=True)
        for r in rows:
            print(f'    seed {r["seed"]}: Δm={r["dm"]:+.4f} Δvf={r["dvf"]:+.4f} '
                  f'hard={r["hard"]} accept={r["accept"]}', flush=True)
    out['summary'] = summ
    p = EXP / 'runs' / 'gate_1235_variants.json'
    p.write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print(f'\nwritten: {p}', flush=True)


if __name__ == '__main__':
    main()
