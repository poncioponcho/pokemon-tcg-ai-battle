# -*- coding: utf-8 -*-
"""vsfirst_slice_f2.py — F2 mega 决斗节奏切片（读 runs/vsfirst_race.jsonl）

回答（对应 ledger f2 设计问题）：
  Q1 我方 678 首次上场：回合/能量/当时奖品差 —— all-in 时机是否错误
  Q2 678 死亡瞬间：bench 有几只 ≥2 能/已进化接续打手 —— 是否裸奔送 3 奖
  Q3 非 677 起手局：677 几回合才到 bench、是否来得及进化 —— T1 检索缺口
"""
import json
import statistics
from pathlib import Path

RUNS = Path(__file__).resolve().parent / 'runs'
rows = [json.loads(l) for l in open(RUNS / 'vsfirst_race.jsonl', encoding='utf-8')]
wins = [r for r in rows if r['a_won']]
losses = [r for r in rows if not r['a_won']]
print(f'=== F2 决斗切片 n={len(rows)} ({len(wins)}W {len(losses)}L) ===\n')


def mean(xs):
    xs = [x for x in xs if x is not None]
    return round(statistics.mean(xs), 2) if xs else None


# ---- Q1 mega 上场时机 ----
print('--- Q1 我方 678 首次上场 ---')
for label, rs in (('wins', wins), ('losses', losses)):
    m = [r for r in rs if r['mega_first_turn'] is not None]
    print(f'  {label}: 上场率={round(len(m)/max(1,len(rs)),3)} '
          f'| 上场回合 mean={mean([r["mega_first_turn"] for r in m])} '
          f'| 上场时能量 mean={mean([r["mega_first_nrg"] for r in m])} '
          f'| 上场时奖品差 mean={mean([r["mega_first_prize_diff"] for r in m])}')
no_mega_w = sum(1 for r in wins if r['mega_first_turn'] is None)
no_mega_l = sum(1 for r in losses if r['mega_first_turn'] is None)
print(f'  678从未上场: 胜局 {no_mega_w} ({round(no_mega_w/max(1,len(wins)),3)}) '
      f'败局 {no_mega_l} ({round(no_mega_l/max(1,len(losses)),3)})')

# ---- Q2 mega 死亡/裸奔 ----
print('\n--- Q2 678 死亡瞬间 bench 接续 ---')
for label, rs in (('wins', wins), ('losses', losses)):
    deaths = [(r, d) for r in rs for d in r['mega_deaths']]
    if not deaths:
        print(f'  {label}: 无死亡事件')
        continue
    bare = sum(1 for _, d in deaths if d['bench_ready_nrg2'] == 0)
    evo = sum(1 for _, d in deaths if d['bench_evolved'] > 0)
    print(f'  {label}: 死亡次数={len(deaths)} '
          f'| 死亡回合 mean={mean([d["turn"] for _, d in deaths])} '
          f'| 死亡时奖品差 mean={mean([d["prize_diff"] for _, d in deaths])}')
    print(f'       bench裸奔(无≥2能)率={round(bare/len(deaths),3)} '
          f'| bench有进化体率={round(evo/len(deaths),3)} '
          f'| bench数量 mean={mean([d["bench_n"] for _, d in deaths])} '
          f'| ≥2能打手数 mean={mean([d["bench_ready_nrg2"] for _, d in deaths])}')

# 死亡时奖品差分布（是否死亡=崩盘信号）
dl = [d['prize_diff'] for r in losses for d in r['mega_deaths'] if d['prize_diff'] is not None]
if dl:
    ahead = sum(1 for x in dl if x <= 0)  # 我方奖品少=领先
    print(f'  败局 678 死亡时仍领先(奖品差≤0)占比={round(ahead/len(dl),3)} '
          f'—— 高则说明死亡本身即崩盘起点')

# ---- Q3 非 677 起手局 ----
print('\n--- Q3 非 677 起手局 ---')
n677 = [r for r in rows if r['opening_active'] not in (677, None)]
for label, rs in (('全体', n677),):
    w = [r for r in rs if r['a_won']]
    l = [r for r in rs if not r['a_won']]
    got = [r for r in rs if r['bench677_turn'] is not None]
    print(f'  n={len(rs)} wr={round(len(w)/max(1,len(rs)),4)} '
          f'| 677到bench率={round(len(got)/max(1,len(rs)),3)} '
          f'| 到bench回合 mean={mean([r["bench677_turn"] for r in got])}')
    mega = [r for r in rs if r['mega_first_turn'] is not None]
    print(f'    678上场率={round(len(mega)/max(1,len(rs)),3)} '
          f'| 上场回合 mean={mean([r["mega_first_turn"] for r in mega])} '
          f'vs 677起手局上场回合 mean='
          f'{mean([r["mega_first_turn"] for r in rows if r["opening_active"]==677 and r["mega_first_turn"] is not None])}')
    for sub, nm in ((w, '其中胜局'), (l, '其中败局')):
        g2 = [r for r in sub if r['bench677_turn'] is not None]
        print(f'    {nm}: n={len(sub)} 677到bench率={round(len(g2)/max(1,len(sub)),3)} '
              f'回合 mean={mean([r["bench677_turn"] for r in g2])}')

# ---- Q4 能量去向（F2a 唯一判据）----
print('\n--- Q4 能量去向（attach 目标占比）---')
for label, rs in (('wins', wins), ('losses', losses)):
    tot = sum(r['attach_total'] for r in rs)
    if tot == 0:
        print(f'  {label}: 无 attach 记录')
        continue
    m = sum(r['attach_to_mega_line'] for r in rs)
    a678 = sum(r['attach_to_678'] for r in rs)
    nc = sum(r['attach_to_noncore'] for r in rs)
    print(f'  {label}: attach总次数={tot} (场均{round(tot/len(rs),2)}) '
          f'| mega线(677+678)={round(m/tot,3)} 其中678={round(a678/tot,3)} '
          f'| 非核心(炮灰/二线)={round(nc/tot,3)}')
# 分阶段：678 上场前 vs 上场后 的能量去向（非核心分流是否发生在成型前）
for label, rs in (('wins', wins), ('losses', losses)):
    pre = [r for r in rs if r['mega_first_turn'] is None]
    print(f'  {label} 678未上场局 n={len(pre)}: '
          f'attach_to_mega场均={round(sum(r["attach_to_mega_line"] for r in pre)/max(1,len(pre)),2)} '
          f'noncore场均={round(sum(r["attach_to_noncore"] for r in pre)/max(1,len(pre)),2)}')

# 对手 723(mega) 上场情况无法直接观测(opp_active id 已录, 723=进化体)
print('\n--- 附: 对手 active 分布(末次记录) ---')
from collections import Counter
c = Counter()
for r in rows:
    pass  # opp 轨迹未按决策存 jsonl, 仅 opening; 略
print('  (opp mega 上场轨迹需决策级记录, 本轮未存 — 若需要下轮加)')
