# -*- coding: utf-8 -*-
"""deck_variant_test.py — 抗样例牌组的换卡候选 A1 格快测。

基线 A1 = rules(我方牌组) vs first(样例牌组) ≈ 0.31（卡组效应主导）。
候选（在 deck.csv 基础上换卡，卡池合法性 = main._CARD_DB ∪ _TRAINER_IDS）：
  VA  雷 tech：-235 -673×2 -674×2 -1102×2 → +ピカチュウex(328)×2 +雷能量(4)×5
      328 かみなり [雷雷●] 220 → ×2 弱点=440 确杀カイオーガ(150)
  VB  VA 加强版：再 -1141×2 → +雷能量×2（雷×7，提高雷雷●上线率）
  VC  能量一致性对照：-1102×2 -1213×2 → +闘能量(6)×4（17→21）
测试策略 = main.py 纯规则（PTCG_NN_MODE=off，卡库覆盖全部 1056 宝可梦）。
同种子配对。用法: python3 experiments/deck_variant_test.py [--n 1000]
"""
import argparse
import collections
import os
import sys
from pathlib import Path

os.environ['PTCG_NN_MODE'] = 'off'  # 纯规则，排除 NN 变量

PROJ = Path('/Users/seyonmacbook/Desktop/Pokemon_TCG_AI_Battle_Challenge')
EXP = PROJ / 'experiments'
sys.path.insert(0, str(PROJ))
sys.path.insert(0, str(EXP))

import main as main_mod  # noqa: E402
import arena_runner as ar  # noqa: E402

BASE = collections.Counter(int(l.strip()) for l in (PROJ / 'deck.csv').read_text().splitlines() if l.strip())
SAMPLE = ar.SAMPLE_DECK
E_LEI, E_TOU = 4, 6
PIKACHU_EX = 328


def apply(base, out, inn):
    d = collections.Counter(base)
    for cid, n in out.items():
        assert d[cid] >= n, f'换出超量: {cid}×{n} > 持有 {d[cid]}'
        d[cid] -= n
        if d[cid] == 0:
            del d[cid]
    for cid, n in inn.items():
        d[cid] += n
    deck = sorted(d.elements())
    assert len(deck) == 60, f'牌组 {len(deck)} != 60'
    return deck


def build_variants():
    """Build legacy deck variants only when this experiment is executed.

    The repository's active ``deck.csv`` changes over time.  Constructing the
    historical variants at import time made pytest collection fail whenever
    that active deck no longer contained the cards this experiment removes.
    """
    return [
        ('BASE 当前牌组', apply(BASE, {}, {})),
        ('VA 雷tech×5雷', apply(BASE, {235: 1, 673: 2, 674: 2, 1102: 2},
                                {PIKACHU_EX: 2, E_LEI: 5})),
        ('VB 雷tech×7雷', apply(BASE, {235: 1, 673: 2, 674: 2, 1102: 2, 1141: 2},
                                {PIKACHU_EX: 2, E_LEI: 7})),
        ('VC 能量一致性', apply(BASE, {1102: 2, 1213: 2}, {E_TOU: 4})),
    ]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--n', type=int, default=1000)
    args = ap.parse_args()
    first = ar.builtin_agent('first')
    print(f"=== deck variant A1-test n={args.n} (agent=main.py 纯规则, 对手=first/SAMPLE) ===",
          flush=True)
    for label, deck in build_variants():
        r = ar.run_arena(main_mod.agent, first, deck, SAMPLE, args.n)
        n = r['wins'] + r['losses'] + r['draws']
        w = r['wins'] / n if n else 0.0
        print(f"{label:22s} {r['wins']:5d}W {r['losses']:5d}L {r['draws']:3d}D "
              f"wr={w:.3f} (turns={r['avg_turns']}, invalid={r['invalid']})", flush=True)


if __name__ == '__main__':
    main()
