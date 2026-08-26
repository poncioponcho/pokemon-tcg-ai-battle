"""beam_smoke.py — beam_agent 小样本冒烟

验: (1) 模块可加载 (2) beam 真触发 (3) invalid==0 (4) 单局耗时 (5) 镜像/vs_first 方向。
用法: /opt/homebrew/bin/python3 experiments/beam_smoke.py [n]
"""
import sys, time
from pathlib import Path

PROJ = Path('/Users/seyonmacbook/Desktop/Pokemon_TCG_AI_Battle_Challenge')
sys.path.insert(0, str(PROJ / 'experiments'))
import arena_runner as ar  # noqa: E402

n = int(sys.argv[1]) if len(sys.argv) > 1 else 10
beam_mod = ar.load_module(PROJ / 'experiments/beam_agent.py')
rule_mod = ar.load_module(PROJ / 'main.py')
deck = [int(l) for l in (PROJ / 'deck.csv').read_text().splitlines() if l.strip()]

t0 = time.perf_counter()
r1 = ar.run_arena(beam_mod.agent, rule_mod.agent, deck, deck, n, seed0=9100)
t1 = time.perf_counter()
print(f'[mirror beam vs rule] n={n} wr={r1["wins"]/max(n,1):.3f} '
      f'(w{r1["wins"]}/l{r1["losses"]}/d{r1["draws"]}) invalid={r1["invalid"]} '
      f'avg_turns={r1["avg_turns"]:.1f} {(t1-t0)/n:.2f}s/局')

t0 = time.perf_counter()
first = ar.builtin_agent('first')
r2 = ar.run_arena(beam_mod.agent, first, deck, ar.SAMPLE_DECK, n, seed0=9200)
t1 = time.perf_counter()
print(f'[vs_first beam       ] n={n} wr={r2["wins"]/max(n,1):.3f} '
      f'(w{r2["wins"]}/l{r2["losses"]}/d{r2["draws"]}) invalid={r2["invalid"]} '
      f'avg_turns={r2["avg_turns"]:.1f} {(t1-t0)/n:.2f}s/局')

print('beam_stats:', beam_mod._stats)
