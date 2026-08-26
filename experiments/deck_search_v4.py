# -*- coding: utf-8 -*-
"""deck_search_v4.py — 全训练家面 + 1235 牌组爬山 (08-10, v24.8 主体)。

与 deck_search_v3 的差异:
1. 评测 agent 换成现役 main.py (v24.8, sha 491d137db9fe) 而非 arena_pool
   v23_2_rules — v23_2 不认识 1235, 用它搜 1235 仍是死卡、搜索无效
   (peer 2026-08-10 08:48 约束)。
2. CANDIDATES 补齐全训练家面: v3 集合 + 1235(エネルギー加速, v24.8 已移植)
   + 1229/1123/1141/1182/1159。1158 排除 (ACE SPEC, 效果未实证);
   1252 スタジアム 不纳入 (机制独立, 从未入牌组)。
3. LOG/CKPT 独立命名空间 deck_search_v4*.jsonl。

机制(筛选→独立种子确认→vs_first 主目标/mirror≥0.49 约束→断点续跑含 n 键)
完全继承 v3。搜完后走 3 种子标准闸 (seed 9000/9001/9002, mirror≥0.7465
或 vs_first≥0.4564 且 mirror≥0.7095, 硬闸=卡池快败+ci_lo>0.5+invalid=0),
过闸且用户显式确认 (08:00 免确认窗口已过) 才提交。

用法：nice -n 10 python3 experiments/deck_search_v4.py [--rounds 3] [--screen-n 1000] [--confirm-n 4000] [--workers 3]
"""
# [可复现加固] PYTHONHASHSEED 须在解释器启动前固定, 进程内赋值无效 → re-exec 守卫
import os as _os
import sys as _sys
if _os.environ.get('PYTHONHASHSEED') != '0':
    _os.environ['PYTHONHASHSEED'] = '0'
    _os.execv(_sys.executable, [_sys.executable] + _sys.argv)

import argparse
import hashlib
import json
import multiprocessing as mp
import sys
import time
from collections import Counter
from pathlib import Path

EXP = Path('/Users/seyonmacbook/Desktop/Pokemon_TCG_AI_Battle_Challenge/experiments')
sys.path.insert(0, str(EXP))
import arena_runner as ar  # noqa: E402

PROJ = ar.PROJ
RUNS = EXP / 'runs'
RUNS.mkdir(exist_ok=True)
LOG = RUNS / 'deck_search_v4.jsonl'
CKPT = RUNS / 'deck_search_v4_ckpt.jsonl'

OUR_DECK = [int(l.strip()) for l in (PROJ / 'deck.csv').read_text().splitlines() if l.strip()]
SAMPLE = ar.SAMPLE_DECK

# [v4] 全训练家面 + bench 宝可梦 + 1235; 排除 1158(未实证)/1252(スタジアム)
CANDIDATES = sorted({674, 675, 676,
                     1097, 1102, 1121, 1123, 1141, 1142, 1145, 1152, 1159,
                     1182, 1205, 1213, 1227, 1229, 1235})

# 卡 DB（判定能量卡，来自现役 main.py 内嵌库）
sys.path.insert(0, str(PROJ))
_champ = ar.load_module(PROJ / 'main.py')
_CARD_DB = _champ._CARD_DB
_TRAINER_IDS = _champ._TRAINER_IDS


def _load_rules_agent():
    """[v4] 现役 main.py 的 agent (v23_2_rules 不认识 1235, 不可用)。"""
    return ar.load_module(PROJ / 'main.py').agent


def is_energy(cid):
    return bool(_CARD_DB.get(cid, {}).get('is_energy'))


def legal_swaps(base):
    """枚举合法单卡置换 (remove_a, add_b)。"""
    cnt = Counter(base)
    out = []
    for a in sorted(cnt):
        if cnt[a] <= 0:
            continue
        for b in CANDIDATES:
            if b == a:
                continue
            if not is_energy(b) and cnt.get(b, 0) >= 4:
                continue
            out.append((a, b))
    return out


def apply_swap(base, a, b):
    d = list(base)
    d.remove(a)
    d.append(b)
    assert len(d) == 60
    return d


def emit(ev):
    with open(LOG, 'a', encoding='utf-8') as f:
        f.write(json.dumps(ev, ensure_ascii=False) + '\n')
    print(ev.get('msg', ''), flush=True)


def mirror_wr(rules, var, base, n, seed0):
    r = ar.run_arena(rules, rules, var, base, n, seed0=seed0)
    tot = r['wins'] + r['losses'] + r['draws']
    wr = r['wins'] / tot if tot else 0.0
    return wr, ar.wilson_ci_lo(wr, tot), r


# ---- 并行 worker：每个进程独立加载一次现役 rules agent，置换间完全独立 ----
_W = {}


def _init_worker():
    _W['rules'] = _load_rules_agent()


def _eval_swap(task):
    a, b, base, n, seed0, do_vf = task
    try:
        var = apply_swap(base, a, b)
        rules = _W['rules']
        r = ar.run_arena(rules, rules, var, base, n, seed0=seed0)
        tot = r['wins'] + r['losses'] + r['draws']
        wr = r['wins'] / tot if tot else 0.0
        vf = None
        if do_vf:
            # [联合适应度] 仅 confirm 任务付 vs_first 腿代价 (screen 保持只跑 mirror)
            first = _W.setdefault('first', ar.builtin_agent('first'))
            rf = ar.run_arena(rules, first, var, ar.SAMPLE_DECK,
                              max(1000, n // 2), seed0=seed0 + 777)
            nf = rf['wins'] + rf['losses'] + rf['draws']
            vf = rf['wins'] / nf if nf else 0.0
        return (wr, ar.wilson_ci_lo(wr, tot), vf, a, b, None)
    except Exception as e:  # 单个置换失败不拖垮整个池：按 wr=0 沉底处理
        return (0.0, 0.0, None, a, b, repr(e))


# ---- 断点续跑：按 (phase, round, base指纹, n, a, b) 记录已完成结果，崩溃重启自动跳过 ----
# 键必须含 n — 不同 n 的评测是不同数据,
# 不含 n 会让小 n 烟测/旧跑的结果污染大 n 真跑 (08-09 已发作两次)
def _ckpt_key(phase, rd, base_key, n, a, b):
    return f'{phase}|{rd}|{base_key}|{n}|{a}|{b}'


def _base_key(base):
    return hashlib.sha1(json.dumps(sorted(base)).encode()).hexdigest()[:12]


def ckpt_load():
    done = {}
    if CKPT.exists():
        for ln in CKPT.read_text(encoding='utf-8').splitlines():
            try:
                ev = json.loads(ln)
                # 旧格式(无 n 字段)一律视为脏数据跳过, 不复用
                if 'n' not in ev:
                    continue
                done[_ckpt_key(ev['phase'], ev['round'], ev['base'],
                               ev['n'], ev['a'], ev['b'])] = \
                    (ev['wr'], ev['lo'], ev.get('vf'))
            except Exception:
                pass
    return done


def ckpt_add(phase, rd, base_key, n, a, b, wr, lo, vf=None):
    with open(CKPT, 'a', encoding='utf-8') as f:
        f.write(json.dumps({'phase': phase, 'round': rd, 'base': base_key, 'n': n,
                            'a': a, 'b': b, 'wr': wr, 'lo': lo, 'vf': vf}) + '\n')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--rounds', type=int, default=3)
    ap.add_argument('--screen-n', type=int, default=1000)
    ap.add_argument('--confirm-n', type=int, default=8000)
    ap.add_argument('--topk', type=int, default=10)
    ap.add_argument('--workers', type=int, default=8)
    args = ap.parse_args()

    rules = _load_rules_agent()
    first = ar.builtin_agent('first')
    base = list(OUR_DECK)

    emit({'ev': 'start', 'ts': time.time(),
          'msg': f'=== deck_search_v4 start: rounds={args.rounds} screen_n={args.screen_n} '
                 f'confirm_n={args.confirm_n} candidates={len(CANDIDATES)} '
                 f'agent=main.py(v24.8) ==='})

    # 基线参考：base vs first(SAMPLE) — 同时作为 vs_first 主目标的当前值
    r0 = ar.run_arena(rules, first, base, SAMPLE, 2000)
    n0 = r0['wins'] + r0['losses'] + r0['draws']
    cur_vf = r0['wins'] / n0 if n0 else 0.0
    emit({'ev': 'baseline_vs_first', 'wr': cur_vf,
          'msg': f'[baseline] rules(OUR) vs first(SAMPLE) n={n0} wr={cur_vf:.4f}'})

    for rd in range(1, args.rounds + 1):
        swaps = legal_swaps(base)
        emit({'ev': 'round_start', 'round': rd, 'n_swaps': len(swaps),
              'msg': f'--- round {rd}: {len(swaps)} 个合法置换，筛选 n={args.screen_n} ---'})

        base_key = _base_key(base)
        done = ckpt_load()
        scored = []
        tasks = []
        for (a, b) in swaps:
            k = _ckpt_key('screenJ', rd, base_key, args.screen_n, a, b)
            if k in done:
                scored.append((done[k][0], done[k][1], a, b))
            else:
                tasks.append((a, b, list(base), args.screen_n, 1000, False))
        t0 = time.time()
        if scored:
            print(f'  resume: 已完成 {len(scored)}/{len(swaps)}，跳过', flush=True)
        with mp.Pool(args.workers, initializer=_init_worker) as pool:
            for res in pool.imap_unordered(_eval_swap, tasks):
                wr, lo, _vf, a2, b2, err = res
                if err:
                    emit({'ev': 'screen_error', 'round': rd, 'rm': a2, 'add': b2,
                          'error': err,
                          'msg': f'  [warn] screen -{a2}+{b2} 异常: {err}，按 wr=0 处理'})
                scored.append((wr, lo, a2, b2))
                ckpt_add('screenJ', rd, base_key, args.screen_n, a2, b2, wr, lo)
                if len(scored) % 50 == 0:
                    print(f'  screen {len(scored)}/{len(swaps)} ({(time.time()-t0)/60:.1f}min)', flush=True)

        scored.sort(reverse=True)
        top = scored[:args.topk]
        emit({'ev': 'screen_done', 'round': rd,
              'top5': [{'rm': a, 'add': b, 'wr': round(w, 4)} for w, lo, a, b in top[:5]],
              'msg': f'[round {rd}] 筛选 top5: ' +
                     ', '.join(f'-{a}+{b} wr={w:.3f}' for w, lo, a, b in top[:5])})

        # 独立种子确认 + vs_first 腿（并行执行；支持断点续跑）
        done = ckpt_load()
        ctasks = []
        cmap = {}
        for w0, lo0, a, b in top:
            k = _ckpt_key('confirmJ', rd, base_key, args.confirm_n, a, b)
            if k in done:
                cmap[(a, b)] = done[k]
            else:
                ctasks.append((a, b, list(base), args.confirm_n, 5000, True))
        with mp.Pool(args.workers, initializer=_init_worker) as pool:
            for res in pool.imap_unordered(_eval_swap, ctasks):
                wr, lo, vf, a2, b2, err = res
                if err:
                    emit({'ev': 'confirm_error', 'round': rd, 'rm': a2, 'add': b2,
                          'error': err,
                          'msg': f'  [warn] confirm -{a2}+{b2} 异常: {err}，按 wr=0 处理'})
                cmap[(a2, b2)] = (wr, lo, vf)
                ckpt_add('confirmJ', rd, base_key, args.confirm_n, a2, b2, wr, lo, vf)
        # [联合接受准则] 主目标 vs_first 最大; 硬约束 mirror 不显著劣于 base (wr>=0.49)
        best = None
        for w0, lo0, a, b in top:
            wr, lo, vf = cmap[(a, b)]
            emit({'ev': 'confirm', 'round': rd, 'rm': a, 'add': b,
                  'screen_wr': round(w0, 4), 'confirm_wr': round(wr, 4),
                  'ci_lo': round(lo, 4), 'vs_first_wr': round(vf, 4) if vf is not None else None,
                  'msg': f'  confirm -{a}+{b}: screen={w0:.3f} confirm={wr:.4f} '
                         f'ci_lo={lo:.4f} vs_first={vf:.4f}'})
            if wr >= 0.49 and vf is not None and (best is None or vf > best[0]):
                best = (vf, wr, lo, a, b)

        if best is None:
            emit({'ev': 'stop', 'round': rd,
                  'msg': f'[round {rd}] 无满足约束（mirror wr≥0.49 且有 vs_first）的候选，停止'})
            break
        vf, wr, lo, a, b = best
        if vf <= cur_vf + 0.005:
            emit({'ev': 'stop', 'round': rd,
                  'msg': f'[round {rd}] 最优候选 vs_first={vf:.4f} 未超当前 {cur_vf:.4f}'
                         f'(+0.005 阈值)，vs_first 爬山到头，停止'})
            break

        base = apply_swap(base, a, b)
        cur_vf = vf
        emit({'ev': 'accept', 'round': rd, 'rm': a, 'add': b,
              'confirm_wr': round(wr, 4), 'ci_lo': round(lo, 4),
              'vs_first_wr': round(vf, 4), 'deck': sorted(base),
              'msg': f'[round {rd}] ✓ 接受 -{a}+{b} (vs_first={vf:.4f} ↑; '
                     f'mirror wr={wr:.4f} ci_lo={lo:.4f} 约束内)'})

    # 终验：最终牌组 vs 原 OUR_DECK
    if sorted(base) != sorted(OUR_DECK):
        wr, lo, r = mirror_wr(rules, base, OUR_DECK, args.confirm_n, seed0=9000)
        rf = ar.run_arena(rules, first, base, SAMPLE, args.confirm_n)
        nf = rf['wins'] + rf['losses'] + rf['draws']
        emit({'ev': 'final', 'deck': sorted(base),
              'vs_orig_mirror_wr': round(wr, 4), 'vs_orig_ci_lo': round(lo, 4),
              'vs_first_wr': round(rf['wins'] / nf, 4),
              'msg': f'=== FINAL: vs 原牌组 mirror wr={wr:.4f} (ci_lo={lo:.4f}), '
                     f'vs first wr={rf["wins"]/nf:.4f} ==='})
    else:
        emit({'ev': 'final', 'deck': sorted(base), 'msg': '=== FINAL: 牌组未变 ==='})

    print(f'最终牌组: {sorted(base)}', flush=True)


if __name__ == '__main__':
    main()
