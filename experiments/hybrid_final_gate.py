"""hybrid_final_gate.py — hybrid 牌组第3发闸: candidate vs config A 大n同批A/B

判读纪律 (ledger #111 / hybrid_search_noise_discipline):
  - 搜索内部 accept 链是噪声爬升, 只归档不解读; 本闸是唯一有效判决。
  - 引擎不可播种 → 无配对二项抽样, n=3000/腿时 Δσ≈1.2pp; |Δ|<2.2pp 不写字。
  - 过闸(全满足才谈第3发打包):
      Crustle ≥ 0.823 (config A 量级不破)
      Cornerstone ≥ 0.99 (悬崖不复发)
      加权 > 0.928 且 Δ加权 > +2.2pp (真·policy外增益, 非噪声)
  - 任一不满足 → keep config A (459cf97), 不动 last-2。这是数学预期的默认结局。

用法: /opt/homebrew/bin/python3 experiments/hybrid_final_gate.py [--n 3000] [--workers 3]
产物: experiments/runs/hybrid_final_gate.json
"""
import argparse
import json
import math
import multiprocessing as mp
import sys
import time
from pathlib import Path

PROJ = Path('/Users/seyonmacbook/Desktop/Pokemon_TCG_AI_Battle_Challenge')
sys.path.insert(0, str(PROJ / 'experiments'))
import deck_search_hybrid as dsh  # noqa: E402  (复用 LEGS/_baseline_deck/legal/ar)

GATE_JSON = PROJ / 'experiments/runs/hybrid_final_gate.json'
SEARCH_JSONL = PROJ / 'experiments/runs/deck_search_hybrid.jsonl'

# 锁定阈值 (勿改, 改动需新 ledger 条目)
T_CRUSTLE = 0.823
T_CORNERSTONE = 0.99
T_WEIGHTED = 0.928
T_DELTA = 0.022          # ledger #111 噪声地板

G = {}


def _init_worker():
    G['base'] = dsh.ar.load_module(PROJ / 'inference/ext/baseline1084_main.py')
    G['first'] = dsh.ar.builtin_agent('first')
    G['meta'] = {}
    for a, _ in dsh.LEGS:
        csv = list((PROJ / 'experiments/arena_pool/meta').glob(f'{a}__*.csv'))[0]
        G['meta'][a] = [int(l) for l in csv.read_text().splitlines() if l.strip()]


def _eval_leg(task):
    tag, deck, leg, n = task
    r = dsh.ar.run_arena(G['base'].agent, G['first'], deck, G['meta'][leg], n, seed0=9000)
    return tag, leg, r['wins'], r['invalid'], n


def load_candidate():
    """最后一条 final 事件的 deck; 搜索还在跑(final 缺失)则中止。"""
    final, last_accept = None, None
    for line in SEARCH_JSONL.read_text().splitlines():
        ev = json.loads(line)
        if ev.get('ev') == 'final':
            final = ev['deck']
        elif ev.get('ev') == 'accept':
            last_accept = ev['deck']
    if final is None:
        sys.exit('ABORT: 搜索尚未出 final 事件 (还在跑或异常终止), 不判读。')
    return final, last_accept


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--n', type=int, default=3000)
    ap.add_argument('--workers', type=int, default=3)
    args = ap.parse_args()

    cand, last_accept = load_candidate()
    cfgA = dsh._baseline_deck()
    assert dsh.legal(cand), f'FINAL 牌组不合法: {sorted(cand)}'

    if sorted(cand) == sorted(cfgA):
        print('VERDICT: FINAL == config A (搜索收敛回起点)。keep config A, 无第3发。')
        GATE_JSON.write_text(json.dumps({'verdict': 'identical_to_config_A',
                                         'deck': sorted(cand)}, ensure_ascii=False, indent=1))
        return

    t0 = time.time()
    tasks = [(tag, deck, leg, args.n)
             for tag, deck in (('cand', cand), ('cfgA', cfgA)) for leg, _ in dsh.LEGS]
    with mp.Pool(args.workers, initializer=_init_worker) as pool:
        res = pool.map(_eval_leg, tasks)

    wr = {tag: {} for tag in ('cand', 'cfgA')}
    inv = {tag: 0 for tag in ('cand', 'cfgA')}
    for tag, leg, w, i, n in res:
        wr[tag][leg] = w / n
        inv[tag] += i
    wsum = {tag: sum(w * wr[tag][leg] for leg, w in dsh.LEGS) for tag in ('cand', 'cfgA')}
    dw = wsum['cand'] - wsum['cfgA']

    print(f'{"leg":<13}{"w":>6}{"cfgA":>8}{"cand":>8}{"Δpp":>8}')
    for leg, w in dsh.LEGS:
        d = (wr['cand'][leg] - wr['cfgA'][leg]) * 100
        print(f'{leg:<13}{w:>6.3f}{wr["cfgA"][leg]:>8.4f}{wr["cand"][leg]:>8.4f}{d:>+8.2f}')
    print(f'weighted      {wsum["cfgA"]:.4f}  {wsum["cand"]:.4f}  Δ{dw*100:+.2f}pp  '
          f'(n={args.n}/腿, Δσ≈{100*math.sqrt(0.25*2/args.n):.2f}pp)')
    print(f'invalid: cand={inv["cand"]} cfgA={inv["cfgA"]}   elapsed={time.time()-t0:.0f}s')

    checks = {
        'crustle_ok': wr['cand']['Crustle'] >= T_CRUSTLE,
        'cornerstone_ok': wr['cand']['Cornerstone'] >= T_CORNERSTONE,
        'weighted_ok': wsum['cand'] > T_WEIGHTED,
        'delta_real': dw > T_DELTA,
        'invalid_zero': inv['cand'] == 0,
    }
    go = all(checks.values())
    verdict = ('GO: 过闸, 可谈打包 (仍需净环境冒烟+用户点头)' if go else
               'NO-GO: keep config A (459cf97), last-2 不动')
    print(f'\nchecks: {checks}\nVERDICT: {verdict}')

    GATE_JSON.write_text(json.dumps({
        'ts': time.time(), 'n_per_leg': args.n, 'candidate': sorted(cand),
        'last_accept_in_search': sorted(last_accept) if last_accept else None,
        'wr': wr, 'weighted': wsum, 'delta_weighted': round(dw, 4),
        'invalid': inv, 'checks': checks, 'verdict': verdict,
        'thresholds': {'crustle': T_CRUSTLE, 'cornerstone': T_CORNERSTONE,
                       'weighted': T_WEIGHTED, 'delta': T_DELTA},
        'elapsed_s': round(time.time() - t0, 1),
    }, ensure_ascii=False, indent=1))
    print(f'→ {GATE_JSON}')


if __name__ == '__main__':
    main()
