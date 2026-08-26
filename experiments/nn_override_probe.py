# -*- coding: utf-8 -*-
"""nn_override_probe.py — 实测 NN Advisor 在真实对局中的介入率（A线根因排查）。

被测 main.py 以 hybrid(rerank) 模式加载，monkeypatch _nn_consult 分类统计：
  calls            Main/Card/Attack 决策中经过 _nn_consult 的次数
  load_fail        npz 加载失败（静默降级纯规则）次数
  no_opts          n_opts==0
  keep_top3        规则首选在 NN top3 内 → 保持规则（机制性抑制）
  keep_gap         规则不在 top3，但 NN top1-top2 gap <= GAP → 保持规则
  override         NN 接管（真正改变行为的决策）
  nn_first_direct  nn_first 模式直接采用（本探针用 rerank 模式，应恒 0）
  exceptions       _nn_consult 内部异常

解读：
  override/calls 极低 (<1%)   → 根因=机制抑制（门禁设计过于保守）
  override 显著但 mirror WR≈0 → 根因=NN 分歧决策本身无正期望
用法: python3 experiments/nn_override_probe.py [--n 100] [--gap 1.0]
"""
import argparse
import sys
from collections import Counter
from pathlib import Path

EXP = Path('/Users/seyonmacbook/Desktop/Pokemon_TCG_AI_Battle_Challenge/experiments')
sys.path.insert(0, str(EXP))
import arena_runner as ar  # noqa: E402

PROJ = ar.PROJ


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--n', type=int, default=100)
    ap.add_argument('--gap', type=float, default=1.0)
    args = ap.parse_args()

    mod = ar.load_module(PROJ / 'main.py')
    mod._NN_GAP = args.gap  # 与线上默认一致（PTCG_NN_GAP=1.0）

    stats = Counter()
    gap_samples = []

    def probe(obs, sel_type, options, max_count, rule_action):
        stats['calls'] += 1
        stats[f'type_{sel_type}'] += 1
        if mod._NN_MODE == 'off' or sel_type not in mod._NN_SEL_TYPES:
            stats['filtered_type'] += 1
            return rule_action
        if not mod._nn_lazy_load():
            stats['load_fail'] += 1
            return rule_action
        try:
            np = mod._NN['np']
            st, sc, o, mk, n_opts = mod._nn_build_features(obs)
            if n_opts == 0:
                stats['no_opts'] += 1
                return rule_action
            logits = mod._nn_forward(st, sc, o, mk)
            order = np.argsort(-logits)
            nn_act = [int(i) for i in order[:max_count]
                      if 0 <= int(i) < n_opts and np.isfinite(logits[int(i)])]
            if not nn_act:
                stats['empty_nn'] += 1
                return rule_action
            if rule_action and rule_action[0] in (int(x) for x in order[:3]):
                stats['keep_top3'] += 1
                return rule_action
            top1 = float(logits[int(order[0])])
            second = logits[int(order[1])] if len(order) > 1 else -np.inf
            gap = top1 - float(second) if np.isfinite(second) else float('inf')
            gap_samples.append(gap)
            if gap > mod._NN_GAP:
                stats['override'] += 1
                return nn_act[:max_count]
            stats['keep_gap'] += 1
            return rule_action
        except Exception:
            stats['exceptions'] += 1
            return rule_action

    mod._nn_consult = probe
    agent_fn = mod.agent
    deck_a = agent_fn({'select': None}, None)
    assert len(deck_a) == 60

    opp = ar.load_opponent('v23_2_rules')
    opp_deck = opp({'select': None})

    # 预检：npz 是否真的加载成功（静默降级是头号嫌疑）
    ok = mod._nn_lazy_load()
    print(f"npz lazy_load ok = {ok}  (False 则 hybrid 实际=纯规则)")
    if ok:
        print(f"npz card_dim={mod._NN['card_dim']}")

    r = ar.run_arena(agent_fn, opp, deck_a, opp_deck, args.n)
    n_dec = stats['calls'] if stats['calls'] else 1
    print(f"\n=== {args.n} 局 mirror 对局结束: "
          f"{r['wins']}W {r['losses']}L {r['draws']}D "
          f"wr={r['wins']/args.n:.3f} avg_turns={r['avg_turns']} ===")
    print(f"NN 介入统计（calls={stats['calls']}, 约 {stats['calls']/max(1,args.n):.0f} 次/局）:")
    for k in ('filtered_type', 'load_fail', 'no_opts', 'empty_nn',
              'keep_top3', 'keep_gap', 'override', 'exceptions'):
        v = stats[k]
        print(f"  {k:<14} {v:>6}  ({v/n_dec*100:.2f}%)")
    if gap_samples:
        gap_samples.sort()
        m = len(gap_samples)
        print(f"分歧且规则不在 top3 的样本数: {m} "
          f"({m/n_dec*100:.2f}% of calls)")
        print(f"  gap 分布: p50={gap_samples[m//2]:.3f} "
              f"p90={gap_samples[int(m*0.9)]:.3f} p99={gap_samples[int(m*0.99)]:.3f} "
              f"max={gap_samples[-1]:.3f}")
        print(f"  gap>{mod._NN_GAP} 的比例: "
              f"{sum(1 for g in gap_samples if g > mod._NN_GAP)/m*100:.2f}%")


if __name__ == '__main__':
    main()
