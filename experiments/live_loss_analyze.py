"""live_loss_analyze.py — config A live 败局归因 (复用 alakazam_diag 事件流逻辑)

输入: experiments/runs/live_replays/*.json + live_episodes_configA.json (对手身份)
产物: experiments/runs/live_loss_report.json + stdout 摘要

归因口径 (与本地诊断一致):
  KO = toArea==3 & fromArea∈{4,5}; 奖品 = fromArea==6 & toArea==2; 攻击 = type15
  logs 用我方视角单侧 (steps[i][us].observation.logs), playerIndex 为绝对座位。
  我方 = TeamNames/agents 里 teamName=='Daniel1547' 或 submissionId==55431232。
"""
import json
import sys
from collections import Counter
from pathlib import Path

PROJ = Path('/Users/seyonmacbook/Desktop/Pokemon_TCG_AI_Battle_Challenge')
sys.path.insert(0, str(PROJ / 'experiments'))
import arena_runner as ar  # noqa: E402

ROWS = {r['id']: r for r in json.load(open(PROJ / 'experiments/runs/live_episodes_configA.json'))}
REPLAYS = PROJ / 'experiments/runs/live_replays'
mod = ar.load_module(PROJ / 'experiments/runs/_configA/main_configA_pristine.py')
CT = mod.card_table


def pval(cid):
    e = CT.get(cid)
    return (3 if e.megaEx else (2 if e.ex else 1)) if e else None


def name(cid):
    e = CT.get(cid)
    return e.name if e else str(cid)


def parse(fp):
    d = json.load(open(fp))
    # 定位我方座位
    us = None
    for i, a in enumerate(d.get('info', {}).get('Agents', []) or []):
        pass
    teams = d.get('info', {}).get('TeamNames') or []
    for i, t in enumerate(teams):
        if t == 'Daniel1547':
            us = i
    if us is None:
        return None
    them = 1 - us
    rewards = d.get('rewards') or []
    my_deaths, their_deaths = [], []
    last_atk = {0: None, 1: None}
    prizes = {0: 0, 1: 0}
    opp_cards = set()
    prev = None  # replay logs=我方上次行动以来的窗口, 非行动点冻结重发 → 只消费新鲜窗口
    for step in d['steps']:
        if us >= len(step):
            continue
        lg = step[us].get('observation', {}).get('logs') or []
        if lg == prev:
            continue
        prev = lg
        for e in lg:
            t = e.get('type')
            if t == 15:
                last_atk[e.get('playerIndex')] = e.get('cardId')
                if e.get('playerIndex') == them:
                    opp_cards.add(e.get('cardId'))
            elif t in (6, 7):
                fa, ta, side = e.get('fromArea'), e.get('toArea'), e.get('playerIndex')
                cid = e.get('cardId')
                if ta == 3 and fa in (4, 5):
                    rec = (cid, pval(cid), last_atk[1 - side])
                    (my_deaths if side == us else their_deaths).append(rec)
                elif fa == 6 and ta == 2:
                    prizes[side] += 1
                if side == them and cid:
                    opp_cards.add(cid)
    return {
        'reward': rewards[us] if us < len(rewards) else None,
        'steps': len(d['steps']),
        'status_tail': (d.get('statuses') or [None])[-1],
        'my_deaths': my_deaths, 'their_deaths': their_deaths,
        'prizes_us': prizes[us], 'prizes_them': prizes[them],
        'opp_cards': sorted(c for c in opp_cards if c),
    }


def summarize(gs, tag):
    n = max(1, len(gs))
    all_my = [d for g in gs for d in g['my_deaths']]
    all_their = [d for g in gs for d in g['their_deaths']]
    killers = Counter(d[2] for d in all_my)
    kv = Counter((d[2], d[0]) for d in all_my)
    their_victims = Counter((d[0], d[1]) for d in all_their)
    print(f'\n### {tag} (n={len(gs)})')
    print(f'  局长 {sum(g["steps"] for g in gs)/n:.0f} 步 | 我方死 {len(all_my)/n:.2f}/局 (678: {sum(1 for d in all_my if d[0]==678)/n:.2f}/局) | 对方死 {len(all_their)/n:.2f}/局')
    print(f'  奖品竞速: 我们 {sum(g["prizes_us"] for g in gs)/n:.2f} vs 对面 {sum(g["prizes_them"] for g in gs)/n:.2f} /局')
    print('  凶手 top:', [(f'{name(k)}({k})' if k else None, c) for k, c in killers.most_common(6)])
    print('  凶手×受害者 top:', [((f'{name(k[0])}' if k[0] else None, name(k[1])), c) for k, c in kv.most_common(6)])
    print('  对面受害者 top:', [(f'{name(k[0])}({k[0]},{k[1]}奖品)', c) for k, c in their_victims.most_common(6)])
    return killers, kv, their_victims


def main():
    games = []
    for fp in sorted(REPLAYS.glob('*.json')):
        eid = int(''.join(c for c in fp.stem if c.isdigit()))
        g = parse(fp)
        if g is None:
            print(f'[skip] {fp.name}: 定位我方座位失败')
            continue
        g['ep'] = eid
        g['opp'] = ROWS.get(eid, {}).get('opp')
        games.append(g)
    n = len(games)
    print(f'解析 {n} 局 replay (胜+负)')

    W = [g for g in games if g['reward'] == 1]
    L = [g for g in games if g['reward'] == -1]
    kL, kvL, tvL = summarize(L, '败局')
    kW, kvW, tvW = summarize(W, '胜局')

    opp_sig = Counter()
    for g in L:
        for c in g['opp_cards']:
            opp_sig[c] += 1
    print('\n败局对手可见卡 top:', [(f'{name(k)}({k})', c) for k, c in opp_sig.most_common(15)])

    out = {
        'n': n, 'n_loss': len(L), 'n_win': len(W),
        'loss': {
            'avg_steps': round(sum(g['steps'] for g in L) / max(1, len(L)), 1),
            'my_deaths_pg': round(sum(len(g['my_deaths']) for g in L) / max(1, len(L)), 2),
            'their_deaths_pg': round(sum(len(g['their_deaths']) for g in L) / max(1, len(L)), 2),
            'prizes_us': round(sum(g['prizes_us'] for g in L) / max(1, len(L)), 2),
            'prizes_them': round(sum(g['prizes_them'] for g in L) / max(1, len(L)), 2),
            'killers': [(f'{name(k)}({k})' if k else 'None', c) for k, c in kL.most_common(10)],
            'killer_x_victim': [(str(k), c) for k, c in kvL.most_common(10)],
            'their_victims': [(str(k), c) for k, c in tvL.most_common(10)],
        },
        'win': {
            'avg_steps': round(sum(g['steps'] for g in W) / max(1, len(W)), 1),
            'my_deaths_pg': round(sum(len(g['my_deaths']) for g in W) / max(1, len(W)), 2),
            'their_deaths_pg': round(sum(len(g['their_deaths']) for g in W) / max(1, len(W)), 2),
            'prizes_us': round(sum(g['prizes_us'] for g in W) / max(1, len(W)), 2),
            'prizes_them': round(sum(g['prizes_them'] for g in W) / max(1, len(W)), 2),
            'killers': [(f'{name(k)}({k})' if k else 'None', c) for k, c in kW.most_common(10)],
            'their_victims': [(str(k), c) for k, c in tvW.most_common(10)],
        },
        'opp_card_freq_in_losses': [(f'{name(k)}({k})', c) for k, c in opp_sig.most_common(20)],
        'per_game': [{'ep': g['ep'], 'opp': g['opp'], 'reward': g['reward'], 'steps': g['steps'],
                      'prizes_us': g['prizes_us'], 'prizes_them': g['prizes_them'],
                      'my_deaths': len(g['my_deaths']), 'their_deaths': len(g['their_deaths'])}
                     for g in games],
    }
    (PROJ / 'experiments/runs/live_loss_report.json').write_text(
        json.dumps(out, ensure_ascii=False, indent=1))
    print('\nsaved -> experiments/runs/live_loss_report.json')


if __name__ == '__main__':
    main()
