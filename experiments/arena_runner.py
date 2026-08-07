# -*- coding: utf-8 -*-
"""arena_runner.py — Hermes Lab Loop L2：本地直驱官方引擎评测（Mac arm64 原生）

被测对象 = 完整提交形态（main.py + model_student.npz hybrid rerank），
隔离运行于 experiments/runs/<id>/（复制 main.py + npz，模拟提交包结构）。

对手池（冻结于 experiments/arena_pool/，sha256 校验）：
  v23_2_rules  纯规则 champion 镜像（无 npz）
  v22_5_rules  回归哨兵（git 2f829d7 快照）
  first        弱点对局（无脑选前 N 项 + 样例牌组，实测 v23.2 仅 ~33% 胜率）
  random       sanity（必须 ≥99% 胜率，否则判定 agent 损坏）

用法:
  # 正式晋级评测（默认 2000 局 ≈ CI ±2.2%，约 20 秒本地）
  python3 arena_runner.py --id exp001 --npz model_student.npz --n 2000 --gate

  # Phase0 快速验证（不接门禁）
  python3 arena_runner.py --id smoke --npz model_student.npz --n 200 --gate

输出 experiments/arena_report-<id>.json（字段与 reward_calc.py 兼容）。
"""
import argparse
import importlib.util
import json
import math
import os
import random
import shutil
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PROJ = Path('/Users/seyonmacbook/Desktop/Pokemon_TCG_AI_Battle_Challenge')
COMP = PROJ / 'inference' / 'comp_data' / 'sample_submission' / 'sample_submission'
EXP = PROJ / 'experiments'
POOL = EXP / 'arena_pool'
RUNS = EXP / 'runs'

# 官方引擎 cg 包（Darwin 自动选 libcg.dylib）
sys.path.insert(0, str(COMP))
from cg.game import battle_start, battle_select, battle_finish  # noqa: E402
from cg.sim import Battle  # noqa: E402

OBS_KEYS = ('select', 'logs', 'current', 'search_begin_input')
SAMPLE_DECK = [int(x) for x in (COMP / 'deck.csv').read_text().split('\n')[:60]]


# ---------- 引擎对局 ----------
def play(agent_fns, decks, max_steps=3000):
    """打一局。winner: 0/1（选手视角），-1=平/异常。fault: 非法动作方。"""
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
            except Exception as e:
                return {'winner': 1 - p, 'steps': steps, 'fault': p,
                        'err': repr(e)[:200]}
            steps += 1
        return {'winner': -1, 'steps': steps, 'err': 'max_steps exceeded'}
    finally:
        battle_finish()


# ---------- agent 加载 ----------
def load_module(path: Path):
    """独立加载一个 agent 模块（各自全局状态隔离）。"""
    spec = importlib.util.spec_from_file_location(f'ag_{path.stem}_{id(path)}', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def builtin_agent(kind: str):
    """first / random：无脑选前 N 项 / 随机选。deck 用官方样例牌组。"""
    def fn(obs, config=None):
        if obs.get('select') is None:
            return SAMPLE_DECK
        sel = obs['select']
        n = sel['maxCount']
        if kind == 'first':
            return list(range(n))
        return random.sample(list(range(len(sel['option']))), n)
    return fn


def load_opponent(name: str):
    """冻结对手。file → arena_pool/<name>.py；builtin → first/random。

    [bugfix] 对手池冻结校验（sha256 与 registry 比对）此前只在文档中声明，
    从未真正执行——任何人改 arena_pool/*.py 都会静默通过。现与 opponents.json
    中的记录比对，不一致即抛错拒绝评测（防 reward hacking）。
    """
    if name in ('first', 'random'):
        return builtin_agent(name)
    p = POOL / f'{name}.py'
    if not p.exists():
        raise FileNotFoundError(f'对手 {name} 缺失: {p}（需 snapshot_opponents.py 生成）')
    try:
        # registry 在 experiments/ 下，path 字段形如 'arena_pool/v23_2_rules.py'
        # （相对 experiments/ 目录），按相对路径匹配键名无关。
        reg = json.loads((POOL.parent / 'opponents.json').read_text(encoding='utf-8'))
        rel = str(p.relative_to(POOL.parent))
        expected = next(
            (spec.get('sha256') for spec in reg.get('opponents', {}).values()
             if spec.get('type') == 'file' and spec.get('path') == rel),
            None)
    except Exception:
        expected = None
    if expected:
        try:
            from experiments.arena_pool_registry import sha256 as _sha256
        except ImportError:
            # 直接以脚本运行 (python3 experiments/arena_runner.py) 时 experiments 包不可用
            import hashlib as _hashlib

            def _sha256(path):
                h = _hashlib.sha256()
                with open(path, 'rb') as _f:
                    for _chunk in iter(lambda: _f.read(1 << 20), b''):
                        h.update(_chunk)
                return h.hexdigest()[:16]
        actual = _sha256(p)
        if actual != expected:
            raise SystemExit(
                f'FROZEN-POOL VIOLATION: 对手 {name} sha256 与 registry 不一致'
                f'（{actual} != {expected}）。arena 环境不得修改；'
                f'确属有意更新则先运行 arena_pool_registry.py 刷新注册表。')
    return load_module(p).agent


# ---------- 评测 ----------
def wilson_ci_lo(p_hat: float, n: int, z: float = 1.96) -> float:
    if n <= 0:
        return 0.0
    denom = 1 + z * z / n
    center = (p_hat + z * z / (2 * n)) / denom
    margin = z * math.sqrt((p_hat * (1 - p_hat) + z * z / (4 * n)) / n) / denom
    return max(0.0, center - margin)


def run_arena(agent_a, agent_b, decks_a, decks_b, n_games, seed0=1000):
    """A vs B 打 n_games 局，先后手轮换，固定种子。返回 A 视角统计。

    invalid 只统计被测方 A 自身的非法动作：对手 (B) fault 时 A 直接获胜，
    把对手的 fault 记进 A 的 invalid 会双重惩罚（既可能判负又扣 clean 门禁）。
    """
    t0 = time.time()
    wins = losses = draws = invalid = 0
    turns = []
    faults = []
    for g in range(n_games):
        swap = (g % 2 == 1)
        fns = (agent_a, agent_b) if not swap else (agent_b, agent_a)
        dks = (decks_a, decks_b) if not swap else (decks_b, decks_a)
        if seed0:
            random.seed(seed0 + g)
        r = play(fns, dks)
        turns.append(r['steps'])
        fault = r.get('fault')
        if fault is not None:
            # fault 的玩家下标是当前局的 fns 视角（swap 时 A 在下标 1）
            a_is_faulty = (fault == 0 and not swap) or (fault == 1 and swap)
            if a_is_faulty:
                invalid += 1
                faults.append({'game': g, 'player': fault, 'err': r.get('err')})
        w = r['winner']
        if w == -1:
            draws += 1
        else:
            a_won = (w == 0 and not swap) or (w == 1 and swap)
            if a_won:
                wins += 1
            else:
                losses += 1
    dt = time.time() - t0
    return {
        'wins': wins, 'losses': losses, 'draws': draws,
        'invalid': invalid, 'avg_turns': round(statistics.mean(turns), 1),
        'elapsed_s': round(dt, 2), 'faults': faults[:5],
    }


def main():
    ap = argparse.ArgumentParser(description='Hermes Lab L2: 本地直驱引擎 arena')
    ap.add_argument('--id', required=True, help='实验 id（写 arena_report-<id>.json）')
    ap.add_argument('--npz', default='', help='model_student.npz 路径（hybrid 用）')
    ap.add_argument('--n', type=int, default=2000)
    ap.add_argument('--opponents', default='v23_2_rules,v22_5_rules,first,random')
    ap.add_argument('--gate', action='store_true', help='跑完直接接晋级门禁')
    ap.add_argument('--canary', type=float, default=0.0, help='门禁用 canary_top1')
    ap.add_argument('--fixed', type=float, default=0.0, help='门禁用 fixed_top1')
    args = ap.parse_args()

    # ---- 隔离运行目录：复制被测 main.py + npz（模拟提交包） ----
    run_dir = RUNS / args.id
    if run_dir.exists():
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True)
    main_src = PROJ / 'main.py'
    shutil.copy(main_src, run_dir / 'main.py')
    for dc in (PROJ / 'deck.csv', COMP / 'deck.csv'):
        if dc.exists():
            shutil.copy(dc, run_dir / 'deck.csv')
            break
    npz_src = Path(args.npz) if args.npz else None
    if npz_src and npz_src.exists():
        shutil.copy(npz_src, run_dir / 'model_student.npz')
    sys.path.insert(0, str(run_dir))
    agent_mod = load_module(run_dir / 'main.py')
    agent_fn = agent_mod.agent
    deck_a = agent_fn({'select': None}, None)
    assert len(deck_a) == 60, f'被测 deck 异常: {len(deck_a)}'

    print(f"=== arena[{args.id}] n={args.n} npz={npz_src.name if npz_src else '纯规则'} "
          f"opponents={args.opponents} ===", flush=True)

    total = {'w': 0, 'l': 0, 'd': 0, 'invalid': 0, 'games': 0, 'turns': 0}
    per_opp = []
    t_all = time.time()
    for name in [o.strip() for o in args.opponents.split(',') if o.strip()]:
        opp = load_opponent(name)
        try:
            opp_deck = opp({'select': None})
        except TypeError:
            opp_deck = opp({'select': None}, None)
        except Exception:
            opp_deck = SAMPLE_DECK
        if len(opp_deck) != 60:
            print(f'  WARN: 对手 {name} deck={len(opp_deck)}，用样例 deck', flush=True)
            opp_deck = SAMPLE_DECK
        r = run_arena(agent_fn, opp, deck_a, opp_deck, args.n)
        total['w'] += r['wins']; total['l'] += r['losses']
        total['d'] += r['draws']; total['invalid'] += r['invalid']
        total['games'] += args.n
        total['turns'] += r['avg_turns'] * args.n
        per_opp.append({
            'opponent': name,
            'w': r['wins'], 'l': r['losses'], 'd': r['draws'],
            'invalid': r['invalid'],
            'wr': round(r['wins'] / args.n, 4),
        })
        print(f"  vs {name:<14} {r['wins']:>4}W {r['losses']:>4}L {r['draws']:>2}D "
              f"wr={r['wins']/args.n:.3f} ({r['elapsed_s']}s)", flush=True)

    n = total['games']
    wr = total['w'] / n if n else 0.0
    report = {
        'ts': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'experiment': args.id,
        'npz': npz_src.name if npz_src else None,
        'engine': 'official sample_submission/cg libcg.dylib (arm64)',
        'games_total': n,
        'wins': total['w'], 'losses': total['l'], 'draws': total['d'],
        'invalid_actions': total['invalid'],
        'win_rate': round(wr, 4),
        'ci95_lo': round(wilson_ci_lo(wr, n), 4),
        'avg_turns': round(total['turns'] / n, 1),
        'elapsed_s': round(time.time() - t_all, 1),
        'per_opponent': per_opp,
    }
    out = EXP / f'arena_report-{args.id}.json'
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print()
    print(f"=== 完成: {n} 局 {report['elapsed_s']}s | WR {wr:.3f} "
          f"CI95lo {report['ci95_lo']:.3f} invalid {total['invalid']} | → {out.name}")

    # ---- 门禁（可选）：调 reward_calc 晋级判定 ----
    if args.gate:
        sys.path.insert(0, str(EXP))
        from reward_calc import cmd_record
        print()
        print('--- 晋级门禁 ---')
        sys.argv = ['reward_calc', 'record', '--experiment', args.id,
                    '--arena', f'arena_report-{args.id}.json',
                    '--canary', str(args.canary), '--fixed', str(args.fixed),
                    '--smoke-pass', 'true',
                    '--invalid-actions', str(total['invalid']),
                    '--quota-used', '0.0']
        try:
            cmd_record(argparse.Namespace(
                experiment=args.id, arena=f'arena_report-{args.id}.json',
                canary=args.canary, fixed=args.fixed, smoke_pass=True,
                invalid_actions=total['invalid'], quota_used=0.0,
                quota_budget=0.0, lb_delta=0.0, submitted=False))
        except SystemExit as e:
            print(f'  gate exit={e.code}（0=晋级, 2=未晋级）')


if __name__ == '__main__':
    main()
