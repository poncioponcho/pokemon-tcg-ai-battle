"""alakazam_diag.py — ③ 诊断: 指定腿输局结构解剖 (logs 事件流 + 座位轮换版)

顾问校准 (2026-08-12):
  - 诊断第一问二选一: 输局"决策可救"还是"结构性(属性克制/奖品竞速)"? 结构性→停手不调参。
  - 复发模式才算信号; n=2000 仅诊断档。
  - 锚 = pristine config A = baseline policy + baseline 自家牌组。

协议修正 (2026-08-12, 纠错):
  - 牌组: pristine 模块 DECK_PATH='deck.csv' 相对 cwd, 静默捡到根目录 v24.8 →
    必须显式传 dsh._baseline_deck() (== submission_baseline/deck.csv, 真·config A 牌面)。
    【教训落账: 一切"模块自带牌组"断言不可信, 显式传牌组】
  - 座位: run_arena 先后手轮换; 裸 play() 固定我方 player0 先手。
    先手位在部分腿有大幅 skew (v24.8 实测 Alakazam 先0.84/后0.62) → 必须轮换。

事件源:
  obs['logs'] 增量事件流。type6/7 卡移动 (area: 1=DECK 2=HAND 3=DISCARD 4=ACTIVE 5=BENCH 6=PRIZE):
    toArea==3 且 fromArea∈{4,5} → KO (天然过滤训练家/能量); fromArea==6 且 toArea==2 → 拿奖品。
  type 15 攻击 (cardId=攻击者)。KO 的 cardId 双方可见; killer=最近一条对方 type15。
  奖品价值: card_table megaEx→3 / ex→2 / else 1。
  注: obs.current.players[1].prize 计数在 obs 中隐藏(常6), 不可用作事件源。

判读启发式:
  - 输局由 678(megaEx=3奖品) 死亡主导 + 凶手=对面主攻 + 长局竞速差 1 身位 → 结构性 → STOP。
  - 输局里我们 KO 效率骤降/同板面复发劣手 → 决策可救, 才谈调参。

用法: /opt/homebrew/bin/python3 experiments/alakazam_diag.py [--n 2000] [--leg Alakazam]
产物: experiments/runs/diag_<leg>.json
"""
import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

PROJ = Path('/Users/seyonmacbook/Desktop/Pokemon_TCG_AI_Battle_Challenge')
sys.path.insert(0, str(PROJ / 'experiments'))
import arena_runner as ar  # noqa: E402
import deck_search_hybrid as dsh  # noqa: E402

PRISTINE = PROJ / 'experiments/runs/_configA/main_configA_pristine.py'


def prize_value(ct, cid):
    e = ct.get(cid)
    if e is None:
        return None
    return 3 if e.megaEx else (2 if e.ex else 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--n', type=int, default=2000)
    ap.add_argument('--leg', default='Alakazam')
    ap.add_argument('--deck', default='baseline',
                    help="baseline=真·config A 自家牌组 (dsh._baseline_deck); 其它值=模块 my_deck (危险: 随 cwd 漂)")
    args = ap.parse_args()
    OUT = PROJ / f'experiments/runs/diag_{args.leg}.json'

    mod = ar.load_module(PRISTINE)
    first = ar.builtin_agent('first')
    ct = mod.card_table
    csv = list((PROJ / 'experiments/arena_pool/meta').glob(f'{args.leg}__*.csv'))[0]
    opp_deck = [int(l) for l in csv.read_text().splitlines() if l.strip()]
    our_deck = dsh._baseline_deck() if args.deck == 'baseline' else mod.my_deck
    assert len(our_deck) == 60 and len(opp_deck) == 60
    # 防漂移: 与提交件一致性硬校验
    live = [int(l) for l in (PROJ / 'submission_baseline/deck.csv').read_text().splitlines() if l.strip()]
    assert sorted(our_deck) == sorted(live), '诊断牌组 != submission_baseline/deck.csv!'

    games = []
    box = {'events': None}

    def rec_agent(obs_dict, config=None):
        evs = box['events']
        if evs is not None:
            turn = None
            try:
                turn = mod.to_observation_class(obs_dict).current.turn
            except Exception:
                pass
            for e in (obs_dict.get('logs') or []):
                t = e.get('type')
                if t == 15:
                    evs.append(('atk', turn, e.get('playerIndex'), e.get('cardId'), e.get('attackId')))
                elif t in (6, 7):
                    fa, ta = e.get('fromArea'), e.get('toArea')
                    if ta == 3 and fa in (4, 5):
                        evs.append(('ko', turn, e.get('playerIndex'), e.get('cardId'), fa))
                    elif fa == 6 and ta == 2:
                        evs.append(('prize', turn, e.get('playerIndex')))
        return mod.agent(obs_dict)

    t0 = time.time()
    for g in range(args.n):
        we = g % 2  # 座位轮换: 偶数局我方 player0(先手), 奇数局 player1(后手)
        box['events'] = []
        fns = [rec_agent, first] if we == 0 else [first, rec_agent]
        dks = [our_deck, opp_deck] if we == 0 else [opp_deck, our_deck]
        r = ar.play(fns, dks)
        evs = box['events']
        box['events'] = None

        last_atk = {0: None, 1: None}
        my_deaths, their_deaths = [], []
        prizes = {'us': 0, 'them': 0}
        first_blood = None
        for ev in evs:
            if ev[0] == 'atk':
                _, _, side, cid, aid = ev
                last_atk[side] = (cid, aid)
            elif ev[0] == 'ko':
                _, turn, side, victim, fa = ev
                killer = last_atk[1 - side]
                rec = (victim, prize_value(ct, victim),
                       killer[0] if killer else None, 'active' if fa == 4 else 'bench')
                (my_deaths if side == we else their_deaths).append(rec)
            else:
                _, _, side = ev
                prizes['us' if side == we else 'them'] += 1
                if first_blood is None:
                    first_blood = 'us' if side == we else 'them'
        winner = r['winner']
        win = 1 if winner == we else (0 if winner == 1 - we else -1)
        games.append({
            'win': win, 'seat': 'first' if we == 0 else 'second',
            'steps': r['steps'], 'fault': r.get('fault'),
            'my_deaths': my_deaths, 'their_deaths': their_deaths,
            'prizes_us': prizes['us'], 'prizes_them': prizes['them'],
            'first_blood': first_blood,
        })
        if (g + 1) % 500 == 0:
            print(f'  {g+1}/{args.n} ({time.time()-t0:.0f}s)', flush=True)

    # ---------- 聚合 ----------
    W = [g for g in games if g['win'] == 1]
    L = [g for g in games if g['win'] == 0]
    D = [g for g in games if g['win'] == -1]
    n = len(games)

    def mean(xs):
        return round(sum(xs) / len(xs), 2) if xs else None

    def wr_of(gs):
        return round(sum(1 for g in gs if g['win'] == 1) / max(1, len(gs)), 4)

    def agg_deaths(gs, key):
        victims, killers, pairs = Counter(), Counter(), Counter()
        val = 0
        cnt678 = 0
        for g in gs:
            for victim, v, killer, loc in g[key]:
                victims[(victim, v)] += 1
                killers[killer] += 1
                pairs[(killer, victim)] += 1
                val += v or 0
                if victim == 678:
                    cnt678 += 1
        ng = max(1, len(gs))
        return {
            'deaths_per_game': round(sum(victims.values()) / ng, 3),
            'prize_value_per_game': round(val / ng, 3),
            'victims': [(str(k), c) for k, c in victims.most_common(8)],
            'killers': [(str(k), c) for k, c in killers.most_common(8)],
            'killer_x_victim': [(str(k), c) for k, c in pairs.most_common(8)],
            'd678_per_game': round(cnt678 / ng, 3),
        }

    fb = Counter((g['first_blood'], g['win']) for g in games)
    lenb = Counter()
    for g in L:
        lenb['≤8t' if g['steps'] <= 8 else ('9-16t' if g['steps'] <= 16 else '≥17t')] += 1

    report = {
        'ts': time.time(), 'leg': args.leg, 'n': n,
        'wr': wr_of(games),
        'wr_by_seat': {
            'first': wr_of([g for g in games if g['seat'] == 'first']),
            'second': wr_of([g for g in games if g['seat'] == 'second']),
        },
        'deck': 'baseline own (dsh._baseline_deck, == submission_baseline/deck.csv)' if args.deck == 'baseline' else 'module my_deck (cwd-dependent!)',
        'anchor': 'pristine config A (runs/_configA) + seat rotation',
        'wins': len(W), 'losses': len(L), 'draws': len(D),
        'faults': sum(1 for g in games if g['fault']),
        'avg_steps': {'win': mean([g['steps'] for g in W]), 'loss': mean([g['steps'] for g in L])},
        'loss_len_buckets': dict(lenb),
        'first_blood': {
            'us_rate': round((fb[('us', 1)] + fb[('us', 0)]) / n, 4),
            'p_win_if_us': round(fb[('us', 1)] / max(1, fb[('us', 1)] + fb[('us', 0)]), 4),
            'p_win_if_them': round(fb[('them', 1)] / max(1, fb[('them', 1)] + fb[('them', 0)]), 4),
        },
        'prize_race': {
            'us_in_wins': mean([g['prizes_us'] for g in W]),
            'us_in_losses': mean([g['prizes_us'] for g in L]),
            'them_in_wins': mean([g['prizes_them'] for g in W]),
            'them_in_losses': mean([g['prizes_them'] for g in L]),
        },
        'our_deaths_in_losses': agg_deaths(L, 'my_deaths'),
        'our_deaths_in_wins': agg_deaths(W, 'my_deaths'),
        'their_deaths_in_losses': agg_deaths(L, 'their_deaths'),
        'their_deaths_in_wins': agg_deaths(W, 'their_deaths'),
        'elapsed_s': round(time.time() - t0, 1),
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=1))
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
