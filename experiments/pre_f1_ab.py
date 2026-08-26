"""pre_f1_ab.py — 提交前 A/B: 现行 main.py(F1-ON) vs pre-F1 main.py(tar 版 v24.8)
引擎不可播种(ledger: measurement_engine_unseedable_discipline), 一切=无配对二项抽样,
n=1000 σ_diff≈2.2pp / n=2000≈1.55pp。判线: F1-ON 各腿 ≥ pre-F1 −2σ 即无回归。
用法: /opt/homebrew/bin/python3 experiments/pre_f1_ab.py [on|off] [legs,逗号] [n]
"""
import json, sys, time
from pathlib import Path
from typing import Any
PROJ = Path('/Users/seyonmacbook/Desktop/Pokemon_TCG_AI_Battle_Challenge')
sys.path.insert(0, str(PROJ / 'experiments'))
import arena_runner as ar  # noqa: E402

which = sys.argv[1] if len(sys.argv) > 1 else 'on'
LEGS = sys.argv[2].split(',') if len(sys.argv) > 2 and sys.argv[2].strip() else \
    ['Crustle', 'Grimmsnarl', 'Archaludon', 'Lucario', 'Alakazam',
     'Gardevoir', 'Cornerstone', 'Dragapult', 'other']
N = int(sys.argv[3]) if len(sys.argv) > 3 else 1000
BIG = {'Crustle', 'Grimmsnarl', 'Archaludon'}   # 中大腿双倍样本

mod = ar.load_module(PROJ / ('main.py' if which == 'on' else 'experiments/runs/_pref1/main.py'))
OUR = [int(l) for l in (PROJ / 'deck.csv').read_text().splitlines() if l.strip()]
first = ar.builtin_agent('first')
META = PROJ / 'experiments/arena_pool/meta'
out: dict[str, Any] = {'which': which, 'ts': time.time(), 'legs': {}}
for a in LEGS:
    csv = list(META.glob(f'{a}__*.csv'))[0]
    opp = [int(l) for l in csv.read_text().splitlines() if l.strip()]
    n = N * 2 if a in BIG else N
    t0 = time.time()
    r = ar.run_arena(mod.agent, first, OUR, opp, n, seed0=9000)
    nd = max(n - r['draws'], 1)
    wr = r['wins'] / n
    out['legs'][a] = {'n': n, 'wr': round(wr, 4), 'ci_lo': round(ar.wilson_ci_lo(r['wins']/nd, nd), 4),
                      'invalid': r['invalid'], 'sec': round(time.time()-t0, 1)}
    print(f"[{which:3s} {a:11s}] n={n} wr={wr:.4f} invalid={r['invalid']} ({time.time()-t0:.0f}s)", flush=True)
fn = PROJ / f'experiments/runs/pre_f1_ab_{which}_{len(LEGS)}leg.json'
json.dump(out, open(fn, 'w'), indent=1)
print('→', fn.name, flush=True)
