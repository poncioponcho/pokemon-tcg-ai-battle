"""search_spike.py — 官方引擎 Search API 本地可行性验证 (beam M1)

验证四件事:
  1. search_begin/search_step 能否从真实对局的当前 obs 建起搜索世界
  2. 搜索世界里双方 select 如何呈现 (yourIndex 是否翻转 → 是否要替对手走)
  3. 从同一状态能否多次 search_step 分支 (beam 的前提)
  4. 速度: μs/step, 单次全 rollout 耗时 → 决定 beam 宽度/深度预算

用法: /opt/homebrew/bin/python3 experiments/search_spike.py
"""
import json, os, sys, time
from pathlib import Path

PROJ = Path('/Users/seyonmacbook/Desktop/Pokemon_TCG_AI_Battle_Challenge')
COMP = PROJ / 'inference/comp_data/sample_submission/sample_submission'
sys.path.insert(0, str(COMP))
from cg.game import battle_start, battle_select, battle_finish  # noqa: E402
from cg import api as A  # noqa: E402

DECK = [int(l) for l in (PROJ / 'deck.csv').read_text().splitlines() if l.strip()]
SAMPLE = [int(l) for l in (COMP / 'deck.csv').read_text().splitlines() if l.strip()]


def main():
    obs, sd = battle_start(DECK, SAMPLE)
    assert obs is not None, f'battle_start failed errorPlayer={sd.errorPlayer}'
    sel = obs.get('select') or {}
    cur = obs.get('current') or {}
    yi = cur.get('yourIndex')
    print(f'[real] first select: ctx={sel.get("context")} type={sel.get("type")} '
          f'n_opts={len(sel.get("option") or [])} yourIndex={yi} turn={cur.get("turn")} '
          f'sbi_len={len(obs.get("search_begin_input") or "")}')

    # 走到第一个 MAIN(ctx=0) 且属于我们的决策 (setup 阶段的 select 也试试, 先记录)
    steps = 0
    while steps < 200:
        sel = obs.get('select')
        if sel and sel.get('option') and sel.get('context') == 0:
            break
        n = len((sel or {}).get('option') or [])
        if n == 0:
            print('[real] no options, stop'); return
        obs = battle_select([0])
        steps += 1
    sel = obs['select']; cur = obs['current']
    yi = cur.get('yourIndex', 0)
    me = cur['players'][yi]; opp = cur['players'][1 - yi]
    print(f'[real] at MAIN select: turn={cur.get("turn")} yi={yi} '
          f'n_opts={len(sel["option"])} myHand={len(me.get("hand") or [])} '
          f'myDeck={me.get("deckCount")} myPrize={len(me.get("prize") or [])} '
          f'oppHand={opp.get("handCount")} oppDeck={opp.get("deckCount")} oppPrize={len(opp.get("prize") or [])}')

    # ---- 构造隐藏信息预测 (spike: 用双方真牌组的任意一致切分) ----
    from collections import Counter
    hand_ids = [c['id'] for c in (me.get('hand') or []) if isinstance(c, dict) and c.get('id')]
    rem = Counter(DECK)
    rem.subtract(Counter(hand_ids))
    remaining = [cid for cid in DECK if rem[cid] > 0 and not rem.subtract(Counter([cid]))]
    # 上面的 trick 写起来绕, 直接重算:
    rem = Counter(DECK)
    for h in hand_ids:
        rem[h] -= 1
    remaining = []
    for cid, k in rem.items():
        remaining += [cid] * k
    n_prize = len(me.get('prize') or [])
    your_prize = remaining[:n_prize]
    your_deck = remaining[n_prize:]
    opp_hand = SAMPLE[:opp.get('handCount', 7)]
    opp_prize = SAMPLE[len(opp_hand):len(opp_hand) + len(opp.get('prize') or [])]
    opp_deck = SAMPLE[len(opp_hand) + len(opp_prize):]
    print(f'[guess] your_deck={len(your_deck)} prize={len(your_prize)} | '
          f'opp hand={len(opp_hand)} deck={len(opp_deck)} prize={len(opp_prize)}')

    # ---- search_begin ----
    obs_dc = A.to_observation_class(obs)
    t0 = time.perf_counter()
    root = A.search_begin(obs_dc, your_deck, your_prize, opp_deck, opp_prize, opp_hand, [])
    t1 = time.perf_counter()
    print(f'[search] begin OK in {(t1-t0)*1e3:.1f}ms, root searchId={root.searchId}')
    ro = root.observation
    print(f'[search] root obs: ctx={ro.select.context if ro.select else None} '
          f'n_opts={len(ro.select.option) if ro.select and ro.select.option else 0} '
          f'yourIndex={ro.current.yourIndex if ro.current else None} turn={ro.current.turn if ro.current else None}')

    # ---- 分支测试: 从 root 对前 3 个选项各 step 一次 ----
    n_root_opts = len(ro.select.option)
    children = []
    for i in range(min(3, n_root_opts)):
        try:
            ch = A.search_step(root.searchId, [i])
            children.append(ch)
            co = ch.observation
            print(f'[branch] opt{i} → searchId={ch.searchId} ctx={co.select.context if co.select else None} '
                  f'n_opts={len(co.select.option) if co.select and co.select.option else 0} '
                  f'yi={co.current.yourIndex if co.current else None} turn={co.current.turn if co.current else None} '
                  f'step={co.current.turnActionCount if co.current else None}')
        except Exception as e:
            print(f'[branch] opt{i} → {type(e).__name__}: {e}')

    # ---- 全 rollout 计时: 从 child[0] 一直走 builtin-first 策略直到结束 ----
    if children:
        st = children[0]
        t0 = time.perf_counter()
        nsteps = 0
        yi_seen = set()
        while nsteps < 3000:
            o = st.observation
            if o.select is None or not o.select.option:
                break
            yi_seen.add(o.current.yourIndex if o.current else -1)
            n_o = len(o.select.option)
            mc = o.select.maxCount or 1
            pick = list(range(min(mc, n_o)))
            try:
                st = A.search_step(st.searchId, pick)
                nsteps += 1
            except ValueError as e:
                if 'battle has ended' in str(e):
                    break
                raise
        dt = time.perf_counter() - t0
        res = st.observation.current.result if st.observation.current else None
        print(f'[rollout] {nsteps} steps in {dt*1e3:.1f}ms ({dt/max(nsteps,1)*1e6:.1f}μs/step), '
              f'end result={res} turn={st.observation.current.turn if st.observation.current else "?"} '
              f'yi_seen={sorted(yi_seen)}')

    A.search_end()
    battle_finish()
    print('[done] search_end + battle_finish OK')


if __name__ == '__main__':
    main()
