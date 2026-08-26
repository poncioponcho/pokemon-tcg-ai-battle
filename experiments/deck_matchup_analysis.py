# -*- coding: utf-8 -*-
"""deck_matchup_analysis.py — 我方牌组 vs 官方样例牌组的对位分析。

起因：deck_policy_isolation.py 证明 'first' 对局 0.33 的主因是卡组效应
(+0.159 vs 策略效应 +0.025)。本脚本解码两副 60 张牌组，对比：
  1. 构成（宝可梦/训练家/能量）
  2. 速度线（min_energy 分布、首攻回合代理、每能量伤害效率）
  3. 属性克制矩阵（我方攻击属性 × 样例防御弱点，及反向）
  4. 身板（HP 分布、ex/mega_ex 密度）
输出给"换卡建议"用的定量依据。零 GPU。
"""
import collections
import sys
from pathlib import Path

PROJ = Path('/Users/seyonmacbook/Desktop/Pokemon_TCG_AI_Battle_Challenge')
sys.path.insert(0, str(PROJ))
import main  # noqa: E402  (用其 _CARD_DB / _TRAINER_IDS)

COMP = PROJ / 'inference' / 'comp_data' / 'sample_submission' / 'sample_submission'
OUR = [int(l.strip()) for l in (PROJ / 'deck.csv').read_text().splitlines() if l.strip()]
SAMPLE = [int(l.strip()) for l in (COMP / 'deck.csv').read_text().splitlines() if l.strip()]
DB = main._CARD_DB
TRAINERS = set(getattr(main, '_TRAINER_IDS', set()) or set())


def cat(cid, db):
    if db.get('is_energy'):
        return 'energy'
    if cid in TRAINERS:
        return 'trainer'
    if db.get('hp', 0) > 0:
        return 'pokemon'
    return 'unknown'


def summarize(name, deck):
    cnt = collections.Counter(deck)
    cats = collections.Counter()
    types = collections.Counter()
    rules = collections.Counter()
    stages = collections.Counter()
    min_en = collections.Counter()
    hps, dmgs, effs = [], [], []
    pokes = []
    for cid, n in sorted(cnt.items()):
        db = DB.get(cid, {})
        c = cat(cid, db)
        cats[c] += n
        if c == 'pokemon':
            t = db.get('type', '?')
            types[t] += n
            rules[db.get('rule', '') or 'normal'] += n
            stages['basic' if db.get('evolves_from', -1) in (-1, None) else 'evolve'] += n
            me = db.get('min_energy', db.get('needed_energy', 99))
            min_en[me] += n
            hp = db.get('hp', 0)
            pw = db.get('power', 0)
            hps.append((hp, n))
            dmgs.append((pw, n))
            if me and me > 0:
                effs.append((pw / me, n))
            pokes.append((cid, n, t, hp, pw, me,
                          db.get('weakness', ''), db.get('rule', '') or '',
                          'evo' if db.get('evolves_from', -1) not in (-1, None) else 'base'))
        elif c == 'unknown':
            pokes.append((cid, n, '???', 0, 0, 0, '', '', '?'))
    print(f"\n===== {name} (60 张, {len(cnt)} 种) =====")
    print(f"构成: {dict(cats)}")
    print(f"属性: {dict(types)} | 规则: {dict(rules)} | 阶段: {dict(stages)}")
    print(f"min_energy 分布: {dict(sorted(min_en.items()))}")
    if hps:
        tw = sum(h * n for h, n in hps) / sum(n for _, n in hps)
        td = sum(d * n for d, n in dmgs) / sum(n for _, n in dmgs)
        te = sum(e * n for e, n in effs) / sum(n for _, n in effs) if effs else 0
        fast = sum(n for (m, n) in min_en.items() if m <= 1)
        print(f"加权: 平均HP {tw:.0f} | 平均伤害 {td:.0f} | 伤害/能量 {te:.1f} | "
              f"1能量即攻卡 {fast}/60")
    print("宝可梦明细 (cid×数 类型 HP 伤害 minEn 弱点 规则 阶段):")
    for p in pokes:
        print(f"  {p[0]:>5}×{p[1]} {p[2]:>2} HP{p[3]:>3} 伤{p[4]:>3} 能{p[5]} "
              f"弱{p[6]:>2} {p[7]:>8} {p[8]}")
    return cnt, pokes


def weakness_matrix(name, atk_cnt, def_cnt, label):
    print(f"\n--- {label} ---")
    hits = collections.Counter()
    for ac, an in atk_cnt.items():
        adb = DB.get(ac, {})
        at = adb.get('type', '')
        if not at or adb.get('hp', 0) == 0:
            continue
        for dc, dn in def_cnt.items():
            ddb = DB.get(dc, {})
            if ddb.get('hp', 0) == 0:
                continue
            if ddb.get('weakness', '') == at:
                hits[at] += an * dn
    print(f"{name}: 弱点命中加权数 = {dict(hits)} (越大越克制)")


our_cnt, our_pokes = summarize('我方 OUR_DECK', OUR)
sm_cnt, sm_pokes = summarize('样例 SAMPLE_DECK', SAMPLE)
weakness_matrix('我方攻击 → 样例防御', our_cnt, sm_cnt, '克制样例')
weakness_matrix('样例攻击 → 我方防御', sm_cnt, our_cnt, '被样例克制')
