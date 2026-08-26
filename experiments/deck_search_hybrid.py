"""deck_search_hybrid.py — hybrid 牌组搜索: baseline policy 驾驶 + meta 腿加权适应度

背景 (ledger: baseline_p1_quantified / cornerstone_cliff_diagnosed):
  deck_search 历史结论('674=负资产')是在弱规则下做出, 可能整批误判。
  本搜索用 baseline policy (h2h 87:13 实证最强规则) 重新评价牌组空间:
  起点 = baseline 自家牌组 (9腿加权 0.928), 目标 = 捏合我方牌组优势
  (Cornerstone 0.993 / Crustle 0.823 / 1235 能量韧性 vs 8锤封锁)。

测量纪律 (ledger: measurement_engine_unseedable_discipline):
  引擎不可播种 → 一切=无配对二项抽样; 现任每轮同批现测, 绝不引用历史值;
  screen 加权 σ≈2pp 只用于排序, 录取必须 confirm 加权 +0.8pp 才翻。

适应度: Σ w_leg × wr_leg, leg ∈ 8 条 meta 腿 (去掉 Gardevoir 0.1%),
  w = meta 占比归一化; 对手 = builtin first 驾驶 meta 牌组 (同 P1 口径)。

用法: nice -n 10 /opt/homebrew/bin/python3 experiments/deck_search_hybrid.py \
        [--rounds 6] [--screen-n 60] [--confirm-n 300] [--workers 3] [--limit-swaps 0]
产物: experiments/runs/deck_search_hybrid.jsonl (逐事件追加, 可断点续跑)
"""
import argparse
import ast
import json
import multiprocessing as mp
import sys
import time
from collections import Counter
from pathlib import Path

PROJ = Path('/Users/seyonmacbook/Desktop/Pokemon_TCG_AI_Battle_Challenge')
sys.path.insert(0, str(PROJ / 'experiments'))
import arena_runner as ar  # noqa: E402

OUT = PROJ / 'experiments/runs/deck_search_hybrid.jsonl'

# 候选加入面: 两副牌组并集 + 我方差异化件 + 1158(ACE SPEC 未知件, 与 1159 互斥由合法性守)
CANDIDATES = sorted({6, 673, 674, 675, 676, 677, 678,
                     1102, 1123, 1141, 1142, 1145, 1152, 1158, 1159,
                     1182, 1192, 1227, 1235, 1252})
ACE_SPEC = {10, 12, 13, 1080, 1082, 1085, 1088, 1089, 1092, 1093, 1095, 1096,
            1100, 1104, 1107, 1109, 1110, 1111, 1125, 1126, 1128, 1155, 1158,
            1159, 1165, 1167, 1169, 1247, 1249}
LEGS = [('Alakazam', 0.227), ('other', 0.197), ('Grimmsnarl', 0.178),
        ('Archaludon', 0.144), ('Lucario', 0.120), ('Crustle', 0.071),
        ('Dragapult', 0.053), ('Cornerstone', 0.011)]
_W = sum(w for _, w in LEGS)
LEGS = [(a, w / _W) for a, w in LEGS]

_ENERGY_IDS = None
_BASE = None          # worker 内 baseline 模块
_FIRST = None
_META = None


def _baseline_deck():
    src = ast.parse((PROJ / 'inference/ext/baseline1084_deck.py').read_text())
    deck = next(ast.literal_eval(n.value) for n in src.body
                if isinstance(n, ast.Assign) and any(getattr(t, 'id', '') == 'DECK' for t in n.targets))
    assert len(deck) == 60
    return deck


def _energy_ids():
    """官方卡数据: 名字含 Energy 即能量卡。"""
    global _ENERGY_IDS
    if _ENERGY_IDS is None:
        from cg.api import all_card_data
        _ENERGY_IDS = {c.cardId for c in all_card_data() if 'Energy' in str(getattr(c, 'name', ''))}
    return _ENERGY_IDS


def legal(deck):
    cnt = Counter(deck)
    if len(deck) != 60:
        return False
    e = _energy_ids()
    if any(n > 4 for c, n in cnt.items() if c not in e):
        return False
    if sum(1 for c in cnt if c in ACE_SPEC) > 1:
        return False
    return True


def gen_swaps(deck):
    out = []
    for a in sorted(set(deck)):
        for b in CANDIDATES:
            if a == b:
                continue
            var = [b if x == a else x for x in deck]
            # 只替换一张 (保持净变化 ±1 张卡)
            i = deck.index(a)
            var = deck[:i] + [b] + deck[i + 1:]
            if legal(var):
                out.append((a, b))
    return out


def _init_worker():
    global _BASE, _FIRST, _META
    _BASE = ar.load_module(PROJ / 'inference/ext/baseline1084_main.py')
    _FIRST = ar.builtin_agent('first')
    _META = {}
    for a, _ in LEGS:
        csv = list((PROJ / 'experiments/arena_pool/meta').glob(f'{a}__*.csv'))[0]
        _META[a] = [int(l) for l in csv.read_text().splitlines() if l.strip()]
    _energy_ids()


def fitness(deck, n):
    """worker 内: 8 腿加权胜率。返回 (fitness, {leg: wr})。"""
    tot, detail = 0.0, {}
    for a, w in LEGS:
        r = ar.run_arena(_BASE.agent, _FIRST, deck, _META[a], n, seed0=9000)
        wr = r['wins'] / n
        detail[a] = round(wr, 4)
        tot += w * wr
    return round(tot, 4), detail


def _eval(task):
    a, b, deck, n = task
    var = deck[:]
    i = var.index(a)
    var[i] = b
    f, d = fitness(var, n)
    return (a, b, f, d)


def emit(ev):
    with open(OUT, 'a') as f:
        f.write(json.dumps(ev, ensure_ascii=False) + '\n')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--rounds', type=int, default=6)
    ap.add_argument('--screen-n', type=int, default=60)
    ap.add_argument('--confirm-n', type=int, default=300)
    ap.add_argument('--workers', type=int, default=3)
    ap.add_argument('--limit-swaps', type=int, default=0, help='>0 时只评前 K 个置换 (冒烟用)')
    ap.add_argument('--accept-delta', type=float, default=0.008)
    args = ap.parse_args()

    base = _baseline_deck()
    emit({'ev': 'start', 'ts': time.time(), 'args': vars(args), 'base': base,
          'note': 'baseline policy 驾驶, 8 meta 腿加权, 起点=baseline 自家牌组'})

    with mp.Pool(args.workers, initializer=_init_worker) as pool:
        for rd in range(1, args.rounds + 1):
            t0 = time.time()
            # 现任同批现测 (绝不引用历史值); _eval 返回 (a,b,f,d), 取后两位
            bf, bdet = pool.map(_eval, [(base[0], base[0], base, args.screen_n)])[0][2:4]
            swaps = gen_swaps(base)
            if args.limit_swaps:
                swaps = swaps[:args.limit_swaps]
            tasks = [(a, b, base, args.screen_n) for a, b in swaps]
            scr = pool.map(_eval, tasks)
            scr.sort(key=lambda x: -x[2])
            for a, b, f, d in scr[:5]:
                emit({'ev': 'screen_top', 'rd': rd, 'swap': [-a, b], 'fit': f,
                      'base_fit': bf, 'legs': d})
            cands = [x for x in scr if x[2] > bf + 0.01][:15]
            emit({'ev': 'round_screened', 'rd': rd, 'base_fit': bf, 'base_legs': bdet,
                  'n_swaps': len(swaps), 'n_confirm': len(cands)})
            if not cands:
                emit({'ev': 'stop', 'rd': rd, 'reason': f'screen 无 >base+1pp 候选 (base_fit={bf})',
                      'final': base, 'elapsed_min': round((time.time() - t0) / 60, 1)})
                break
            # confirm: 候选与现任同批 n=confirm_n
            ctasks = [(a, b, base, args.confirm_n) for a, b, _, _ in cands]
            ctasks.append((base[0], base[0], base, args.confirm_n))
            res = pool.map(_eval, ctasks)
            bcf = res[-1][2]
            res = res[:-1]
            res.sort(key=lambda x: -x[2])
            best = res[0]
            emit({'ev': 'round_confirmed', 'rd': rd, 'base_fit_confirm': bcf,
                  'top': [{'swap': [-a, b], 'fit': f, 'legs': d} for a, b, f, d in res[:5]]})
            if best[2] > bcf + args.accept_delta:
                a, b, f, d = best
                i = base.index(a)
                base = base[:i] + [b] + base[i + 1:]
                emit({'ev': 'accept', 'rd': rd, 'swap': [-a, b], 'fit': f,
                      'delta': round(f - bcf, 4), 'deck': base,
                      'elapsed_min': round((time.time() - t0) / 60, 1)})
            else:
                emit({'ev': 'stop', 'rd': rd,
                      'reason': f'confirm 最优 {best[2]} 未超现任 {bcf} +{args.accept_delta}',
                      'final': base, 'elapsed_min': round((time.time() - t0) / 60, 1)})
                break
    emit({'ev': 'final', 'deck': base, 'ts': time.time()})
    print('FINAL deck:', sorted(base), flush=True)


if __name__ == '__main__':
    main()
