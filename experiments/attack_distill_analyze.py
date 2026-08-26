"""attack_distill_analyze.py — 攻击蒸馏记录分析

读 experiments/runs/attack_distill_records.jsonl (probe 产物),
输出 experiments/runs/attack_distill_probe.md 诊断报告。

回答三个问题:
  Q-A 一致率: 规则 vs 精英 / NN vs 精英 / 规则 vs NN (按 ctx 分)
  Q-B 混淆对: (规则选择 → 精英选择) top 对, 重点攻击 id 对
  Q-C 局面切片: top 分歧对发生在什么局面 (对方HP/我方能量/奖品差/回合/胜败)
"""
import json, os, sys
from collections import Counter, defaultdict

PROJ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RECS = os.path.join(PROJ, 'experiments/runs/attack_distill_records.jsonl')
OUT_MD = os.path.join(PROJ, 'experiments/runs/attack_distill_probe.md')

ATK_NAMES = {981: 'Riolu atk(981)', 982: 'Mega Brave 270(982)', 983: 'Aura Jab 130(983)'}


def load():
    rows = []
    with open(RECS) as f:
        for line in f:
            rows.append(json.loads(line))
    return rows


def primary(tags):
    """决策标签列表 → 主标签 (攻击优先, 否则第一个)。"""
    atks = [t for t in tags if t.startswith('atk:')]
    return atks[0] if atks else (tags[0] if tags else 'none')


def is_atk(tag):
    return tag.startswith('atk:')


def bucket_hp(hp):
    for lo, hi, name in [(0, 60, '≤60'), (61, 130, '61-130'), (131, 200, '131-200'),
                         (201, 270, '201-270'), (271, 340, '271-340'), (341, 9999, '>340')]:
        if lo <= hp <= hi:
            return name
    return '?'


def main():
    rows = load()
    print(f'records: {len(rows)}')
    by_ctx = defaultdict(list)
    for r in rows:
        by_ctx[str(r['ctx'])].append(r)

    L = []
    L.append('# 攻击选择蒸馏诊断报告 (2026-08-10)')
    L.append('')
    L.append(f"- 记录: {len(rows)} 条攻击相关决策, 来自 800 个 Lucario 驾驶局 (all_replays 最新段)")
    L.append(f"- 三方: elite=回放真实选择 / teacher=NN(kerr_teacher_v3) / rule=当前 main.py v24.8")
    L.append(f"- ctx 分布: { {k: len(v) for k, v in sorted(by_ctx.items(), key=lambda x: -len(x[1]))} }")
    L.append('')

    # ---- Q-A 一致率 ----
    L.append('## Q-A 三方一致率 (主标签 = 攻击选项优先)')
    L.append('')
    L.append('| 子集 | n | rule==elite | NN==elite | rule==NN | rule 攻击率 | elite 攻击率 | NN 攻击率 |')
    L.append('|---|---:|---:|---:|---:|---:|---:|---:|')
    for name, subset in [('全部', rows)] + [(f'ctx={k}', v) for k, v in sorted(by_ctx.items(), key=lambda x: -len(x[1])) if k in ('0', '7')]:
        n = len(subset)
        re_ = sum(1 for r in subset if primary(r['rule']) == primary(r['elite'])) / n
        ne = sum(1 for r in subset if r['nn'] and primary([r['nn']]) == primary(r['elite'])) / n
        rn = sum(1 for r in subset if r['nn'] and primary(r['rule']) == primary([r['nn']])) / n
        ra = sum(1 for r in subset if is_atk(primary(r['rule']))) / n
        ea = sum(1 for r in subset if is_atk(primary(r['elite']))) / n
        na = sum(1 for r in subset if r['nn'] and is_atk(r['nn'])) / n
        L.append(f'| {name} | {n} | {re_:.3f} | {ne:.3f} | {rn:.3f} | {ra:.3f} | {ea:.3f} | {na:.3f} |')
    L.append('')

    # ---- Q-B 混淆对 ----
    L.append('## Q-B 分歧混淆对 (rule → elite, 仅两者不同的决策)')
    L.append('')
    for ctx_name, subset in [('ctx=7 (纯攻击选择)', by_ctx.get('7', [])),
                             ('ctx=0 (主菜单含攻击)', by_ctx.get('0', []))]:
        pairs = Counter()
        for r in subset:
            rp, ep = primary(r['rule']), primary(r['elite'])
            if rp != ep:
                pairs[(rp, ep)] += 1
        L.append(f'### {ctx_name} — top 15 分歧对 (n={sum(pairs.values())})')
        L.append('')
        L.append('| rule 选 | elite 选 | 次数 | 占比 |')
        L.append('|---|---|---:|---:|')
        tot = sum(pairs.values()) or 1
        for (rp, ep), c in pairs.most_common(15):
            L.append(f'| {rp} | {ep} | {c} | {c / tot:.1%} |')
        L.append('')

    # ---- Q-C 局面切片: 对每个 top 攻击对分歧, 给局面统计 ----
    L.append('## Q-C 局面切片 (top 攻击分歧对的局面特征)')
    L.append('')
    for ctx_name, subset in [('ctx=7', by_ctx.get('7', [])), ('ctx=0', by_ctx.get('0', []))]:
        groups = defaultdict(list)
        for r in subset:
            rp, ep = primary(r['rule']), primary(r['elite'])
            if rp != ep and (is_atk(rp) or is_atk(ep)):
                groups[(rp, ep)].append(r)
        for (rp, ep), rs in sorted(groups.items(), key=lambda x: -len(x[1]))[:6]:
            if len(rs) < 30:
                continue
            n = len(rs)
            opp_hp = [r['opp']['active_hp'] for r in rs]
            my_en = [r['me']['active_energy'] for r in rs]
            turns = [r['turn'] for r in rs]
            prize_d = [r['opp']['n_prize'] - r['me']['n_prize'] for r in rs]
            wins = sum(1 for r in rs if r.get('reward') and r['reward'] > 0)
            hp_buckets = Counter(bucket_hp(h) for h in opp_hp)
            nn_agree_elite = sum(1 for r in rs if r['nn'] and r['nn'] == ep) / n
            L.append(f'### {ctx_name} {rp} → elite {ep} (n={n})')
            L.append(f"- 对方 active HP 分布: {dict(hp_buckets.most_common())}")
            L.append(f"- 我方 active 能量: 均值 {sum(my_en)/n:.2f} | 回合: 均值 {sum(turns)/n:.1f} | 奖品差(opp-me): 均值 {sum(prize_d)/n:+.2f}")
            L.append(f"- elite 侧胜率: {wins/n:.2f} | NN 同意 elite: {nn_agree_elite:.2f}")
            # 我方/对方 active id top
            my_ids = Counter(r['me']['active_id'] for r in rs)
            opp_ids = Counter(r['opp']['active_id'] for r in rs)
            L.append(f"- 我方 active top: {my_ids.most_common(4)} | 对方 active top: {opp_ids.most_common(4)}")
            L.append('')

    # ---- 攻击 id 使用总览 ----
    L.append('## 攻击 ID 使用总览 (主标签)')
    L.append('')
    for who in ('elite', 'rule', 'nn'):
        c = Counter()
        for r in rows:
            t = primary(r[who] if who != 'nn' else ([r['nn']] if r['nn'] else []))
            if is_atk(t):
                c[t] += 1
        L.append(f'- {who}: {c.most_common(8)}')
    L.append('')

    with open(OUT_MD, 'w') as f:
        f.write('\n'.join(L))
    print(f'wrote {OUT_MD} ({len(L)} lines)')


if __name__ == '__main__':
    main()
