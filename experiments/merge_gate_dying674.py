"""merge_gate_dying674.py — dying_674 移植三配置同批闸 (pre-audit §3 协议)

三配置: pristine (runs/_configA 快照) / FLAG-OFF / FLAG-ON (submission_baseline/main.py)
9 腿 × n=2000, 引擎不可播种 → 同一 pool batch 内交错测量, 全程无配对二项抽样 (#111)。

判决 (merge_pre_audit.md §3):
  parity   : |OFF − pristine| 每腿 & 加权 < 2.2pp
  function : Crustle/Alakazam ON ≥ pristine (噪声内), 计数器 ON blocked>0 & attacks=0, OFF attacks>0
  regression: 其余 7 腿 ON−pristine 无 < −2.2pp
  提交判据  : ON 加权 > pristine 加权 + 2.2pp 且以上全过 → GO (否则 NO-GO=正常结局)

用法: /opt/homebrew/bin/python3 experiments/merge_gate_dying674.py [--n 2000] [--workers 3]
产物: experiments/runs/merge_gate_dying674.json
"""
import argparse
import json
import multiprocessing as mp
import sys
import time
from pathlib import Path

PROJ = Path('/Users/seyonmacbook/Desktop/Pokemon_TCG_AI_Battle_Challenge')
sys.path.insert(0, str(PROJ / 'experiments'))
import arena_runner as ar  # noqa: E402
import deck_search_hybrid as dsh  # noqa: E402  (复用 _baseline_deck)

OUT = PROJ / 'experiments/runs/merge_gate_dying674.json'
PRISTINE = PROJ / 'experiments/runs/_configA/main_configA_pristine.py'
MERGED = PROJ / 'submission_baseline/main.py'

LEGS = [('Alakazam', 0.227), ('other', 0.197), ('Grimmsnarl', 0.178),
        ('Archaludon', 0.144), ('Lucario', 0.120), ('Crustle', 0.071),
        ('Dragapult', 0.053), ('Cornerstone', 0.011), ('Gardevoir', 0.001)]
_W = sum(w for _, w in LEGS)
LEGS = [(a, w / _W) for a, w in LEGS]
NOISE = 0.022          # ledger #111
FUNC_LEGS = {'Crustle', 'Alakazam'}

G = {}


def _load_meta():
    meta = {}
    for a, _ in LEGS:
        csv = list((PROJ / 'experiments/arena_pool/meta').glob(f'{a}__*.csv'))[0]
        meta[a] = [int(l) for l in csv.read_text().splitlines() if l.strip()]
    return meta


def _init_worker():
    G['mods'] = {
        'pristine': ar.load_module(PRISTINE),
        'OFF': ar.load_module(MERGED),
        'ON': ar.load_module(MERGED),
    }
    G['mods']['OFF'].FLAG_DYING_674 = False
    assert G['mods']['ON'].FLAG_DYING_674 is True
    G['first'] = ar.builtin_agent('first')
    G['meta'] = _load_meta()
    G['deck'] = dsh._baseline_deck()   # baseline 自家牌组 (config A 牌面)


def _eval(task):
    cfg, leg, n = task
    r = ar.run_arena(G['mods'][cfg].agent, G['first'], G['deck'], G['meta'][leg],
                     n, seed0=9000)
    return cfg, leg, r['wins'], r['invalid'], n


def _counter_leg(n=300):
    """单进程计数器腿: dying 674 非KO攻击 ON 应恒 0 / OFF 应 >0。"""
    first = ar.builtin_agent('first')
    meta = _load_meta()
    deck = dsh._baseline_deck()
    out = {}
    for cfg, flag in (('OFF', False), ('ON', True)):
        m = ar.load_module(MERGED)
        m.FLAG_DYING_674 = flag
        for leg in ('Crustle', 'Cornerstone'):
            m._DYING674.update({'situations': 0, 'blocked': 0, 'attacks': 0})
            r = ar.run_arena(m.agent, first, deck, meta[leg], n, seed0=9000)
            out[f'{cfg}_{leg}'] = {**m._DYING674, 'wr': round(r['wins'] / n, 4)}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--n', type=int, default=2000)
    ap.add_argument('--workers', type=int, default=3)
    args = ap.parse_args()

    # 防御: 提交捆绑 deck.csv 必须仍等于 baseline 自家牌组 (pre-audit: deck 不动)
    live = [int(l) for l in (PROJ / 'submission_baseline/deck.csv').read_text().splitlines() if l.strip()]
    assert sorted(live) == sorted(dsh._baseline_deck()), 'submission_baseline/deck.csv 漂移!'

    t0 = time.time()
    tasks = [(cfg, leg, args.n) for cfg in ('pristine', 'OFF', 'ON') for leg, _ in LEGS]
    with mp.Pool(args.workers, initializer=_init_worker) as pool:
        res = pool.map(_eval, tasks)

    wr = {c: {} for c in ('pristine', 'OFF', 'ON')}
    inv = {c: 0 for c in wr}
    for cfg, leg, w, i, n in res:
        wr[cfg][leg] = w / n
        inv[cfg] += i
    wsum = {c: sum(w * wr[c][leg] for leg, w in LEGS) for c in wr}

    print(f'{"leg":<13}{"w":>6}{"pristine":>9}{"OFF":>8}{"ON":>8}{"OFF-Δpp":>9}{"ON-Δpp":>9}')
    for leg, w in LEGS:
        p, o, n_ = wr['pristine'][leg], wr['OFF'][leg], wr['ON'][leg]
        print(f'{leg:<13}{w:>6.3f}{p:>9.4f}{o:>8.4f}{n_:>8.4f}'
              f'{(o-p)*100:>+9.2f}{(n_-p)*100:>+9.2f}')
    print(f'weighted      {wsum["pristine"]:.4f} {wsum["OFF"]:.4f} {wsum["ON"]:.4f} '
          f'OFFΔ{(wsum["OFF"]-wsum["pristine"])*100:+.2f}pp ONΔ{(wsum["ON"]-wsum["pristine"])*100:+.2f}pp')
    print(f'invalid: {inv}  ({time.time()-t0:.0f}s)')

    print('--- 计数器腿 (单进程 n=300) ---')
    counters = _counter_leg()
    for k, v in counters.items():
        print(f'  {k}: {v}')

    parity_ok = all(abs(wr['OFF'][l] - wr['pristine'][l]) < NOISE for l, _ in LEGS) \
        and abs(wsum['OFF'] - wsum['pristine']) < NOISE
    func_ok = all(wr['ON'][l] >= wr['pristine'][l] - NOISE for l in FUNC_LEGS) \
        and counters['ON_Crustle']['attacks'] == 0 and counters['ON_Crustle']['blocked'] > 0
    reg_ok = all(wr['ON'][l] - wr['pristine'][l] > -NOISE
                 for l, _ in LEGS if l not in FUNC_LEGS)
    delta_on = wsum['ON'] - wsum['pristine']
    go = parity_ok and func_ok and reg_ok and delta_on > NOISE and inv['ON'] == 0

    checks = {'parity': parity_ok, 'function': func_ok, 'regression': reg_ok,
              'on_delta_pp': round(delta_on * 100, 2), 'invalid_on': inv['ON']}
    verdict = ('GO: merge > config A +2.2pp, 可谈提交 (仍需净环境冒烟+用户点头)' if go
               else 'NO-GO: ' + ('增益 <2.2pp 噪声地板' if parity_ok and func_ok and reg_ok
                                  else '闸腿未过, 见 checks'))
    print(f'\nchecks: {checks}\nVERDICT: {verdict}')

    OUT.write_text(json.dumps({'ts': time.time(), 'n_per_leg': args.n, 'wr': wr,
                               'weighted': wsum, 'invalid': inv, 'counters': counters,
                               'checks': checks, 'verdict': verdict,
                               'elapsed_s': round(time.time() - t0, 1)},
                              ensure_ascii=False, indent=1))
    print(f'→ {OUT}')


if __name__ == '__main__':
    main()
