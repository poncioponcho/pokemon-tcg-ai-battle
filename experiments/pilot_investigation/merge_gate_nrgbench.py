"""merge_gate_nrgbench.py — nrg_bench 候选三配置同批闸 (全 9 腿加权协议)

候选: submission_baseline/main.py FLAG_NRG_BENCH
  setup期 active 非当回合攻击关键 (plan.attacker != 0) → 能量评分 -200 (转 bench)。
  证据: top_pilot diff pre-first-KO 赢局喂 active 我们 28.2% vs Sixth/ミワ 6-11%。

三配置 (精确隔离 nrg 效应, dying_674 已 NO-GO 排除):
  pristine : runs/_configA 快照 (config A 提交件)
  OFF      : FLAG_DYING_674=False, FLAG_NRG_BENCH=False (验证 flag 机械 parity)
  ON       : FLAG_DYING_674=False, FLAG_NRG_BENCH=True  (候选)
9 腿 × n=2000, 引擎不可播种 → 同一 pool batch 内交错测量, 无配对二项抽样 (#111)。

判决 (advisor 2026-08-12 18:49):
  parity    : |OFF − pristine| 每腿 & 加权 < 2.2pp
  regression: 任一腿 ON−pristine < −2.2pp 即不过 (全局改动可能帮加权砸单腿)
  提交判据  : 全 9 腿加权 ON−pristine > +2.2pp 且以上全过且 invalid ON==0 → 才谈提交
  保真度危机: 本地闸过 ≠ live 赢 (#132); 真仲裁 = 交后 live WR 重测

用法: /opt/homebrew/bin/python3 experiments/merge_gate_nrgbench.py [--n 2000] [--workers 3]
产物: experiments/runs/merge_gate_nrgbench.json
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

OUT = PROJ / 'experiments/runs/merge_gate_nrgbench.json'
PRISTINE = PROJ / 'experiments/runs/_configA/main_configA_pristine.py'
MERGED = PROJ / 'submission_baseline/main.py'

LEGS = [('Alakazam', 0.227), ('other', 0.197), ('Grimmsnarl', 0.178),
        ('Archaludon', 0.144), ('Lucario', 0.120), ('Crustle', 0.071),
        ('Dragapult', 0.053), ('Cornerstone', 0.011), ('Gardevoir', 0.001)]
_W = sum(w for _, w in LEGS)
LEGS = [(a, w / _W) for a, w in LEGS]
NOISE = 0.022          # ledger #111

G = {}


def _load_meta():
    meta = {}
    for a, _ in LEGS:
        csv = list((PROJ / 'experiments/arena_pool/meta').glob(f'{a}__*.csv'))[0]
        meta[a] = [int(l) for l in csv.read_text().splitlines() if l.strip()]
    return meta


def _load_merged(dying: bool, nrg: bool):
    m = ar.load_module(MERGED)
    m.FLAG_DYING_674 = dying
    m.FLAG_NRG_BENCH = nrg
    return m


def _init_worker():
    G['mods'] = {
        'pristine': ar.load_module(PRISTINE),
        'OFF': _load_merged(False, False),
        'ON': _load_merged(False, True),
    }
    G['first'] = ar.builtin_agent('first')
    G['meta'] = _load_meta()
    G['deck'] = dsh._baseline_deck()   # baseline 自家牌组 (config A 牌面)


def _eval(task):
    cfg, leg, n = task
    r = ar.run_arena(G['mods'][cfg].agent, G['first'], G['deck'], G['meta'][leg],
                     n, seed0=9000)
    return cfg, leg, r['wins'], r['invalid'], n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--n', type=int, default=2000)
    ap.add_argument('--workers', type=int, default=3)
    args = ap.parse_args()

    # 防御: 提交捆绑 deck.csv 必须仍等于 baseline 自家牌组
    live = [int(l) for l in (PROJ / 'submission_baseline/deck.csv').read_text().splitlines() if l.strip()]
    assert sorted(live) == sorted(dsh._baseline_deck()), 'submission_baseline/deck.csv 漂移!'
    # 防御: 盘上 main.py 的 flag 默认值不影响闸 (worker 显式覆写), 但候选提交态必须是 ON
    import ast as _ast
    _src = MERGED.read_text()
    assert 'FLAG_NRG_BENCH' in _src and 'score -= 200' in _src, 'nrg_bench 编辑未落盘!'

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

    parity_ok = all(abs(wr['OFF'][l] - wr['pristine'][l]) < NOISE for l, _ in LEGS) \
        and abs(wsum['OFF'] - wsum['pristine']) < NOISE
    reg_ok = all(wr['ON'][l] - wr['pristine'][l] > -NOISE for l, _ in LEGS)
    delta_on = wsum['ON'] - wsum['pristine']
    go = parity_ok and reg_ok and delta_on > NOISE and inv['ON'] == 0

    checks = {'parity': parity_ok, 'regression': reg_ok,
              'on_delta_pp': round(delta_on * 100, 2), 'invalid_on': inv['ON']}
    verdict = ('GO: nrg_bench > config A +2.2pp, 贴 advisor 定交不交' if go
               else 'NO-GO: ' + ('增益 <2.2pp 噪声地板' if parity_ok and reg_ok
                                  else '闸腿未过, 见 checks'))
    print(f'\nchecks: {checks}\nVERDICT: {verdict}')

    OUT.write_text(json.dumps({'ts': time.time(), 'n_per_leg': args.n, 'wr': wr,
                               'weighted': wsum, 'invalid': inv,
                               'checks': checks, 'verdict': verdict,
                               'elapsed_s': round(time.time() - t0, 1)},
                              ensure_ascii=False, indent=1))
    print(f'→ {OUT}')


if __name__ == '__main__':
    main()
