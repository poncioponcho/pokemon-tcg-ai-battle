# -*- coding: utf-8 -*-
"""vsfirst_diagnose.py — vs_first=0.37 系统性缺陷诊断（Tier 0 + Tier 1）

背景：builtin_agent('first') 是"无脑选 option 列表前 N 项"的 dumb greedy，
规则 agent 对它仅 ~0.37 胜率（先后手轮换、invalid=0）——合法但次优的步被稳定剥削。

Tier 0: 打 1 局，dump 每步 select 原始结构（验证引擎 option 排序假设、确认可分类字段）
Tier 1: 打 N 局 vs_first，包一层 agent 记录每个决策的类型/上下文/选项数，
        输出：败局按局长分桶（开局崩 vs 终盘输）、胜/败局决策类型频次差、先后手分侧胜率

用法:
  /opt/homebrew/bin/python3 experiments/vsfirst_diagnose.py --n 2000 --seed0 9000
产出:
  experiments/runs/vsfirst_tier0_dump.json   Tier 0 原始结构
  experiments/runs/vsfirst_diagnose.json     Tier 1 聚合报告
"""
import argparse
import json
import random
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

EXP = Path(__file__).resolve().parent
sys.path.insert(0, str(EXP))
from arena_runner import play, builtin_agent, SAMPLE_DECK, load_module, PROJ  # noqa: E402

RUNS = EXP / 'runs'
RUNS.mkdir(exist_ok=True)


def norm(mod, value, kind):
    """用 main.py 自己的规范化映射分类（单一事实源，不另造映射）。"""
    try:
        if kind == 'select':
            return mod._norm_select_type(value)
        if kind == 'context':
            return mod._norm_context(value)
        return mod._norm_type(value)
    except Exception:
        return value


class RecAgent:
    """包装规则 agent：逐决策记录 (sel_type, context, maxCount, n_options, 所选 option 类型)。"""
    def __init__(self, agent_fn, mod):
        self.fn = agent_fn
        self.mod = mod
        self.decisions = []       # 本局全部决策（dict）
        self.tier0_dump = []      # 前 K 步原始 select
        self.tier0_left = 40

    def __call__(self, obs):
        sel = obs.get('select')
        if sel is None:
            return self.fn(obs)
        act = self.fn(obs)
        opts = sel.get('option') or []
        opt_types = [norm(self.mod, o.get('type'), 'option')
                     if isinstance(o, dict) else '?' for o in opts]
        chosen_types = []
        for i in (act if isinstance(act, list) else [act]):
            if isinstance(i, int) and 0 <= i < len(opts):
                o = opts[i]
                chosen_types.append(norm(self.mod, o.get('type'), 'option')
                                    if isinstance(o, dict) else str(type(o).__name__))
        cur = obs.get('current') or {}
        players = cur.get('player') or cur.get('players') or []
        my_i = cur.get('yourIndex', 0)
        my_prize = opp_prize = None
        my_active = opp_active = None
        my_active_nrg = None
        my_active_hp = None
        bench = None
        bench_raw = []
        act_raw = None
        try:
            me = players[my_i]
            my_prize = len(me.get('prize') or [])
            opp_prize = len(players[1 - my_i].get('prize') or [])
            ma = me.get('active') or []
            oa = players[1 - my_i].get('active') or []
            my_active = ma[0].get('id') if ma and isinstance(ma[0], dict) else None
            opp_active = oa[0].get('id') if oa and isinstance(oa[0], dict) else None
            act_raw = ma[0] if ma and isinstance(ma[0], dict) else None
            if act_raw:
                my_active_nrg = len(act_raw.get('energyCards') or act_raw.get('energies') or [])
                my_active_hp = act_raw.get('hp')
            bench_raw = [b for b in (me.get('bench') or []) if isinstance(b, dict)]
            bench = [(b.get('id'), len(b.get('energyCards') or b.get('energies') or []),
                      b.get('hp')) for b in bench_raw]
        except Exception:
            pass
        # Attach 目标解析：chosen Attach 选项 → (inPlayArea==4 → active; 否则 bench[inPlayIndex])
        attach_targets = []
        for i in (act if isinstance(act, list) else [act]):
            if not (isinstance(i, int) and 0 <= i < len(opts)):
                continue
            o = opts[i]
            if not (isinstance(o, dict)
                    and norm(self.mod, o.get('type'), 'option') == 'Attach'):
                continue
            tid = None
            if o.get('inPlayArea') == 4:
                tid = my_active
            else:
                ipi = o.get('inPlayIndex', -1)
                if isinstance(ipi, int) and 0 <= ipi < len(bench_raw):
                    tid = bench_raw[ipi].get('id')
            attach_targets.append(tid if tid is not None else 'unknown')
        # [阻塞归因] 手牌能量数 + active贴能选项是否可用（区分"没能量可贴"与"优先级拦截"）
        nrg_in_hand = None
        attach_active_avail = False
        try:
            hand = players[my_i].get('hand') or []
            cdb = getattr(self.mod, '_CARD_DB', {})
            nrg_in_hand = sum(1 for c in hand
                              if isinstance(c, dict)
                              and cdb.get(c.get('id'), {}).get('is_energy'))
            attach_active_avail = any(
                isinstance(o, dict)
                and norm(self.mod, o.get('type'), 'option') == 'Attach'
                and o.get('inPlayArea') == 4 for o in opts)
        except Exception:
            pass
        rec = {
            'sel_type': norm(self.mod, sel.get('type'), 'select'),
            'context': norm(self.mod, sel.get('context'), 'context'),
            'maxCount': sel.get('maxCount'),
            'n_options': len(opts),
            'chosen_types': chosen_types,
            'turn': cur.get('turn'),
            'my_prize': my_prize, 'opp_prize': opp_prize,
            'my_active': my_active, 'opp_active': opp_active,
            'my_active_nrg': my_active_nrg, 'my_active_hp': my_active_hp,
            'bench': bench, 'attach_targets': attach_targets,
            'attack_avail': 'Attack' in opt_types,
            'chose_attack': 'Attack' in chosen_types,
            'nrg_in_hand': nrg_in_hand,
            'attach_active_avail': attach_active_avail,
        }
        self.decisions.append(rec)
        if self.tier0_left > 0:
            self.tier0_left -= 1
            d = dict(rec)
            d['raw_select'] = sel
            self.tier0_dump.append(d)
        return act

    def reset(self):
        self.decisions = []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--n', type=int, default=2000)
    ap.add_argument('--seed0', type=int, default=9000)
    args = ap.parse_args()

    mod = load_module(PROJ / 'main.py')
    agent_fn = mod.agent
    deck_a = agent_fn({'select': None})
    assert len(deck_a) == 60
    opp = builtin_agent('first')

    rec = RecAgent(agent_fn, mod)
    games = []
    stuck_dump = []  # 决策级阻塞样本：active=678 & nrg<2 & attach可用 → 实际选了什么
    t0 = time.time()
    tier0_written = False
    for g in range(args.n):
        swap = (g % 2 == 1)
        fns = (rec, opp) if not swap else (opp, rec)
        dks = (deck_a, SAMPLE_DECK) if not swap else (SAMPLE_DECK, deck_a)
        random.seed(args.seed0 + g)
        rec.reset()
        r = play(fns, dks)
        w = r['winner']
        a_won = (w == 0 and not swap) or (w == 1 and swap) if w in (0, 1) else None
        games.append({
            'game': g, 'we_second': swap, 'a_won': a_won, 'steps': r['steps'],
            'fault': r.get('fault'), 'decisions': list(rec.decisions),
        })
        if len(stuck_dump) < 2000:
            for d in rec.decisions:
                if (d['my_active'] == 678 and d['my_active_nrg'] is not None
                        and d['my_active_nrg'] < 2 and d.get('attach_active_avail')):
                    stuck_dump.append({'game': g, 'a_won': a_won,
                                       'turn': d['turn'], 'nrg': d['my_active_nrg'],
                                       'hp': d['my_active_hp'],
                                       'nrg_in_hand': d.get('nrg_in_hand'),
                                       'chosen': d['chosen_types'],
                                       'attach_targets': d.get('attach_targets'),
                                       'n_options': d['n_options']})
        if not tier0_written and rec.tier0_left == 0:
            (RUNS / 'vsfirst_tier0_dump.json').write_text(
                json.dumps(rec.tier0_dump, ensure_ascii=False, indent=1, default=str),
                encoding='utf-8')
            tier0_written = True
        if (g + 1) % 400 == 0:
            print(f'  {g+1}/{args.n} 局 ({time.time()-t0:.0f}s)', flush=True)

    # ---------- 聚合 ----------
    decided = [g for g in games if g['a_won'] is not None]
    wins = [g for g in decided if g['a_won']]
    losses = [g for g in decided if not g['a_won']]
    draws = len(games) - len(decided)
    wr = len(wins) / max(1, len(games))

    # 分侧胜率（we_second=False → 我方先手）
    def side_wr(second):
        gs = [g for g in decided if g['we_second'] == second]
        return {'n': len(gs), 'wr': round(sum(1 for g in gs if g['a_won']) / max(1, len(gs)), 4)}
    side = {'we_first': side_wr(False), 'we_second': side_wr(True)}

    # 败局局长分桶
    buckets = {'<=15': 0, '16-30': 0, '31-50': 0, '51-80': 0, '>80': 0}
    win_steps = [g['steps'] for g in wins]
    loss_steps = [g['steps'] for g in losses]
    for g in losses:
        s = g['steps']
        for lo, hi, k in ((0, 15, '<=15'), (16, 30, '16-30'), (31, 50, '31-50'),
                          (51, 80, '51-80'), (81, 10**9, '>80')):
            if lo <= s <= hi:
                buckets[k] += 1
                break

    # 决策类型频次：胜局 vs 败局（按每局平均，消除局长差异）
    def freq(gs, key):
        c = Counter()
        for g in gs:
            for d in g['decisions']:
                c[str(d[key])] += 1
        total_dec = sum(c.values()) or 1
        return {k: {'per_game': round(v / max(1, len(gs)), 3),
                    'share': round(v / total_dec, 4)}
                for k, v in c.most_common(15)}
    freq_cmp = {
        'wins': {'n_games': len(wins), 'by_sel_type': freq(wins, 'sel_type'),
                 'by_context': freq(wins, 'context')},
        'losses': {'n_games': len(losses), 'by_sel_type': freq(losses, 'sel_type'),
                   'by_context': freq(losses, 'context')},
    }

    # 所选 option 类型分布（胜/败）
    def chosen_freq(gs):
        c = Counter()
        for g in gs:
            for d in g['decisions']:
                for t in d['chosen_types']:
                    c[str(t)] += 1
        return dict(c.most_common(12))
    chosen = {'wins': chosen_freq(wins), 'losses': chosen_freq(losses)}

    # 攻击让度 + 奖品竞速轨迹
    def race_stats(gs):
        out = []
        for g in gs:
            mains = [d for d in g['decisions'] if d['sel_type'] == 'Main']
            avail = sum(1 for d in mains if d['attack_avail'])
            passed = sum(1 for d in mains if d['attack_avail'] and not d['chose_attack'])
            # 奖品差轨迹（我方剩余 - 对手剩余；负=落后）
            diffs = [(d['my_prize'] - d['opp_prize'])
                     for d in mains if d['my_prize'] is not None]
            first_behind = next((d['turn'] for d in mains
                                 if d['my_prize'] is not None
                                 and d['my_prize'] > d['opp_prize']), None)
            first_ahead = next((d['turn'] for d in mains
                                if d['my_prize'] is not None
                                and d['my_prize'] < d['opp_prize']), None)
            opening = next((d['my_active'] for d in g['decisions']
                            if d['my_active'] is not None), None)
            opp_opening = next((d['opp_active'] for d in g['decisions']
                                if d['opp_active'] is not None), None)
            toactive_turns = [d['turn'] for d in g['decisions']
                              if d['context'] == 'ToActive' and d['turn'] is not None]
            # ---- mega 决斗轨迹（F2 切片）----
            mega_first = next((d for d in g['decisions'] if d['my_active'] == 678), None)
            mega_deaths = []
            prev_active = None
            prev_active_hp = None
            for d in g['decisions']:
                if prev_active == 678 and d['my_active'] != 678:
                    bl = d['bench'] or []
                    ready = sum(1 for cid, e, h in bl if e >= 2)
                    evolved = sum(1 for cid, e, h in bl if cid in (674, 678))
                    mega_deaths.append({
                        'turn': d['turn'],
                        'mega_hp': prev_active_hp,
                        'prize_diff': (d['my_prize'] - d['opp_prize'])
                        if d['my_prize'] is not None else None,
                        'bench_n': len(bl), 'bench_ready_nrg2': ready,
                        'bench_evolved': evolved, 'bench': bl,
                    })
                prev_active = d['my_active']
                prev_active_hp = d['my_active_hp']
            bench677_turn = next((d['turn'] for d in g['decisions']
                                  if any(cid == 677 for cid, _, _ in (d['bench'] or []))
                                  or d['my_active'] == 677), None)
            # [阻塞归因] active=678 且能量<2 的决策点：是没能量可贴还是被优先级拦截
            stuck = [d for d in g['decisions']
                     if d['my_active'] == 678 and d['my_active_nrg'] is not None
                     and d['my_active_nrg'] < 2]
            stuck_n = len(stuck)
            stuck_no_nrg = sum(1 for d in stuck if d.get('nrg_in_hand') == 0)
            stuck_avail = sum(1 for d in stuck if d.get('attach_active_avail'))
            stuck_chose_attach = sum(1 for d in stuck if d.get('attach_targets'))
            mega_peak_nrg = max((d['my_active_nrg'] for d in g['decisions']
                                 if d['my_active'] == 678
                                 and d['my_active_nrg'] is not None), default=None)
            # ---- 能量去向聚合（F2a 验证）----
            at = [t for d in g['decisions'] for t in (d.get('attach_targets') or [])]
            attach_total = len(at)
            attach_to_678 = sum(1 for t in at if t == 678)
            attach_to_mega = sum(1 for t in at if t in (677, 678))
            attach_to_noncore = sum(1 for t in at
                                    if t not in (677, 678) and t != 'unknown')
            out.append({
                'main_n': len(mains),
                'atk_avail': avail, 'atk_pass': passed,
                'atk_pass_rate': round(passed / avail, 4) if avail else None,
                'final_prize_diff': diffs[-1] if diffs else None,
                'first_behind_turn': first_behind,
                'first_ahead_turn': first_ahead,
                'opening_active': opening, 'opp_opening_active': opp_opening,
                'toactive_turns': toactive_turns,
                'first_ko_taken_turn': toactive_turns[0] if toactive_turns else None,
                'kos_taken': len(toactive_turns),
                'mega_first_turn': mega_first['turn'] if mega_first else None,
                'mega_first_nrg': mega_first['my_active_nrg'] if mega_first else None,
                'mega_first_hp': mega_first['my_active_hp'] if mega_first else None,
                'mega_first_bench': mega_first['bench'] if mega_first else None,
                'mega_first_prize_diff': (mega_first['my_prize'] - mega_first['opp_prize'])
                if mega_first and mega_first['my_prize'] is not None else None,
                'mega_deaths': mega_deaths,
                'mega_death_n': len(mega_deaths),
                'bench677_turn': bench677_turn,
                'mega_peak_nrg': mega_peak_nrg,
                'stuck_n': stuck_n, 'stuck_no_nrg': stuck_no_nrg,
                'stuck_avail': stuck_avail, 'stuck_chose_attach': stuck_chose_attach,
                'attach_total': attach_total,
                'attach_to_678': attach_to_678,
                'attach_to_mega_line': attach_to_mega,
                'attach_to_noncore': attach_to_noncore,
            })
        return out
    wrace = race_stats(wins)
    lrace = race_stats(losses)

    # 首奖归属 → 胜率切片（先拿第一个奖品 vs 先丢第一个奖品）
    all_race = ([(g, r) for g, r in zip(wins, wrace)]
                + [(g, r) for g, r in zip(losses, lrace)])
    fp = {'we_take_first': [0, 0], 'they_take_first': [0, 0], 'same_or_none': [0, 0]}
    for g, r in all_race:
        a, b = r['first_ahead_turn'], r['first_behind_turn']
        if a is not None and (b is None or a < b):
            k = 'we_take_first'
        elif b is not None and (a is None or b < a):
            k = 'they_take_first'
        else:
            k = 'same_or_none'
        fp[k][0] += 1
        fp[k][1] += 1 if g['a_won'] else 0
    first_prize = {k: {'n': v[0], 'wr': round(v[1] / v[0], 4) if v[0] else None}
                   for k, v in fp.items()}
    # 落盘后逆转率：先丢首奖但最终赢
    comebacks = sum(1 for g, r in all_race
                    if g['a_won'] and r['first_behind_turn'] is not None
                    and (r['first_ahead_turn'] is None
                         or r['first_behind_turn'] < r['first_ahead_turn']))
    first_prize['comeback_wins_after_losing_first_prize'] = comebacks

    # 每局明细落盘（后续切片不重跑）
    with open(RUNS / 'vsfirst_race.jsonl', 'w', encoding='utf-8') as f:
        for g, r in all_race:
            f.write(json.dumps({'game': g['game'], 'we_second': g['we_second'],
                                'a_won': g['a_won'], 'steps': g['steps'], **r},
                               ensure_ascii=False) + '\n')

    def agg_race(rs):
        n = max(1, len(rs))
        apr = [r['atk_pass_rate'] for r in rs if r['atk_pass_rate'] is not None]
        fpd = [r['final_prize_diff'] for r in rs if r['final_prize_diff'] is not None]
        fbt = [r['first_behind_turn'] for r in rs if r['first_behind_turn'] is not None]
        return {
            'atk_pass_rate_mean': round(statistics.mean(apr), 4) if apr else None,
            'final_prize_diff_mean': round(statistics.mean(fpd), 3) if fpd else None,
            'first_behind_turn_mean': round(statistics.mean(fbt), 1) if fbt else None,
            'never_behind_share': round(sum(1 for r in rs
                                            if r['first_behind_turn'] is None) / n, 4),
        }

    report = {
        'n': args.n, 'seed0': args.seed0,
        'wr': round(wr, 4), 'wins': len(wins), 'losses': len(losses), 'draws': draws,
        'invalid_ours': sum(1 for g in games if g['fault'] is not None and
                            ((g['fault'] == 0) != g['we_second'])),
        'side': side,
        'steps': {
            'wins_mean': round(statistics.mean(win_steps), 1) if win_steps else None,
            'losses_mean': round(statistics.mean(loss_steps), 1) if loss_steps else None,
            'loss_buckets': buckets,
        },
        'freq_cmp': freq_cmp,
        'chosen_option_types': chosen,
        'race': {'wins': agg_race(wrace), 'losses': agg_race(lrace)},
        'first_prize': first_prize,
        'elapsed_s': round(time.time() - t0, 1),
    }
    out = RUNS / 'vsfirst_diagnose.json'
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')
    (RUNS / 'vsfirst_stuck_dump.jsonl').write_text(
        '\n'.join(json.dumps(x, ensure_ascii=False) for x in stuck_dump), encoding='utf-8')

    print(f"\n=== vs_first 诊断 n={args.n} seed0={args.seed0} ===")
    print(f"WR {wr:.4f} ({len(wins)}W {len(losses)}L {draws}D) "
          f"invalid_ours={report['invalid_ours']}")
    print(f"分侧: 先手 {side['we_first']}  后手 {side['we_second']}")
    print(f"局长: 胜局均值 {report['steps']['wins_mean']} / 败局均值 {report['steps']['losses_mean']}")
    print(f"败局分桶: {buckets}")
    print(f"→ {out}")


if __name__ == '__main__':
    main()
