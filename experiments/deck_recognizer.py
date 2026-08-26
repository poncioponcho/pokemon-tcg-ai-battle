"""deck_recognizer.py — 对手牌组识别器 (beam M3 核心)

visible 卡 → archetype 分类 → canonical 60 张 → 供 beam_agent 注入 OPP_DECK。

签名表: 从 meta_decks_raw.jsonl (4500 局双座位标注) 自动导出 PMI 权重
  w(c, A) = log(P(A|c) / P(A))  (仅保留 P(A|c) >= 0.5 的强签名卡)
canonical 表: experiments/arena_pool/meta/*.csv (rank 最佳样本)

判决: score[A] = Σ 可见卡权重; top1-top2 >= MARGIN 才采纳, 否则弃权(None)。
弃权/误识的后果都是 beam 回退纯规则 (负余量自纠错), 不产出错误决策。

自测: /opt/homebrew/bin/python3 experiments/deck_recognizer.py
  用标注数据模拟"牌组宝可梦线全亮"做离线准确率 + 混淆矩阵。
"""
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

PROJ = Path(__file__).resolve().parent.parent
RAW = PROJ / 'experiments/runs/meta_decks_raw.jsonl'
POOL = PROJ / 'experiments/arena_pool/meta'

MARGIN = 2.0   # 默认判决 margin (CLI 覆盖见 __main__; 不在 import 时碰 sys.argv)
MIN_SIG_P = 0.5   # P(A|c) 下限, 过滤共享 staples (1152/1182/1227 之类)


def load_labeled():
    rows = [json.loads(l) for l in open(RAW)]
    out = []  # (arch, Counter deck)
    for r in rows:
        for seat in (0, 1):
            a = r['arch'][seat]
            if a and a != 'other':
                out.append((a, Counter(r['decks'][seat])))
    return out


def build_signature(labeled):
    card_arch = defaultdict(Counter)   # c -> Counter(arch)
    arch_n = Counter()
    for a, dk in labeled:
        arch_n[a] += 1
        for c in dk:  # 每张独特卡计一次 (P(A|c) 按"含此卡的座位"计)
            card_arch[c][a] += 1
    total = sum(arch_n.values())
    sig = defaultdict(dict)  # c -> {arch: w}
    for c, ac in card_arch.items():
        n_c = sum(ac.values())
        for a, n_ac in ac.items():
            p_a_given_c = n_ac / n_c
            if p_a_given_c < MIN_SIG_P:
                continue
            p_a = arch_n[a] / total
            w = math.log(p_a_given_c / p_a)
            sig[c][a] = round(w, 3)
    return sig, arch_n


def load_canonical():
    table = {}
    for p in POOL.glob('*.csv'):
        arch = p.name.split('__')[0]
        if arch == 'other':
            continue
        table[arch] = [int(l) for l in p.read_text().splitlines() if l.strip()]
    return table


SIG, ARCH_N = build_signature(load_labeled())
CANON = load_canonical()


def classify_ids(visible_ids, margin=MARGIN):
    """visible id 列表 → (arch, canonical60) 或 None。"""
    score = defaultdict(float)
    for c in visible_ids:
        for a, w in SIG.get(c, {}).items():
            score[a] += w
    if not score:
        return None
    ranked = sorted(score.items(), key=lambda kv: -kv[1])
    top_a, top_s = ranked[0]
    second = ranked[1][1] if len(ranked) > 1 else 0.0
    if top_s <= 0 or top_s - second < margin:
        return None
    deck = CANON.get(top_a)
    if deck is None:
        return None
    return top_a, deck


def visible_opp_ids(obs, my_idx):
    """从 obs dict 抽对手可见卡 id (active/bench 含 preEvolution + discard + 翻开的 prize)。"""
    cur = obs.get('current') or {}
    players = cur.get('players') or []
    if len(players) < 2:
        return []
    opp = players[1 - my_idx]
    ids = []
    for zone in ('active', 'bench'):
        for pk in (opp.get(zone) or []):
            if not isinstance(pk, dict):
                continue
            if pk.get('id'):
                ids.append(pk['id'])
            for c in (pk.get('preEvolution') or []):
                if isinstance(c, dict) and c.get('id'):
                    ids.append(c['id'])
    for c in (opp.get('discard') or []):
        if isinstance(c, dict) and c.get('id'):
            ids.append(c['id'])
    for c in (opp.get('prize') or []):
        if isinstance(c, dict) and c.get('id'):  # 翻开的奖品卡
            ids.append(c['id'])
    return ids


def classify_obs(obs, my_idx, margin=MARGIN):
    return classify_ids(visible_opp_ids(obs, my_idx), margin)


def selftest(margin=MARGIN):
    labeled = load_labeled()
    # 每 archetype 的宝可梦线 = 该牌组中 "宝可梦" 卡 (用签名卡近似: 出现卡即亮)
    # 模拟: visible = 牌组内所有独特卡 id (上界: 全亮); 再报"仅 Pokemon 线"近似
    per_arch = Counter(); correct = Counter(); abstain = Counter(); confuse = Counter()
    for a, dk in labeled:
        vis = list(dk.keys())  # 全亮上界
        r = classify_ids(vis, margin=margin)
        per_arch[a] += 1
        if r is None:
            abstain[a] += 1
        elif r[0] == a:
            correct[a] += 1
        else:
            confuse[(a, r[0])] += 1
    print(f'margin={margin}  labeled_seats={len(labeled)}  archs={len(per_arch)}')
    for a in sorted(per_arch):
        n = per_arch[a]
        print(f'  {a:12s} n={n:4d} 正确={correct[a]/n:.3f} 弃权={abstain[a]/n:.3f} '
              f'误识={(n-correct[a]-abstain[a])/n:.3f}')
    if confuse:
        print('  混淆:', confuse.most_common(8))
    # 签名卡样例
    for a in sorted(ARCH_N):
        tops = sorted(((c, d[a]) for c, d in SIG.items() if a in d),
                      key=lambda kv: -kv[1])[:5]
        print(f'  sig[{a}] top5: {tops}')


if __name__ == '__main__':
    selftest(float(sys.argv[1]) if len(sys.argv) > 1 else MARGIN)
