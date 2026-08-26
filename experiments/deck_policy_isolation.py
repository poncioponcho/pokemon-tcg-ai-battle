# -*- coding: utf-8 -*-
"""deck_policy_isolation.py — 'first' 弱点对局归因：卡组 vs 策略 2×2 隔离实验。

背景：arena 中我方 hybrid/rules 对 'first'（无脑选前 n 项 + 官方样例牌组）
仅 ~0.33 胜率。该对局混淆了两个变量：牌组不同（我方 deck.csv vs 官方样例）
与策略不同（我方规则 vs 无脑首选）。本实验固定对手 B = first(SAMPLE_DECK)，
A 侧做 {rules, first} × {OUR_DECK, SAMPLE_DECK} 2×2 析因，分离两变量：

  rules(OUR)    vs first(SAMPLE)  = 基线（即 arena 已知行 ~0.33）
  first(OUR)    vs first(SAMPLE)  = 策略效应 = 本格 - 基线
  rules(SAMPLE) vs first(SAMPLE)  = 卡组效应 = 本格 - 基线
  first(SAMPLE) vs first(SAMPLE)  = 镜像锚点（应 ≈0.50，sanity）

解读：
  卡组效应大  → 修牌组（构筑问题）
  策略效应大且 first(OUR) > rules(OUR) → 规则在此对局净负收益，修决策
先后手轮换；四格是独立批次。seed 只控制 Python 侧，native shuffle
不可注种，因此不将格间差值当作 paired/CRN 统计。零 GPU。
用法: python3 experiments/deck_policy_isolation.py [--n 1000]
"""
import argparse
import sys
from pathlib import Path

EXP = Path('/Users/seyonmacbook/Desktop/Pokemon_TCG_AI_Battle_Challenge/experiments')
sys.path.insert(0, str(EXP))
import arena_runner as ar  # noqa: E402  (复用 play/run_arena/SAMPLE_DECK/builtin_agent/load_opponent)

PROJ = ar.PROJ
OUR_DECK = [int(l.strip()) for l in (PROJ / 'deck.csv').read_text().splitlines() if l.strip()]
SAMPLE = ar.SAMPLE_DECK


def wr_of(r):
    n = r['wins'] + r['losses'] + r['draws']
    return (r['wins'] / n) if n else 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--n', type=int, default=1000)
    args = ap.parse_args()

    first = ar.builtin_agent('first')
    rules = ar.load_opponent('v23_2_rules')

    cells = [
        ('A1 rules(OUR)    vs first(SAMPLE)  [基线]', rules, OUR_DECK),
        ('A2 first(OUR)    vs first(SAMPLE)  [策略隔离]', first, OUR_DECK),
        ('A3 rules(SAMPLE) vs first(SAMPLE)  [卡组隔离]', rules, SAMPLE),
        ('A4 first(SAMPLE) vs first(SAMPLE)  [镜像锚点]', first, SAMPLE),
    ]
    print(f"=== deck/policy isolation n={args.n} ===", flush=True)
    print(f"OUR_DECK 前5: {OUR_DECK[:5]} | SAMPLE 前5: {SAMPLE[:5]}", flush=True)
    results = {}
    for label, agent_a, deck_a in cells:
        r = ar.run_arena(agent_a, first, deck_a, SAMPLE, args.n)
        w = wr_of(r)
        results[label.split()[0]] = w
        print(f"{label}  {r['wins']:5d}W {r['losses']:5d}L {r['draws']:3d}D "
              f"wr={w:.3f}  (avg_turns={r['avg_turns']}, invalid={r['invalid']})",
              flush=True)

    base = results['A1']
    print('\n--- 效应分解（相对基线 A1）---', flush=True)
    print(f"策略效应 (A2-A1, 首选 vs 规则，同牌组对比): {results['A2'] - base:+.3f}", flush=True)
    print(f"卡组效应 (A3-A1, 样例牌组 vs 我方牌组):   {results['A3'] - base:+.3f}", flush=True)
    print(f"镜像锚点 A4（应≈0.50）:                   {results['A4']:.3f}", flush=True)


if __name__ == '__main__':
    main()
