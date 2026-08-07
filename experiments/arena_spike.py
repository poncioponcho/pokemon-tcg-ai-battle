# -*- coding: utf-8 -*-
"""Arena Spike: 本地直接 ctypes 驱动官方 cg 引擎（不依赖 kaggle_environments）。

用法: python3 arena_spike.py [--games N]
目的: 实测 Mac arm64 (libcg.dylib) 单局耗时，裁决「400 局 ≤ 30 分钟」可行性。
"""
import argparse
import json
import random
import statistics
import sys
import time
from pathlib import Path

PROJ = Path('/Users/seyonmacbook/Desktop/Pokemon_TCG_AI_Battle_Challenge')
COMP = PROJ / 'inference' / 'comp_data' / 'sample_submission' / 'sample_submission'
sys.path.insert(0, str(COMP))   # cg 包（Darwin 自动加载 libcg.dylib）
sys.path.insert(0, str(PROJ))   # main.py (v23.2)

from cg.game import battle_start, battle_select, battle_finish  # noqa: E402
from cg.sim import Battle  # noqa: E402

import main as v23  # noqa: E402


def read_sample_deck():
    csv = (COMP / 'deck.csv').read_text().split('\n')
    return [int(csv[i]) for i in range(60)]


def random_agent(obs):
    sel = obs.get('select')
    return random.sample(list(range(len(sel['option']))), sel['maxCount'])


OBS_KEYS = ('select', 'logs', 'current', 'search_begin_input')


def play(agent_fns, decks, max_steps=3000):
    """打一局。返回 {'winner': 0/1/-1(draw), 'steps': n, 'fault': p?, 'err': str?}"""
    _, sd = battle_start(decks[0], decks[1])
    if Battle.battle_ptr is None or sd.errorPlayer >= 0:
        try:
            battle_finish()
        except Exception:
            pass
        return {'winner': -1, 'steps': 0, 'err': f'start failed errorPlayer={sd.errorPlayer}'}
    steps = 0
    try:
        while steps < max_steps:
            obs = Battle.obs
            cur = obs.get('current') or {}
            res = cur.get('result', -1)
            if res is not None and res >= 0:
                return {'winner': 0 if res == 0 else (1 if res == 1 else -1),
                        'steps': steps}
            p = cur.get('yourIndex', 0)
            a_obs = {k: obs.get(k) for k in OBS_KEYS}
            try:
                act = agent_fns[p](a_obs)
                battle_select(act)
            except Exception as e:  # 非法动作/异常 → 该方判负
                return {'winner': 1 - p, 'steps': steps, 'fault': p,
                        'err': repr(e)[:200]}
            steps += 1
        return {'winner': -1, 'steps': steps, 'err': 'max_steps exceeded'}
    finally:
        battle_finish()


def run_match(name, fn_a, fn_b, deck_a, deck_b, n_games):
    times, steps, wins = [], [], [0, 0, 0]  # wins: [a, b, draw]
    faults = []
    for g in range(n_games):
        # 先后手轮换
        if g % 2 == 0:
            fns, dks = (fn_a, fn_b), (deck_a, deck_b)
            swap = False
        else:
            fns, dks = (fn_b, fn_a), (deck_b, deck_a)
            swap = True
        t0 = time.time()
        r = play(fns, dks)
        dt = time.time() - t0
        times.append(dt)
        steps.append(r['steps'])
        if 'fault' in r:
            faults.append({'game': g, **r})
        w = r['winner']
        if w == -1:
            wins[2] += 1
        else:
            # 映射回 a/b 视角
            a_won = (w == 0 and not swap) or (w == 1 and swap)
            wins[0 if a_won else 1] += 1
    return {
        'match': name, 'games': n_games,
        'wins_a': wins[0], 'wins_b': wins[1], 'draws': wins[2],
        'sec_per_game_avg': round(statistics.mean(times), 3),
        'sec_per_game_p50': round(statistics.median(times), 3),
        'sec_per_game_max': round(max(times), 3),
        'steps_avg': round(statistics.mean(steps), 1),
        'steps_max': max(steps),
        'faults': faults,
        'est_400_games_min': round(statistics.mean(times) * 400 / 60, 1),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--games', type=int, default=20, help='每场对阵的局数（默认20）')
    args = ap.parse_args()

    deck_v23 = v23.agent({'select': None}, None)
    assert len(deck_v23) == 60, f'v23.2 deck 长度异常: {len(deck_v23)}'
    deck_rand = read_sample_deck()

    print(f'[spike] v23.2 deck ok (60 cards) | engine: {COMP}/cg', flush=True)
    t_all = time.time()

    r1 = run_match('v23.2 vs v23.2', v23.agent, v23.agent,
                   deck_v23, deck_v23, args.games)
    print(json.dumps({k: v for k, v in r1.items() if k != 'faults'},
                     ensure_ascii=False), flush=True)

    r2 = run_match('v23.2 vs random', v23.agent, random_agent,
                   deck_v23, deck_rand, args.games)
    print(json.dumps({k: v for k, v in r2.items() if k != 'faults'},
                     ensure_ascii=False), flush=True)

    total = time.time() - t_all
    report = {
        'engine': 'official sample_submission/cg libcg.dylib (arm64)',
        'host': 'local mac arm64',
        'matches': [r1, r2],
        'total_seconds': round(total, 1),
        'verdict_400_games_le_30min': bool(
            max(r1['est_400_games_min'], r2['est_400_games_min']) <= 30),
    }
    out = PROJ / 'experiments' / 'arena_spike_report.json'
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n',
                   encoding='utf-8')
    print(f'[spike] total {total:.1f}s | verdict 400局<=30min: '
          f'{report["verdict_400_games_le_30min"]} | report -> {out}')
    for r in (r1, r2):
        for f in r['faults'][:3]:
            print(f"[fault] {r['match']} g{f['game']}: {f.get('err')}")


if __name__ == '__main__':
    main()
