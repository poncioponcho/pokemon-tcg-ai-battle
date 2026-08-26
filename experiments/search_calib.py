"""search_calib.py — beam M2 前置校准

校准三件事 (M2 计分/触发的前提):
  A. 真实对局终局 obs.current.result 语义: 0/1=绝对座位胜, 2=平 (文档说法) — 用奖品数独立印证
  B. 搜索世界 rollout 终局 result 语义同上 (players[] 是绝对索引) — 用奖品数交叉验证
  C. MAIN(ctx=0) 攻击选项结构: type==13 且带 attackId (M2 触发条件的依据)

用法: /opt/homebrew/bin/python3 experiments/search_calib.py
"""
import json, sys
from collections import Counter
from pathlib import Path

PROJ = Path('/Users/seyonmacbook/Desktop/Pokemon_TCG_AI_Battle_Challenge')
COMP = PROJ / 'inference/comp_data/sample_submission/sample_submission'
sys.path.insert(0, str(COMP))
import cg.game as G  # noqa: E402
from cg import api as A  # noqa: E402

DECK = [int(l) for l in (PROJ / 'deck.csv').read_text().splitlines() if l.strip()]
SAMPLE = [int(l) for l in (COMP / 'deck.csv').read_text().splitlines() if l.strip()]
N = 12


def first_pick(sel):
    opts = (sel or {}).get('option') or []
    mc = (sel or {}).get('maxCount') or 1
    return list(range(min(mc, len(opts))))


def part_a():
    print('=== A. 真实对局 result 语义 ===')
    rows = []
    for g in range(N):
        obs, sd = G.battle_start(DECK, SAMPLE)
        assert obs is not None, f'battle_start failed {sd.errorPlayer}'
        steps = 0
        while steps < 3000:
            sel = obs.get('select')
            if not sel or not sel.get('option'):
                break
            try:
                obs = G.battle_select(first_pick(sel))
            except (IndexError, ValueError):
                obs = G.Battle.obs
                break
            steps += 1
        cur = (obs or {}).get('current') or {}
        yi = cur.get('yourIndex')
        res = cur.get('result')
        pls = cur.get('players') or [{}, {}]
        my_prize = len(pls[yi].get('prize') or []) if yi is not None else -1
        op_prize = len(pls[1 - yi].get('prize') or []) if yi is not None else -1
        rows.append((yi, res, my_prize, op_prize, cur.get('turn')))
        print(f'  g{g}: yi={yi} result={res} myPrize={my_prize} oppPrize={op_prize} turn={cur.get("turn")}')
        G.battle_finish()
    # 交叉: result==yi 应 ↔ oppPrize==0 (我方拿完奖品)
    ok = sum(1 for yi, res, mp, op, _ in rows
             if (res == yi and op == 0) or (res == 1 - yi and mp == 0) or res == 2)
    print(f'  → {ok}/{N} 局 result 与奖品数自洽 (0/1=绝对座位胜 成立)')


def part_b():
    print('=== B. 搜索世界 result 语义 (root 起全 rollout) ===')
    rows = []
    for g in range(N):
        obs, sd = G.battle_start(DECK, SAMPLE)
        assert obs is not None
        steps = 0
        while steps < 200:  # 走到第一个 ctx=0 MAIN
            sel = obs.get('select')
            if sel and sel.get('option') and sel.get('context') == 0:
                break
            obs = G.battle_select(first_pick(sel))
            steps += 1
        cur = obs['current']; yi = cur['yourIndex']
        me, opp = cur['players'][yi], cur['players'][1 - yi]
        hand_ids = [c['id'] for c in (me.get('hand') or []) if isinstance(c, dict) and c.get('id')]
        rem = Counter(DECK)
        for h in hand_ids:
            rem[h] -= 1
        remaining = [cid for cid, k in rem.items() for _ in range(k)]
        n_prize = len(me.get('prize') or [])
        your_prize, your_deck = remaining[:n_prize], remaining[n_prize:]
        oh = opp.get('handCount', 0); op_ = len(opp.get('prize') or [])
        opp_hand, opp_prize = SAMPLE[:oh], SAMPLE[oh:oh + op_]
        opp_deck = SAMPLE[oh + op_:]

        obs_dc = A.to_observation_class(obs)
        st = A.search_begin(obs_dc, your_deck, your_prize, opp_deck, opp_prize, opp_hand, [])
        root_yi = st.observation.current.yourIndex
        nsteps = 0
        while nsteps < 3000:
            o = st.observation
            if o.select is None or not o.select.option:
                break
            pick = first_pick({'option': o.select.option, 'maxCount': o.select.maxCount})
            try:
                st = A.search_step(st.searchId, pick)
            except ValueError as e:
                if 'battle has ended' in str(e):
                    break
                raise
            nsteps += 1
        fcur = st.observation.current
        res = fcur.result
        p0_prize = len(fcur.players[0].prize or [])
        p1_prize = len(fcur.players[1].prize or [])
        p0_deck = fcur.players[0].deckCount; p1_deck = fcur.players[1].deckCount
        rows.append((root_yi, res, p0_prize, p1_prize, p0_deck, p1_deck, fcur.turn))
        print(f'  g{g}: root_yi={root_yi} result={res} p0Prize={p0_prize} p1Prize={p1_prize} '
              f'p0Deck={p0_deck} p1Deck={p1_deck} turn={fcur.turn} steps={nsteps}')
        A.search_end()
        G.battle_finish()
    ok = sum(1 for _, res, p0, p1, d0, d1, _ in rows
             if (res == 0 and (p0 == 0 or d1 == 0)) or (res == 1 and (p1 == 0 or d0 == 0)) or res == 2)
    print(f'  → {ok}/{N} 局 result 与奖品/牌库自洽 (绝对座位语义 成立)')


def part_c():
    print('=== C. MAIN 攻击选项结构 ===')
    obs, sd = G.battle_start(DECK, SAMPLE)
    assert obs is not None
    steps = 0
    found = False
    while steps < 60:
        sel = obs.get('select')
        if sel and sel.get('option') and sel.get('context') == 0:
            types = Counter(o.get('type') for o in sel['option'] if isinstance(o, dict))
            atk = [o for o in sel['option'] if isinstance(o, dict) and o.get('type') == 13]
            cur = obs.get('current') or {}
            if atk:
                print(f'  turn={cur.get("turn")} opts={len(sel["option"])} type分布={dict(types)}')
                print(f'  攻击选项样例 keys={sorted(atk[0].keys())} attackId={atk[0].get("attackId")} '
                      f'n_attacks={len(atk)}')
                found = True
                break
        obs = G.battle_select(first_pick(sel))
        steps += 1
    if not found:
        print('  60 步内未遇到带攻击选项的 MAIN select')
    G.battle_finish()


if __name__ == '__main__':
    part_a()
    part_b()
    part_c()
    print('[done]')
