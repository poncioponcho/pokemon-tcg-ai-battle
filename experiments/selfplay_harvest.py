#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""selfplay_harvest.py — 主线B: 现役规则 agent + FINAL 牌组自对弈回放采集
=========================================================================
产出与 leaderboard_replay/raw 完全同构的 episode JSON, extract.py 零改动直接消费。

设计:
- 每 worker 独立加载 main.py 两次 (mod_a/mod_b, 全局态隔离), 双方都是现役规则 agent
- 对局混合: gid%10<7 → mirror (FINAL vs FINAL); 否则 FINAL vs SAMPLE_DECK
  (覆盖最苦手的 vs first/SAMPLE  matchup 状态分布, 政策侧仍在分布内)
- 种子 seed0+g (对齐 run_arena 配对语义); 只收 winner∈{0,1} 且无 fault 的局
- replay 结构: info.TeamNames=[selfplay-p0, selfplay-p1], steps=[[rec0,rec1]...],
  step0=双方牌组动作(60 int), 每个决策步仅行动方有 observation(select+current)
- 文件: inference/selfplay_replay/raw/episode-sp<g>-replay.json (tmp+rename 原子写)
- 断点续跑: 已存在的 gid 跳过
- --manifest 模式: 扫描已采文件生成 inference/selfplay_replay/manifest.csv
  (episode_id, rank_at_capture=1.0, team_name=胜方; 供 extract 的 captured_team 过滤
  → 胜方视角 = "己方 agent 胜局")

用法:
  python3 experiments/selfplay_harvest.py --games 4000 --seed0 20000 --workers 8
  python3 experiments/selfplay_harvest.py --manifest
"""
import argparse
import json
import os
import random
import sys
import time
from multiprocessing import Pool
from pathlib import Path

os.environ['PTCG_NN_MODE'] = 'off'  # 必须先于 load_module (纯规则策略)

EXP = Path(__file__).resolve().parent
PROJ = EXP.parent
sys.path.insert(0, str(EXP))
import arena_runner as ar  # noqa: E402

OUT_DIR = PROJ / 'inference' / 'selfplay_replay' / 'raw'
MANIFEST_OUT = PROJ / 'inference' / 'selfplay_replay' / 'manifest.csv'
TEAM_NAMES = ['selfplay-p0', 'selfplay-p1']

_FINAL_DECK = None
_WORKER_STATE = {}


def _final_deck():
    global _FINAL_DECK
    if _FINAL_DECK is None:
        _FINAL_DECK = [int(l.strip()) for l in (PROJ / 'deck.csv').read_text().splitlines()
                       if l.strip()]
    return _FINAL_DECK


def _init_worker():
    """每个 spawn 子进程加载两份 main.py (全局态隔离)。"""
    mod_a = ar.load_module(PROJ / 'main.py')
    mod_b = ar.load_module(PROJ / 'main.py')
    _WORKER_STATE['fns'] = (mod_a.agent, mod_b.agent)


def _init_worker_dagger():
    """DAgger: nn_first 模块 + off 模块各一 (npz 用仓库根 model_student.npz)。"""
    os.environ['PTCG_NN_MODE'] = 'nn_first'
    m_nn = ar.load_module(PROJ / 'main.py')
    os.environ['PTCG_NN_MODE'] = 'off'
    m_off = ar.load_module(PROJ / 'main.py')
    _WORKER_STATE['fns_nn'] = m_nn
    _WORKER_STATE['fns_off'] = m_off


def _play_record_dagger(g, seed0):
    """[主线B DAgger 08-09] student(nn_first) 打一侧, 规则 oracle 重标该侧全部决策。

    p_student = g%2 交替; 每回合双方 agent 都调用 (保证各自 _GAME_STATE 全观测同步),
    student 侧落子用 student 动作, 记录的 label 用 oracle(规则) 动作。
    oracle 侧正常打正常记。replay 结构与 _play_record 一致。
    """
    m_nn, m_off = _WORKER_STATE['fns_nn'], _WORKER_STATE['fns_off']
    decks = (_final_deck(), _final_deck())
    if seed0:
        random.seed(seed0 + g)
    from cg.game import battle_start, battle_select, battle_finish
    from cg.sim import Battle
    _, sd = battle_start(decks[0], decks[1])
    if Battle.battle_ptr is None or sd.errorPlayer >= 0:
        try:
            battle_finish()
        except Exception:
            pass
        return None, 'start_failed'
    p_student = g % 2
    steps = [[{'observation': {}, 'action': list(decks[0])},
              {'observation': {}, 'action': list(decks[1])}]]
    n_decisions = 0
    winner = -1
    nsteps = 0
    try:
        while nsteps < 3000:
            obs = Battle.obs
            cur = obs.get('current') or {}
            res = cur.get('result', -1)
            if res is not None and res >= 0:
                winner = 0 if res == 0 else (1 if res == 1 else -1)
                break
            p = cur.get('yourIndex', 0)
            a_obs = {k: obs.get(k) for k in ar.OBS_KEYS}
            try:
                act_nn = m_nn.agent(a_obs)    # 双侧每回合都喂, 保持内部状态同步
                act_off = m_off.agent(a_obs)
                battle_select(act_nn if p == p_student else act_off)
            except Exception as e:
                return None, f'fault_p{p}:{repr(e)[:120]}'
            sel = a_obs.get('select')
            label_act = act_off  # DAgger: 标签恒为 oracle(规则) 动作, 不论哪侧
            rec = [{'observation': {}, 'action': []},
                   {'observation': {}, 'action': []}]
            if sel is not None:
                rec[p] = {'observation': {'select': sel, 'current': cur},
                          'action': label_act}
                n_decisions += 1
            else:
                rec[p] = {'observation': {'select': None, 'current': cur},
                          'action': label_act}
            steps.append(rec)
            nsteps += 1
    finally:
        battle_finish()
    if winner not in (0, 1):
        return None, 'draw' if winner == -1 else 'error'
    replay = {
        'info': {'TeamNames': TEAM_NAMES},
        'steps': steps,
        'rewards': [1 if winner == 0 else 0, 1 if winner == 1 else 0],
        'dagger_student_side': p_student,
    }
    return (replay, n_decisions, winner, True, nsteps), None


def _play_record(g, seed0):
    """打一局并记录为 replay dict; 平局/fault/异常返回 (None, 原因)。"""
    fns = _WORKER_STATE['fns']
    mirror = (g % 10) < 7
    decks = (_final_deck(), _final_deck() if mirror else list(ar.SAMPLE_DECK))
    if seed0:
        random.seed(seed0 + g)
    from cg.game import battle_start, battle_select, battle_finish
    from cg.sim import Battle
    _, sd = battle_start(decks[0], decks[1])
    if Battle.battle_ptr is None or sd.errorPlayer >= 0:
        try:
            battle_finish()
        except Exception:
            pass
        return None, 'start_failed'
    steps = [[{'observation': {}, 'action': list(decks[0])},
              {'observation': {}, 'action': list(decks[1])}]]
    n_decisions = 0
    winner = -1
    nsteps = 0
    try:
        while nsteps < 3000:
            obs = Battle.obs
            cur = obs.get('current') or {}
            res = cur.get('result', -1)
            if res is not None and res >= 0:
                winner = 0 if res == 0 else (1 if res == 1 else -1)
                break
            p = cur.get('yourIndex', 0)
            a_obs = {k: obs.get(k) for k in ar.OBS_KEYS}
            try:
                act = fns[p](a_obs)
                battle_select(act)
            except Exception as e:
                return None, f'fault_p{p}:{repr(e)[:120]}'
            sel = a_obs.get('select')
            rec = [{'observation': {}, 'action': []},
                   {'observation': {}, 'action': []}]
            if sel is not None:
                rec[p] = {'observation': {'select': sel, 'current': cur},
                          'action': act}
                n_decisions += 1
            else:
                rec[p] = {'observation': {'select': None, 'current': cur},
                          'action': act}
            steps.append(rec)
            nsteps += 1
    finally:
        battle_finish()
    if winner not in (0, 1):
        return None, 'draw' if winner == -1 else 'error'
    replay = {
        'info': {'TeamNames': TEAM_NAMES},
        'steps': steps,
        'rewards': [1 if winner == 0 else 0, 1 if winner == 1 else 0],
    }
    return (replay, n_decisions, winner, mirror, nsteps), None


def _do_game(task):
    g, seed0, dagger = task
    out = OUT_DIR / f'episode-sp{g}-replay.json'
    if out.exists():
        return g, 'skip', 0
    res, err = (_play_record_dagger(g, seed0) if dagger
                else _play_record(g, seed0))
    if res is None:
        return g, f'drop:{err}', 0
    replay, n_decisions, winner, mirror, nsteps = res
    tmp = out.with_suffix('.tmp')
    with tmp.open('w') as f:
        json.dump(replay, f, default=str)
    tmp.rename(out)
    tag = 'd' if dagger else ('m' if mirror else 's')
    return g, f'ok:w{winner}:{tag}:t{nsteps}', n_decisions


def cmd_harvest(args):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    games = list(range(args.gid0, args.gid0 + args.games))
    t0 = time.time()
    done = drop = skip = decisions = 0
    tasks = [(g, args.seed0, args.dagger) for g in games]
    init = _init_worker_dagger if args.dagger else _init_worker
    with Pool(args.workers, initializer=init) as pool:
        for g, status, nd in pool.imap_unordered(_do_game, tasks, chunksize=1):
            if status == 'skip':
                skip += 1
            elif status.startswith('ok'):
                done += 1
                decisions += nd
            else:
                drop += 1
            tot = done + drop + skip
            if tot % 100 == 0:
                dt = time.time() - t0
                rate = done / max(dt, 1e-9) * 60
                print(f'[{time.strftime("%H:%M:%S")}] {tot}/{len(games)} '
                      f'ok={done} drop={drop} skip={skip} decisions={decisions} '
                      f'({rate:.0f} g/min)', flush=True)
    dt = time.time() - t0
    print(f'[done] ok={done} drop={drop} skip={skip} decisions={decisions} '
          f'in {dt/60:.1f}min -> {OUT_DIR}', flush=True)


def cmd_manifest():
    """扫描 raw 目录, 生成 manifest.csv (episode_id,rank_at_capture,team_name,winner)。"""
    import csv
    files = sorted(OUT_DIR.glob('episode-sp*-replay.json'))
    rows = []
    for f in files:
        ep = f.stem.replace('-replay', '').replace('episode-', '')
        try:
            with f.open() as h:
                d = json.load(h)
            rewards = d.get('rewards') or [0, 0]
            winner = 0 if rewards[0] == 1 else (1 if rewards[1] == 1 else -1)
            if winner not in (0, 1):
                continue
            # [DAgger] student 侧视角全程保留 (coverage 是目的, 不按胜负过滤):
            # team_name 记 student 侧 → is_captured_team=1 落在 student 决策上
            side = d.get('dagger_student_side')
            team = TEAM_NAMES[side] if side in (0, 1) else TEAM_NAMES[winner]
            rows.append({'episode_id': ep,
                         'rank_at_capture': '1.0',
                         'team_name': team,
                         'winner': winner})
        except Exception as e:
            print(f'[warn] {f.name}: {e}', flush=True)
    MANIFEST_OUT.parent.mkdir(parents=True, exist_ok=True)
    with MANIFEST_OUT.open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['episode_id', 'rank_at_capture',
                                          'team_name', 'winner'])
        w.writeheader()
        w.writerows(rows)
    print(f'[manifest] {len(rows)} episodes -> {MANIFEST_OUT}', flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--games', type=int, default=4000)
    ap.add_argument('--gid0', type=int, default=0,
                    help='episode gid 起点 (DAgger 批次用 100000+ 避免撞自对弈 gid)')
    ap.add_argument('--seed0', type=int, default=20000)
    ap.add_argument('--workers', type=int, default=8)
    ap.add_argument('--dagger', action='store_true',
                    help='DAgger 模式: student(nn_first) 打一侧, 规则 oracle 重标')
    ap.add_argument('--manifest', action='store_true')
    args = ap.parse_args()
    if args.manifest:
        cmd_manifest()
    else:
        cmd_harvest(args)


if __name__ == '__main__':
    main()
