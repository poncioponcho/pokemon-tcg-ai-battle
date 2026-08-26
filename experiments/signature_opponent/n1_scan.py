"""n1_scan.py — N1 旋钮可达区间扫描（N0 工程件②，2026-08-13 Kimi 自建）

双实例 harness：config A（pristine，我方牌组）vs 签名对手变体（sig_opp 旋钮格 × meta 腿）。
量测 = sig_opp 模块内 SigWatcher 自观测（spec §3.1 事件语义的 obs 侧实现，读对手侧=读变体自身）。

网格（runbook §1，单轴扫描；BASE=双关地板为 runbook 网格外延的一格，用于地板参照
和 N2 neither 格，不违 runbook——K0 判读只用 R 格区间上限）：
  BASE              pivot OFF + 罚分 0      ≡ config A 行为地板
  R-00/01/02        ③ 3奖身 × ⑤ buf 0/+1/+2
  R-10/11/12        ③ 2奖身+ × ⑤ buf 0/+1/+2
  E-1/2/3/4         罚分 200/400/800/1600   （pivot OFF；E-0 与 BASE 同构故并入 BASE）

腿（runbook §3，live 配比归一化；Gardevoir≈0 与 other 剔除）：
  Alakazam .274 / Lucario .175 / Crustle .175 / Cornerstone .100 /
  Grimmsnarl .100 / Archaludon .100 / Dragapult .075

K0 判读（互斥三分支，08-13 13:30 口径）：
  腿 pass = 该腿 R2 可达区间上限（R 格 max）≥1.5/局
  KILL（无条件优先）= 加权 fail 份额 ≥0.50（端点归 KILL）
  FLAG（仅当 <0.50）= 大腿（≥.15）或残差腿（Dragapult/Grimmsnarl/Archaludon）任一 fail
  PASS = 其余
  E1 只报告（目标带 6.2-10.9%，spec §2），K0 不判 E1。

用法：
  /opt/homebrew/bin/python3 experiments/signature_opponent/n1_scan.py --smoke
  /opt/homebrew/bin/python3 experiments/signature_opponent/n1_scan.py --n 400
产物：experiments/runs/n1_knob_scan.json + stdout 表（runbook §4 模板列）
纪律：#111 同批交错（逐局逐格轮转）；先后手逐局轮换；引擎不可播种（seed 仅对齐惯例）。
"""
import argparse
import json
import random
import statistics
import sys
import time
from pathlib import Path

PROJ = Path('/Users/seyonmacbook/Desktop/Pokemon_TCG_AI_Battle_Challenge')
sys.path.insert(0, str(PROJ / 'experiments'))
import arena_runner as ar  # noqa: E402
import deck_search_hybrid as dsh  # noqa: E402  (复用 _baseline_deck)

SIG_OPP = PROJ / 'experiments/signature_opponent/sig_opp.py'
PRISTINE = PROJ / 'experiments/runs/_configA/main_configA_pristine.py'
OUT = PROJ / 'experiments/runs/n1_knob_scan.json'

CELLS = [
    ('BASE', dict(on=False, scope=3, buf=0, pen=0)),
    ('R-00', dict(on=True, scope=3, buf=0, pen=0)),
    ('R-01', dict(on=True, scope=3, buf=1, pen=0)),
    ('R-02', dict(on=True, scope=3, buf=2, pen=0)),
    ('R-10', dict(on=True, scope=2, buf=0, pen=0)),
    ('R-11', dict(on=True, scope=2, buf=1, pen=0)),
    ('R-12', dict(on=True, scope=2, buf=2, pen=0)),
    ('E-1', dict(on=False, scope=3, buf=0, pen=200)),
    ('E-2', dict(on=False, scope=3, buf=0, pen=400)),
    ('E-3', dict(on=False, scope=3, buf=0, pen=800)),
    ('E-4', dict(on=False, scope=3, buf=0, pen=1600)),
]
LEGS = [('Alakazam', 0.274), ('Lucario', 0.175), ('Crustle', 0.175),
        ('Cornerstone', 0.100), ('Grimmsnarl', 0.100), ('Archaludon', 0.100),
        ('Dragapult', 0.075)]
BIG = {'Alakazam', 'Lucario', 'Crustle'}
RESIDUAL = {'Dragapult', 'Grimmsnarl', 'Archaludon'}
R2_PASS = 1.5          # K0 腿 pass 线（spec R2 真人带 1.06-2.07 带内中高位）
E1_BAND = (6.2, 10.9)  # spec §2 E1 目标带（仅报告）


def load_meta_decks():
    meta = {}
    for a, _ in LEGS:
        csv = list((PROJ / 'experiments/arena_pool/meta').glob(f'{a}__*.csv'))[0]
        meta[a] = [int(l) for l in csv.read_text().splitlines() if l.strip()]
    return meta


def make_cell_mod(cfg):
    m = ar.load_module(SIG_OPP)
    m.SIG_RETREAT_ON = cfg['on']
    m.SIG_RETREAT_PRIZE_SCOPE = cfg['scope']
    m.SIG_RETREAT_BUFFER = cfg['buf']
    m.SIG_NRG_ACTIVE_PENALTY = cfg['pen']
    return m


def stat_from_games(games):
    """watcher per-game 记录 → r2 逐局均值±SE、E1 汇总±SE（spec 聚合约定：和的比，非比的均值）。"""
    n = len(games)
    r2s = [g['sw8_vol'] - g['sw8_vol_pre'] for g in games]
    r2 = statistics.mean(r2s) if r2s else 0.0
    r2_se = (statistics.stdev(r2s) / (n ** 0.5)) if n > 1 else None
    pre = sum(g['nrg_pre'] for g in games)
    pre_act = sum(g['nrg_pre_act'] for g in games)
    pre_bench = sum(g['nrg_pre_bench'] for g in games)
    e1 = pre_act / pre * 100 if pre else None
    e1_se = ((e1 / 100 * (1 - e1 / 100) / pre) ** 0.5 * 100) if pre and e1 is not None else None
    e1_full = pre_act / (pre_act + pre_bench) * 100 if (pre_act + pre_bench) else None
    return {'games': n, 'r2': round(r2, 3), 'r2_se': round(r2_se, 3) if r2_se else None,
            'pre_n': pre, 'e1': round(e1, 1) if e1 is not None else None,
            'e1_se': round(e1_se, 1) if e1_se is not None else None,
            'e1_full': round(e1_full, 1) if e1_full is not None else None}


def k0_report(per_cell, legs, out_path, t0):
    """腿级可达区间 + K0 判读（互斥三分支）+ stdout 表 + JSON 落盘。--merge 模式复用。"""
    per_leg = []
    for leg, lw in legs:
        rows = [r for r in per_cell if r['leg'] == leg]
        r_rows = [r for r in rows if r['cell'].startswith('R-')]
        e_rows = [r for r in rows if r['cell'] == 'BASE' or r['cell'].startswith('E-')]
        r2s = [r['r2'] for r in r_rows]
        e1s = [r['e1'] for r in e_rows if r['e1'] is not None]
        leg_pass = bool(r2s) and max(r2s) >= R2_PASS
        per_leg.append({'leg': leg, 'live_w': lw,
                        'r2_reach': [round(min(r2s), 3), round(max(r2s), 3)] if r2s else None,
                        'e1_reach': [round(min(e1s), 1), round(max(e1s), 1)] if e1s else None,
                        'leg_pass': leg_pass,
                        'flag': (not leg_pass) and (leg in BIG or leg in RESIDUAL)})
    fail_w = sum(p['live_w'] for p in per_leg if not p['leg_pass'])
    if fail_w >= 0.50:
        k0 = 'KILL'
    elif any(p['flag'] for p in per_leg):
        k0 = 'FLAG'
    else:
        k0 = 'PASS'
    flagged = [p['leg'] for p in per_leg if p['flag']]

    print(f'\n{"leg":<12}{"w":>6}{"cell":>6}{"n":>5}{"usWR":>7}{"R2":>7}{"R2se":>7}'
          f'{"E1%":>7}{"E1se":>6}{"E1full":>7}{"invO":>5}')
    for r in per_cell:
        print(f'{r["leg"]:<12}{r["live_w"]:>6.3f}{r["cell"]:<6}{r["n"]:>5}'
              f'{r["us_wr"]:>7.3f}{r["r2"]:>7.3f}{r["r2_se"]!s:>7}'
              f'{r["e1"]!s:>7}{r["e1_se"]!s:>6}{r["e1_full"]!s:>7}{r["inv_opp"]:>5}')
    print('\n--- 腿级可达区间（R2 目标带 1.06-2.07，pass=上限≥1.5；E1 目标带 6.2-10.9 仅报告）---')
    for p in per_leg:
        print(f'{p["leg"]:<12}w={p["live_w"]:.3f} R2_reach={p["r2_reach"]} '
              f'E1_reach={p["e1_reach"]} pass={p["leg_pass"]} flag={p["flag"]}')
    print(f'\nK0: 加权 fail 份额={fail_w:.3f} → {k0}'
          + (f'（flagged: {flagged}）' if flagged else ''))

    out = {'ts': time.time(), 'grid': sorted(set(r['cell'] for r in per_cell)),
           'legs': [[a, w] for a, w in legs],
           'r2_pass_line': R2_PASS, 'e1_band': E1_BAND,
           'per_cell': per_cell, 'per_leg': per_leg,
           'k0': {'weighted_fail_share': round(fail_w, 3), 'verdict': k0, 'flagged_legs': flagged},
           'elapsed_s': round(time.time() - t0, 1)}
    Path(out_path).write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(f'→ {out_path}  ({time.time()-t0:.0f}s)')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--n', type=int, default=400)
    ap.add_argument('--legs', default=','.join(a for a, _ in LEGS))
    ap.add_argument('--cells', default=','.join(c for c, _ in CELLS))
    ap.add_argument('--seed0', type=int, default=9000)
    ap.add_argument('--smoke', action='store_true', help='n=30, Alakazam, BASE/R-12/E-4 验证量测')
    ap.add_argument('--merge', default='', help='逗号分隔的逐腿 JSON，只汇总出 K0 报告')
    ap.add_argument('--out', default=str(OUT))
    args = ap.parse_args()

    if args.merge:
        per_cell = []
        for fp in args.merge.split(','):
            per_cell.extend(json.loads(Path(fp.strip()).read_text())['per_cell'])
        k0_report(per_cell, LEGS, args.out, time.time())
        return

    if args.smoke:
        args.n, args.legs, args.cells = 30, 'Alakazam', 'BASE,R-12,E-4'

    legs = [(a, w) for a, w in LEGS if a in args.legs.split(',')]
    cells = [(c, cfg) for c, cfg in CELLS if c in args.cells.split(',')]
    meta = load_meta_decks()
    us = ar.load_module(PRISTINE)
    us_deck = dsh._baseline_deck()

    t0 = time.time()
    per_cell = []
    for leg, lw in legs:
        mods = {c: make_cell_mod(cfg) for c, cfg in cells}
        for m in mods.values():
            m.reset_stats()
        wins = {c: 0 for c, _ in cells}
        inv_us = {c: 0 for c, _ in cells}
        inv_opp = {c: 0 for c, _ in cells}
        n = args.n
        for g in range(n):
            if g % 100 == 0:
                print(f'  .. {leg} g={g}/{n} ({time.time()-t0:.0f}s)', flush=True)
            swap = (g % 2 == 1)
            if args.seed0:
                random.seed(args.seed0 + g)
            for c, _cfg in cells:
                opp = mods[c]
                fns = (us.agent, opp.agent) if not swap else (opp.agent, us.agent)
                dks = (us_deck, meta[leg]) if not swap else (meta[leg], us_deck)
                r = ar.play(fns, dks)
                fault = r.get('fault')
                if fault is not None:
                    us_faulty = (fault == 0 and not swap) or (fault == 1 and swap)
                    (inv_us if us_faulty else inv_opp)[c] += 1
                    if inv_opp[c] <= 2 and not us_faulty:
                        print(f'  !! 变体 fault leg={leg} cell={c} g={g}: {r.get("err")}', flush=True)
                w = r['winner']
                us_won = (w == 0 and not swap) or (w == 1 and swap)
                if us_won:
                    wins[c] += 1
        for c, cfg in cells:
            mods[c].finalize_stats()
            st = stat_from_games(mods[c].WATCHER.games)
            row = {'leg': leg, 'live_w': lw, 'cell': c, 'knobs': cfg, 'n': n,
                   'us_wr': round(wins[c] / n, 4), 'inv_us': inv_us[c], 'inv_opp': inv_opp[c], **st}
            per_cell.append(row)
        done = ', '.join(f'{c}:R2={next(r["r2"] for r in per_cell if r["leg"] == leg and r["cell"] == c)}'
                         for c, _ in cells[:3])
        print(f'[{leg}] n={n} 完成 ({time.time()-t0:.0f}s) {done} ...', flush=True)

    # ---- 腿级可达区间 + K0 判读（互斥三分支） ----
    per_leg = []
    for leg, lw in legs:
        rows = [r for r in per_cell if r['leg'] == leg]
        r_rows = [r for r in rows if r['cell'].startswith('R-')]
        e_rows = [r for r in rows if r['cell'] == 'BASE' or r['cell'].startswith('E-')]
        r2s = [r['r2'] for r in r_rows]
        e1s = [r['e1'] for r in e_rows if r['e1'] is not None]
        leg_pass = bool(r2s) and max(r2s) >= R2_PASS
        per_leg.append({'leg': leg, 'live_w': lw,
                        'r2_reach': [round(min(r2s), 3), round(max(r2s), 3)] if r2s else None,
                        'e1_reach': [round(min(e1s), 1), round(max(e1s), 1)] if e1s else None,
                        'leg_pass': leg_pass,
                        'flag': (not leg_pass) and (leg in BIG or leg in RESIDUAL)})
    fail_w = sum(p['live_w'] for p in per_leg if not p['leg_pass'])
    if fail_w >= 0.50:
        k0 = 'KILL'
    elif any(p['flag'] for p in per_leg):
        k0 = 'FLAG'
    else:
        k0 = 'PASS'
    flagged = [p['leg'] for p in per_leg if p['flag']]

    # ---- stdout 表（runbook §4 模板列） ----
    print(f'\n{"leg":<12}{"w":>6}{"cell":>6}{"n":>5}{"usWR":>7}{"R2":>7}{"R2se":>7}'
          f'{"E1%":>7}{"E1se":>6}{"E1full":>7}{"invO":>5}')
    for r in per_cell:
        print(f'{r["leg"]:<12}{r["live_w"]:>6.3f}{r["cell"]:<6}{r["n"]:>5}'
              f'{r["us_wr"]:>7.3f}{r["r2"]:>7.3f}{r["r2_se"]!s:>7}'
              f'{r["e1"]!s:>7}{r["e1_se"]!s:>6}{r["e1_full"]!s:>7}{r["inv_opp"]:>5}')
    print('\n--- 腿级可达区间（R2 目标带 1.06-2.07，pass=上限≥1.5；E1 目标带 6.2-10.9 仅报告）---')
    for p in per_leg:
        print(f'{p["leg"]:<12}w={p["live_w"]:.3f} R2_reach={p["r2_reach"]} '
              f'E1_reach={p["e1_reach"]} pass={p["leg_pass"]} flag={p["flag"]}')
    print(f'\nK0: 加权 fail 份额={fail_w:.3f} → {k0}'
          + (f'（flagged: {flagged}）' if flagged else ''))

    out = {'ts': time.time(), 'n_per_cell_leg': args.n, 'grid': [c for c, _ in cells],
           'legs': [[a, w] for a, w in legs],
           'r2_pass_line': R2_PASS, 'e1_band': E1_BAND,
           'per_cell': per_cell, 'per_leg': per_leg,
           'k0': {'weighted_fail_share': round(fail_w, 3), 'verdict': k0, 'flagged_legs': flagged},
           'elapsed_s': round(time.time() - t0, 1)}
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(f'→ {args.out}  ({time.time()-t0:.0f}s)')


if __name__ == '__main__':
    main()
