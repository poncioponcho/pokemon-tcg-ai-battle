"""f1_gate.py — F1 (1084.5 prize 框架 + 墙转火) 9 腿验收闸

A/B 口径: 候选 = 当前 main.py + _PARAMS['f1_gust_target_score'/'f1_wall_retarget']=True
(模块加载后程序化翻转, 文件默认仍 False = 线上零行为变化);
基线 = runs/meta_matchup_ref.json (同 main.py flags OFF vs builtin-first 驾驶 meta 牌组, n=2000)。

判线 (peer 16:05 纪律):
  Crustle 真增益 (base 0.4965, 期望 +10pp 量级; 若只 +3pp 说明转火没生效)
  Alakazam 第一验证目标 (base 0.466, 看 target_score 通用选靶是否救得动)
  地板腿 Gardevoir 0.9725 / Cornerstone 0.9545 / Dragapult 0.935 任一退化 >1.7pp×2 即否
  invalid 全 0; 观测 _F1_STATS (wall_retarget 必须 >0, 否则转火根本没发射)

产物: runs/f1_gate_s{seed}.json
用法: /opt/homebrew/bin/python3 experiments/f1_gate.py [n] [legs,逗号] [seeds,逗号]
"""
import json
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

PROJ = Path('/Users/seyonmacbook/Desktop/Pokemon_TCG_AI_Battle_Challenge')
sys.path.insert(0, str(PROJ / 'experiments'))
import arena_runner as ar  # noqa: E402

n = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
META_DIR = PROJ / 'experiments/arena_pool/meta'
ALL_LEGS = ['Crustle', 'Alakazam', 'Gardevoir', 'Cornerstone', 'Dragapult',
            'Lucario', 'Grimmsnarl', 'Archaludon', 'other']
LEGS = sys.argv[2].split(',') if len(sys.argv) > 2 and sys.argv[2].strip() else ALL_LEGS
SEEDS = [int(s) for s in sys.argv[3].split(',')] if len(sys.argv) > 3 else [9000, 9001, 9002]
FLAGS = sys.argv[4].split(',') if len(sys.argv) > 4 and sys.argv[4].strip() else ['f1_gust_target_score', 'f1_wall_retarget']
NOISE = 0.017

deck = [int(l) for l in (PROJ / 'deck.csv').read_text().splitlines() if l.strip()]
ref = json.loads((PROJ / 'experiments/runs/meta_matchup_ref.json').read_text())

cand = ar.load_module(PROJ / 'main.py')
for _fl in FLAGS:
    cand._PARAMS[_fl] = True
first = ar.builtin_agent('first')

meta_decks = {}
for a in LEGS:
    csvs = list(META_DIR.glob(f'{a}__*.csv'))
    assert csvs, f'缺 meta 牌组: {a}'
    meta_decks[a] = [int(l) for l in csvs[0].read_text().splitlines() if l.strip()]

out: dict[str, Any] = {
    'n': n, 'seeds': SEEDS,
    'agent': f'main.py + {FLAGS} ON vs first-piloted meta',
    'ts': time.time(), 'legs': {}, 'f1_stats': {},
}
print(f'=== f1_gate n={n} seeds={SEEDS} legs={LEGS} ===', flush=True)
t_all = time.time()
for a in LEGS:
    leg: dict[str, Any] = {'base_wr': ref['results'][a]['wr'], 'seeds': {}}
    s0 = dict(cand._F1_STATS)
    for seed in SEEDS:
        t0 = time.time()
        r = ar.run_arena(cand.agent, first, deck, meta_decks[a], n, seed0=seed)
        dt = time.time() - t0
        nd = max(n - r['draws'], 1)
        wr = r['wins'] / n
        lo = ar.wilson_ci_lo(r['wins'] / nd, nd)
        leg['seeds'][seed] = {'wins': r['wins'], 'losses': r['losses'], 'draws': r['draws'],
                              'invalid': r['invalid'], 'wr': round(wr, 4),
                              'ci_lo': round(lo, 4), 'sec': round(dt, 1)}
        print(f'  [{a:11s} s{seed}] wr={wr:.4f} ci_lo={lo:.4f} invalid={r["invalid"]} '
              f'(base {leg["base_wr"]:.4f}) {dt:.0f}s', flush=True)
    wrs = [leg['seeds'][s]['wr'] for s in SEEDS]
    leg['wr_min'] = min(wrs)
    leg['wr_mean'] = round(sum(wrs) / len(wrs), 4)
    leg['delta_mean'] = round(leg['wr_mean'] - leg['base_wr'], 4)
    leg['invalid_total'] = sum(leg['seeds'][s]['invalid'] for s in SEEDS)
    leg['verdict'] = 'REGRESS' if leg['wr_min'] < leg['base_wr'] - 2 * NOISE else 'ok'
    if leg['invalid_total'] > 0:
        leg['verdict'] = 'FAIL'
    out['f1_stats'][a] = {k: cand._F1_STATS[k] - s0[k] for k in cand._F1_STATS}
    out['legs'][a] = leg
    print(f'  [{a:11s}] mean={leg["wr_mean"]:.4f} min={leg["wr_min"]:.4f} '
          f'delta={leg["delta_mean"]:+.4f} verdict={leg["verdict"]} '
          f'f1={out["f1_stats"][a]}', flush=True)

out['elapsed_min'] = round((time.time() - t_all) / 60, 1)
regress = [a for a in LEGS if out['legs'][a]['verdict'] != 'ok']
out['overall'] = 'FAIL: ' + ','.join(regress) if regress else 'CLEAN'
tag = {'f1_gust_target_score': 'gust', 'f1_wall_retarget': 'wall'}.get(FLAGS[0], 'both') if len(FLAGS) == 1 else 'both'
OUT = PROJ / f'experiments/runs/f1_gate_{tag}_s{"-".join(map(str, SEEDS))}.json'
with open(OUT, 'w') as f:
    json.dump(out, f, indent=1)
print(f'overall={out["overall"]} elapsed={out["elapsed_min"]}min → {OUT.name}', flush=True)
