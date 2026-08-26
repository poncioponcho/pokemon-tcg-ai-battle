# -*- coding: utf-8 -*-
"""vsfirst_slice_p1.py — P1 守成/逆转归因切片（零重跑，读 runs/vsfirst_race.jsonl）

回答三个问题：
  Q1 开局 active 是谁、首个被 KO 在几回合 —— 开局竞速慢的结构定位
  Q2 先拿首奖的局里输掉的 56% 去了哪 —— 守成失败归因
  Q3 先丢首奖仅 66 局逆转 —— 逆转局与崩盘局差在哪
"""
import json
import statistics
from collections import Counter
from pathlib import Path

RUNS = Path(__file__).resolve().parent / 'runs'
rows = [json.loads(l) for l in open(RUNS / 'vsfirst_race.jsonl', encoding='utf-8')]
wins = [r for r in rows if r['a_won']]
losses = [r for r in rows if not r['a_won']]
n = len(rows)


def wr_of(rs):
    return round(sum(1 for r in rs if r['a_won']) / max(1, len(rs)), 4)


print(f'=== P1 切片 n={n} ({len(wins)}W {len(losses)}L) ===\n')

# ---- Q1 开局 active 与首 KO ----
print('--- Q1 开局 active（我方）---')
oc = Counter(r['opening_active'] for r in rows)
for cid, c in oc.most_common(8):
    rs = [r for r in rows if r['opening_active'] == cid]
    print(f'  active={str(cid):>6}: n={c:>4} wr={wr_of(rs)}')
print('--- Q1 对手开局 active ---')
oc2 = Counter(r['opp_opening_active'] for r in rows)
for cid, c in oc2.most_common(8):
    rs = [r for r in rows if r['opp_opening_active'] == cid]
    print(f'  opp_active={str(cid):>6}: n={c:>4} wr={wr_of(rs)}')

for label, rs in (('wins', wins), ('losses', losses)):
    kt = [r['first_ko_taken_turn'] for r in rs if r['first_ko_taken_turn'] is not None]
    early = sum(1 for t in kt if t <= 6)
    kos = [r['kos_taken'] for r in rs]
    print(f'Q1 {label}: 首个被KO回合 mean={round(statistics.mean(kt),1) if kt else None} '
          f'| ≤6回合被KO率={round(early/max(1,len(rs)),4)} '
          f'| 场均被KO次数={round(statistics.mean(kos),2)} '
          f'| 从未被KO局占比={round(sum(1 for r in rs if r["kos_taken"]==0)/max(1,len(rs)),4)}')

# ---- Q2 守成：先拿首奖的局 ----
we_first_prize = [r for r in rows
                  if r['first_ahead_turn'] is not None
                  and (r['first_behind_turn'] is None
                       or r['first_ahead_turn'] < r['first_behind_turn'])]
wfp_w = [r for r in we_first_prize if r['a_won']]
wfp_l = [r for r in we_first_prize if not r['a_won']]
print(f'\n--- Q2 先拿首奖 n={len(we_first_prize)} (赢{len(wfp_w)} 输{len(wfp_l)}) ---')
for label, rs in (('守住', wfp_w), ('守丢', wfp_l)):
    if not rs:
        continue
    print(f'  {label}: 步数mean={round(statistics.mean(r["steps"] for r in rs),1)} '
          f'| 终局奖品差mean={round(statistics.mean(r["final_prize_diff"] for r in rs if r["final_prize_diff"] is not None),2)} '
          f'| 场均被KO={round(statistics.mean(r["kos_taken"] for r in rs),2)} '
          f'| 攻击让度mean={round(statistics.mean(r["atk_pass_rate"] for r in rs if r["atk_pass_rate"] is not None),3)} '
          f'| 后被反超率(后又落后)={round(sum(1 for r in rs if r["first_behind_turn"] is not None)/len(rs),3)}')

# ---- Q3 逆转：先丢首奖的局 ----
they_first = [r for r in rows
              if r['first_behind_turn'] is not None
              and (r['first_ahead_turn'] is None
                   or r['first_behind_turn'] < r['first_ahead_turn'])]
tf_w = [r for r in they_first if r['a_won']]
tf_l = [r for r in they_first if not r['a_won']]
print(f'\n--- Q3 先丢首奖 n={len(they_first)} (逆转{len(tf_w)} 崩{len(tf_l)}) ---')
for label, rs in (('逆转', tf_w), ('崩盘', tf_l)):
    if not rs:
        continue
    fkt = [r['first_ko_taken_turn'] for r in rs if r['first_ko_taken_turn'] is not None]
    print(f'  {label}: 首丢奖回合mean={round(statistics.mean(r["first_behind_turn"] for r in rs),1)} '
          f'| 首个被KO回合mean={round(statistics.mean(fkt),1) if fkt else None} '
          f'| 步数mean={round(statistics.mean(r["steps"] for r in rs),1)} '
          f'| 终局奖品差mean={round(statistics.mean(r["final_prize_diff"] for r in rs if r["final_prize_diff"] is not None),2)} '
          f'| 攻击让度mean={round(statistics.mean(r["atk_pass_rate"] for r in rs if r["atk_pass_rate"] is not None),3)}')

# ---- Q4 分侧 × 首奖 交叉 ----
print('\n--- Q4 分侧 × 首奖 ---')
for second in (False, True):
    sub = [r for r in rows if r['we_second'] == second]
    wf = [r for r in sub if r in we_first_prize]
    tf = [r for r in sub if r in they_first]
    print(f'  {"后手" if second else "先手"}: n={len(sub)} wr={wr_of(sub)} '
          f'| 先拿首奖率={round(len(wf)/max(1,len(sub)),3)} '
          f'| 先丢首奖率={round(len(tf)/max(1,len(sub)),3)}')
