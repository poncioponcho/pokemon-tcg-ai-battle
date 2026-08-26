"""beam_m3_gate.py — beam M3 验收闸: BEAM_OPP_DECK=auto vs 全 meta 池, 3 种子

对照 v0 基线 runs/meta_matchup_ref.json (纯规则 main.py vs builtin-first 操控的
meta 牌组, n=2000)。beam 侧 = main.py 规则 + 1-ply beam + 识别器注入对手牌组。
识别器弃权 → 镜像假设 (M2 行为); 误识 → 负余量自动回退纯规则。

闸线 (beam_m3_blueprint.md §3):
  Alakazam > 0.50 (基线 0.466) | Crustle > 0.52 (基线 0.497)
  Lucario 镜像不退化 | 加权期望 > v0 加权 | 全腿 invalid == 0

产物: runs/beam_m3_gate.json
用法: /opt/homebrew/bin/python3 experiments/beam_m3_gate.py [n] [legs,逗号] [seeds,逗号]
全量: nohup /opt/homebrew/bin/python3 experiments/beam_m3_gate.py 1000 > runs/beam_m3_gate.log 2>&1 &
"""
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

PROJ = Path('/Users/seyonmacbook/Desktop/Pokemon_TCG_AI_Battle_Challenge')
os.environ['BEAM_OPP_DECK'] = 'auto'  # 必须先于 beam_agent 模块加载
sys.path.insert(0, str(PROJ / 'experiments'))
import arena_runner as ar  # noqa: E402

n = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
META_DIR = PROJ / 'experiments/arena_pool/meta'
ALL_LEGS = ['Alakazam', 'Crustle', 'Lucario', 'Grimmsnarl', 'Archaludon',
            'Dragapult', 'Cornerstone', 'Gardevoir', 'other']
LEGS = sys.argv[2].split(',') if len(sys.argv) > 2 and sys.argv[2].strip() else ALL_LEGS
SEEDS = [int(s) for s in sys.argv[3].split(',')] if len(sys.argv) > 3 else [9000, 9001, 9002]

deck = [int(l) for l in (PROJ / 'deck.csv').read_text().splitlines() if l.strip()]
ref = json.loads((PROJ / 'experiments/runs/meta_matchup_ref.json').read_text())

# meta 占比: 从 4500 局标注数据双座位统计 (含 other)
share: Counter[str] = Counter()
for line in open(PROJ / 'experiments/runs/meta_decks_raw.jsonl'):
    for a in json.loads(line)['arch']:
        share[a or 'other'] += 1
tot = sum(share.values())
SHARE = {a: share[a] / tot for a in LEGS}

meta_decks = {}
for a in LEGS:
    csvs = list(META_DIR.glob(f'{a}__*.csv'))
    assert csvs, f'缺 meta 牌组: {a}'
    meta_decks[a] = [int(l) for l in csvs[0].read_text().splitlines() if l.strip()]

beam_mod = ar.load_module(PROJ / 'experiments/beam_agent.py')
first = ar.builtin_agent('first')

# 闸线: (腿, 阈值, 语义)  — Lucario/加权单独判
LEG_GATE = {'Alakazam': 0.50, 'Crustle': 0.52}
NOISE = 0.017  # ±1.7pp 噪声铁律

out: dict[str, Any] = {
    'n': n, 'seeds': SEEDS, 'beam_opp_deck': 'auto', 'ts': time.time(),
    'legs': {}, 'stats_delta': {},
}
OUT_JSON = PROJ / f'experiments/runs/beam_m3_gate_s{"-".join(map(str, SEEDS))}.json'
print(f'=== beam_m3_gate n={n} seeds={SEEDS} legs={LEGS} ===', flush=True)
t_all = time.time()
for a in LEGS:
    leg: dict[str, Any] = {'base_wr': ref['results'][a]['wr'], 'seeds': {}}
    s0 = {k: (dict(v) if isinstance(v, Counter) else v) for k, v in beam_mod._stats.items()}
    for seed in SEEDS:
        t0 = time.time()
        r = ar.run_arena(beam_mod.agent, first, deck, meta_decks[a], n, seed0=seed)
        dt = time.time() - t0
        nd = max(n - r['draws'], 1)
        wr = r['wins'] / n
        lo = ar.wilson_ci_lo(r['wins'] / nd, nd)
        leg['seeds'][seed] = {'wins': r['wins'], 'losses': r['losses'], 'draws': r['draws'],
                              'invalid': r['invalid'], 'wr': round(wr, 4),
                              'ci_lo': round(lo, 4), 'avg_turns': r['avg_turns'],
                              'sec': round(dt, 1)}
        print(f'  [{a:11s} s{seed}] wr={wr:.4f} ci_lo={lo:.4f} invalid={r["invalid"]} '
              f'(base {leg["base_wr"]:.4f}) {dt:.0f}s', flush=True)
    wrs = [leg['seeds'][s]['wr'] for s in SEEDS]
    leg['wr_min'] = min(wrs)
    leg['wr_mean'] = round(sum(wrs) / len(wrs), 4)
    leg['invalid_total'] = sum(leg['seeds'][s]['invalid'] for s in SEEDS)
    # 判读: 目标腿达闸线; Lucario 镜像不退化 (min >= base - 2*噪声); 其余腿不退化参考
    if a in LEG_GATE:
        leg['verdict'] = 'PASS' if leg['wr_min'] > LEG_GATE[a] else 'FAIL'
    elif a == 'Lucario':
        leg['verdict'] = 'PASS' if leg['wr_min'] >= leg['base_wr'] - 2 * NOISE else 'FAIL'
    else:
        leg['verdict'] = 'PASS' if leg['wr_min'] >= leg['base_wr'] - 2 * NOISE else 'WARN'
    if leg['invalid_total'] > 0:
        leg['verdict'] = 'FAIL'
    s1 = beam_mod._stats
    out['stats_delta'][a] = {
        'beam': s1['beam'] - s0['beam'], 'fallback': s1['fallback'] - s0['fallback'],
        'abort': s1['abort'] - s0['abort'], 'fb_no_hidden': s1['fb_no_hidden'] - s0['fb_no_hidden'],
        'recog_none': s1['recog_none'] - s0['recog_none'],
        'recog': {k: s1['recog'].get(k, 0) - s0['recog'].get(k, 0)
                  for k in set(s1['recog']) | set(s0['recog'])},
        'beam_deck': {k: s1['beam_deck'].get(k, 0) - s0['beam_deck'].get(k, 0)
                      for k in set(s1['beam_deck']) | set(s0['beam_deck'])}}
    out['legs'][a] = leg
    d = out['stats_delta'][a]
    print(f'  [{a:11s}] mean={leg["wr_mean"]:.4f} min={leg["wr_min"]:.4f} '
          f'verdict={leg["verdict"]} recog={d["recog"]} abstain={d["recog_none"]} '
          f'beam_deck={d["beam_deck"]} beam={d["beam"]} fb={d["fallback"]} abort={d["abort"]}',
          flush=True)

# 加权期望 vs v0 —— 两版占比 (防 stale 占比误导):
# (a) jsonl: 4500 局标注集实测占比
# (b) sumi_top: Sumi 帖 729926 的 7/26 top-band 锚点 (Grimmsnarl .513 / Lucario .0003 /
#     Archaludon ~.03), 其余族按 jsonl 相对比例填充; Garchomp/Tarountula 未入池, 并入 other
bw = sum(SHARE[a] * out['legs'][a]['wr_mean'] for a in LEGS)
vw = sum(SHARE[a] * ref['results'][a]['wr'] for a in LEGS)
out['weighted'] = {'share_source': 'meta_decks_raw.jsonl 4500局实测',
                   'share': {a: round(SHARE[a], 4) for a in LEGS},
                   'beam': round(bw, 4), 'v0_base': round(vw, 4),
                   'delta': round(bw - vw, 4)}
SUMI = {'Grimmsnarl': 0.513, 'Lucario': 0.0003, 'Archaludon': 0.03}
rest = [a for a in LEGS if a not in SUMI]
rest_jsonl = sum(SHARE[a] for a in rest)
fill = 1.0 - sum(SUMI.values())
SHARE2 = {a: (SUMI[a] if a in SUMI else SHARE[a] / rest_jsonl * fill) for a in LEGS}
bw2 = sum(SHARE2[a] * out['legs'][a]['wr_mean'] for a in LEGS)
vw2 = sum(SHARE2[a] * ref['results'][a]['wr'] for a in LEGS)
out['weighted_sumi_top'] = {'share_source': 'Sumi 729926 锚点 + jsonl 相对比例填充 (Garchomp/Tarountula→other)',
                            'share': {a: round(SHARE2[a], 4) for a in LEGS},
                            'beam': round(bw2, 4), 'v0_base': round(vw2, 4),
                            'delta': round(bw2 - vw2, 4)}
out['elapsed_min'] = round((time.time() - t_all) / 60, 1)
fails = [a for a in LEGS if out['legs'][a]['verdict'] == 'FAIL']
out['overall'] = 'PASS' if not fails and bw > vw else ('FAIL: ' + ','.join(fails) if fails else 'HOLD: weighted')
with open(OUT_JSON, 'w') as f:
    json.dump(out, f, indent=1)
print(f'weighted[jsonl] beam={bw:.4f} v0={vw:.4f} delta={bw - vw:+.4f}', flush=True)
print(f'weighted[sumi ] beam={bw2:.4f} v0={vw2:.4f} delta={bw2 - vw2:+.4f}', flush=True)
print(f'overall={out["overall"]}  elapsed={out["elapsed_min"]}min', flush=True)
print(f'wrote {OUT_JSON.name}', flush=True)
