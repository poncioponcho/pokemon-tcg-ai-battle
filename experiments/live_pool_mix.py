"""live_pool_mix.py — 从 42 局 live replay 反推 live 池牌族配比 (A 轨 N3 子步, 只读)

输入:
  experiments/runs/live_replays/episode-*-replay.json  (42 局, 在盘)
  experiments/runs/live_loss_report.json               (per_game: ep/reward/opp, 校准胜负)
方法:
  每局每座位, 跨全部步并集公共区可见卡 id (active/bench/discard/prize + preEvolution),
  喂 experiments/deck_recognizer.py 的 classify_ids (PMI 签名, margin=2.0 弃权→other)。
  我方座位判定: replay info.TeamNames 里 == 我方 agent 名 (Daniel1547) 的座位;
  双 Daniel1547 = 我方两发自撞 (mirror), 对手牌组=我方 Lucario 系, 单列。
输出:
  experiments/runs/live_pool_mix.json  {per_game, mix, mix_ex_mirror, by_arch WR}
"""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

PROJ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJ / 'experiments'))
import deck_recognizer as dr  # noqa: E402

OUR_NAME = 'Daniel1547'
REPLAY_DIR = PROJ / 'experiments/runs/live_replays'
REPORT = PROJ / 'experiments/runs/live_loss_report.json'
OUT = PROJ / 'experiments/runs/live_pool_mix.json'

ZONES = ('active', 'bench', 'discard', 'prize')


def seat_visible_ids(replay, seat):
    """跨全部步, 并集 seat 的公共区可见卡 id (含 preEvolution)。"""
    ids = set()
    for step in replay['steps']:
        obs = step[seat]['observation'] or {}
        cur = obs.get('current') or {}
        players = cur.get('players') or []
        if len(players) < 2:
            continue
        p = players[seat]
        for zone in ZONES:
            for card in (p.get(zone) or []):
                if not isinstance(card, dict):
                    continue
                if card.get('id'):
                    ids.add(card['id'])
                for pre in (card.get('preEvolution') or []):
                    if isinstance(pre, dict) and pre.get('id'):
                        ids.add(pre['id'])
    return ids


def classify(ids):
    if not ids:
        return 'other'
    r = dr.classify_ids(list(ids), margin=2.0)
    return r[0] if r else 'other'


def main():
    report = json.load(open(REPORT))
    ep_reward = {g['ep']: g['reward'] for g in report['per_game']}
    ep_opp = {g['ep']: g['opp'] for g in report['per_game']}

    per_game = []
    mix = Counter()
    arch_result = defaultdict(lambda: [0, 0])  # arch -> [win, loss]
    n_mirror = 0
    for f in sorted(REPLAY_DIR.glob('episode-*-replay.json')):
        ep = int(f.stem.split('-')[1])
        replay = json.load(open(f))
        names = (replay.get('info') or {}).get('TeamNames') or []
        mirror = len(names) == 2 and names[0] == names[1] == OUR_NAME
        if mirror:
            n_mirror += 1
        # 我方座位: TeamNames 里首个 == OUR_NAME; mirror 时取 0 (对手=1, 同牌组)
        our_seat = names.index(OUR_NAME) if OUR_NAME in names else 0
        opp_seat = 1 - our_seat
        opp_ids = seat_visible_ids(replay, opp_seat)
        arch = classify(opp_ids)
        if mirror:
            arch_tag = f'mirror:{arch}'
        else:
            arch_tag = arch
        reward = ep_reward.get(ep)
        per_game.append({'ep': ep, 'opp': ep_opp.get(ep), 'mirror': mirror,
                         'opp_arch': arch, 'n_opp_visible_ids': len(opp_ids),
                         'reward': reward})
        mix[arch_tag] += 1
        if reward == 1:
            arch_result[arch_tag][0] += 1
        elif reward == -1:
            arch_result[arch_tag][1] += 1

    total = sum(mix.values())
    mix_ex_mirror = Counter({k: v for k, v in mix.items() if not k.startswith('mirror:')})
    total_ex = sum(mix_ex_mirror.values())

    out = {
        'source': 'live_replays(42) + deck_recognizer.classify_ids(margin=2.0)',
        'n_games': total, 'n_mirror': n_mirror,
        'mix': {k: {'n': v, 'pct': round(v / total, 4)} for k, v in mix.most_common()},
        'mix_ex_mirror': {k: {'n': v, 'pct': round(v / total_ex, 4)}
                          for k, v in mix_ex_mirror.most_common()},
        'by_arch': {k: {'win': w, 'loss': l,
                        'wr': round(w / (w + l), 4) if w + l else None}
                    for k, (w, l) in arch_result.items()},
        'per_game': per_game,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1))

    print(f'n={total}  mirror={n_mirror}')
    print(f'{"arch":<22}{"n":>4}{"pct":>8}{"pct_ex_mirror":>14}{"W":>4}{"L":>4}{"WR":>8}')
    for k, v in mix.most_common():
        w, l = arch_result[k]
        wr = f'{w/(w+l):.3f}' if w + l else '-'
        ex = f'{v/total_ex:.1%}' if not k.startswith('mirror:') else '-'
        print(f'{k:<22}{v:>4}{v/total:>8.1%}{ex:>14}{w:>4}{l:>4}{wr:>8}')
    print(f'\n-> {OUT}')


if __name__ == '__main__':
    main()
