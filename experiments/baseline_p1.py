"""baseline_p1.py — P1 诊断: baseline1084 agent 挂进 9 腿框架
用法: /opt/homebrew/bin/python3 experiments/baseline_p1.py [own|our] [legs,逗号] [n]
  own = baseline agent + baseline 自牌组 (真 1084.5 提交态)
  our = baseline agent + 我方 deck.csv (纯规则质量隔离)
"""
import json, sys, time
from pathlib import Path
from typing import Any
PROJ = Path('/Users/seyonmacbook/Desktop/Pokemon_TCG_AI_Battle_Challenge')
sys.path.insert(0, str(PROJ / 'experiments'))
import arena_runner as ar  # noqa: E402

which = sys.argv[1] if len(sys.argv) > 1 else 'own'
LEGS = sys.argv[2].split(',') if len(sys.argv) > 2 and sys.argv[2].strip() else \
    ['Crustle', 'Alakazam', 'Grimmsnarl', 'Archaludon', 'Lucario',
     'Gardevoir', 'Cornerstone', 'Dragapult', 'other']
N = int(sys.argv[3]) if len(sys.argv) > 3 else 1000

base = ar.load_module(PROJ / 'inference/ext/baseline1084_main.py')
import ast as _ast  # noqa: E402
# 安全取 baseline 牌组: 解析源码里的 DECK 字面量, 绝不 exec
# (baseline1084_deck.py 顶层有 Path('deck.csv').write_text — import 会覆盖我方 deck.csv!)
_dsrc = _ast.parse((PROJ / 'inference/ext/baseline1084_deck.py').read_text())
BASE_DECK = next(_ast.literal_eval(n.value) for n in _dsrc.body
                 if isinstance(n, _ast.Assign) and any(getattr(t, 'id', '') == 'DECK' for t in n.targets))
assert len(BASE_DECK) == 60
OUR = [int(l) for l in (PROJ / 'deck.csv').read_text().splitlines() if l.strip()]
deck_a = BASE_DECK if which == 'own' else OUR
first = ar.builtin_agent('first')
META = PROJ / 'experiments/arena_pool/meta'
out: dict[str, Any] = {'which': which, 'n': N, 'ts': time.time(), 'legs': {}}
for a in LEGS:
    csv = list(META.glob(f'{a}__*.csv'))[0]
    opp = [int(l) for l in csv.read_text().splitlines() if l.strip()]
    t0 = time.time()
    r = ar.run_arena(base.agent, first, deck_a, opp, N, seed0=9000)
    nd = max(N - r['draws'], 1)
    wr = r['wins'] / N
    out['legs'][a] = {'wr': round(wr, 4), 'ci_lo': round(ar.wilson_ci_lo(r['wins']/nd, nd), 4),
                      'invalid': r['invalid'], 'sec': round(time.time()-t0, 1)}
    print(f"[{which} {a:11s}] wr={wr:.4f} invalid={r['invalid']} ({time.time()-t0:.0f}s)", flush=True)
fn = PROJ / f'experiments/runs/baseline_p1_{which}.json'
json.dump(out, open(fn, 'w'), indent=1)
print('→', fn.name, flush=True)
