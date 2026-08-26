"""realpilot_gate.py — 真人级闸 (ledger #132 implication ③)

两侧均 pristine (config A) policy 驾驶, 只换牌组: 我方 baseline 自家牌组 vs meta 9 腿。
测「等 pilot 强度下的牌组对位差」——first-pilot 测试系统性高估 live (#132), 本闸把对手
pilot 拉到真人级, 看各腿是真均势还是牌组结构性劣势:
  wr ∈ 0.5±2.2pp → 均势 (#111 噪声地板; n=2000 单测 σ≈1.1pp)
  wr < 0.5−2.2pp → 我方牌组该腿结构性劣势 = first-pilot 测试藏住的缺口 (候选改进靶)
  wr > 0.5+2.2pp → 牌组优势

防漂移铁律 (#127): 牌组显式 dsh._baseline_deck() 且硬断言 == submission_baseline/deck.csv;
绝不用 mod.my_deck (DECK_PATH 相对 cwd 会静默捡根 v24.8)。

用法: /opt/homebrew/bin/python3 experiments/realpilot_gate.py [--n 2000] [--workers 3]
产物: experiments/runs/realpilot_gate.json
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

OUT = PROJ / 'experiments/runs/realpilot_gate.json'
PRISTINE = PROJ / 'experiments/runs/_configA/main_configA_pristine.py'

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


def _init_worker():
    G['mod'] = ar.load_module(PRISTINE)
    G['meta'] = _load_meta()
    G['deck'] = dsh._baseline_deck()   # baseline 自家牌组 (config A 牌面)


def _eval(task):
    leg, n = task
    r = ar.run_arena(G['mod'].agent, G['mod'].agent, G['deck'], G['meta'][leg],
                     n, seed0=9000)
    return leg, r['wins'], r['invalid'], n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--n', type=int, default=2000)
    ap.add_argument('--workers', type=int, default=3)
    args = ap.parse_args()

    # 防漂移 (#127): 提交捆绑 deck.csv 必须仍等于 baseline 自家牌组
    live = [int(l) for l in (PROJ / 'submission_baseline/deck.csv')
               .read_text().splitlines() if l.strip()]
    assert sorted(live) == sorted(dsh._baseline_deck()), 'submission_baseline/deck.csv 漂移!'

    t0 = time.time()
    tasks = [(leg, args.n) for leg, _ in LEGS]
    with mp.Pool(args.workers, initializer=_init_worker) as pool:
        res = pool.map(_eval, tasks)

    wr, inv = {}, 0
    for leg, w, i, n in res:
        wr[leg] = w / n
        inv += i
    wsum = sum(w * wr[leg] for leg, w in LEGS)

    print(f'{"leg":<13}{"w":>6}{"wr":>8}{"dVs0.5pp":>10}  tag')
    tags = {}
    for leg, w in LEGS:
        d = (wr[leg] - 0.5) * 100
        tag = '劣势' if d < -NOISE * 100 else ('优势' if d > NOISE * 100 else '均势')
        tags[leg] = tag
        print(f'{leg:<13}{w:>6.3f}{wr[leg]:>8.4f}{d:>+10.2f}  {tag}')
    print(f'weighted      {wsum:.4f} (dVs0.5 {(wsum - 0.5) * 100:+.2f}pp)  '
          f'invalid={inv}  ({time.time() - t0:.0f}s)')

    weak = [l for l, _ in LEGS if tags[l] == '劣势']
    verdict = (f'结构性劣势腿: {weak} → first-pilot 测试藏住的缺口, 值得评估改进靶'
               if weak else
               '无腿显著低于均势 → first-pilot 口径下无藏住的牌组缺口, 收兵口径再确认')
    print(f'VERDICT: {verdict}')

    OUT.write_text(json.dumps({'ts': time.time(), 'n_per_leg': args.n, 'wr': wr,
                               'weighted': wsum, 'invalid': inv, 'tags': tags,
                               'verdict': verdict,
                               'elapsed_s': round(time.time() - t0, 1)},
                              ensure_ascii=False, indent=1))
    print(f'→ {OUT}')


if __name__ == '__main__':
    main()
