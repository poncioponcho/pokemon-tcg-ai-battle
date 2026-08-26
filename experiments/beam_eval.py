"""beam_eval.py — beam M2 方向信号: 镜像腿 beam vs 纯规则 (同 deck.csv), 3 种子

beam 在此腿的世界模型是完美的 (对手牌组+策略都是规则 agent), 是 1-ply beam 的
上限测试: 这里赢不了, 哪里都赢不了 (go/no-go)。
产物: runs/beam_eval_mirror.json
用法: nohup /opt/homebrew/bin/python3 experiments/beam_eval.py [n] > runs/beam_eval.log 2>&1 &
"""
import json, sys, time
from pathlib import Path
from typing import Any

PROJ = Path('/Users/seyonmacbook/Desktop/Pokemon_TCG_AI_Battle_Challenge')
sys.path.insert(0, str(PROJ / 'experiments'))
import arena_runner as ar  # noqa: E402

n = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
deck = [int(l) for l in (PROJ / 'deck.csv').read_text().splitlines() if l.strip()]

beam_mod = ar.load_module(PROJ / 'experiments/beam_agent.py')
rule_mod = ar.load_module(PROJ / 'main.py')

out: dict[str, Any] = {'n': n, 'seeds': {}, 'ts': time.time()}
for seed in (9100, 9101, 9102):
    t0 = time.perf_counter()
    r = ar.run_arena(beam_mod.agent, rule_mod.agent, deck, deck, n, seed0=seed)
    dt = time.perf_counter() - t0
    wr = r['wins'] / n
    lo = ar.wilson_ci_lo(r['wins'] / max(n - r['draws'], 1), n - r['draws']) if n else 0
    out['seeds'][seed] = {'wins': r['wins'], 'losses': r['losses'], 'draws': r['draws'],
                          'invalid': r['invalid'], 'wr': round(wr, 4), 'ci_lo': round(lo, 4),
                          'avg_turns': round(r['avg_turns'], 1), 'sec': round(dt, 1)}
    print(f'[seed {seed}] wr={wr:.4f} ci_lo={lo:.4f} w{r["wins"]}/l{r["losses"]}/d{r["draws"]} '
          f'invalid={r["invalid"]} avg_turns={r["avg_turns"]:.1f} {dt:.0f}s', flush=True)

out['stats'] = dict(beam_mod._stats)
with open(PROJ / 'experiments/runs/beam_eval_mirror.json', 'w') as f:
    json.dump(out, f, indent=1)
print('wrote runs/beam_eval_mirror.json')
print('beam_stats:', beam_mod._stats)
