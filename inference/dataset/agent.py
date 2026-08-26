"""Standalone NN policy agent: mirrors extract.py feature building at inference time.

Usage:
    python3 agent.py                     # self-test with mock obs
    python3 agent.py --mock-game         # play a mock game vs first_agent (no engine)
"""
import json, os, sys
import numpy as np
import torch

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
import train_bc
try:
    from .card_vocab import card_index
except ImportError:
    from card_vocab import card_index

VOCAB = train_bc.VOCAB
CARD_DIM = int(VOCAB['size'])
K = 64
N_CTX, N_STYPE, O_DIM = 45, 10, 52
AREA_MAX, STYPE_MAX = 12, 15


def load_model(path=None):
    path = path or os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'model_awr.pt')
    meta_path = os.path.join(os.path.dirname(path), 'model_meta.json')
    if os.path.exists(meta_path):
        with open(meta_path, encoding='utf-8') as handle:
            model_meta = json.load(handle)
        if model_meta.get('card_vocab_version') != VOCAB.get('version'):
            raise RuntimeError(
                'Model/card vocabulary mismatch: '
                f"{model_meta.get('card_vocab_version')} != {VOCAB.get('version')}"
            )
    m = train_bc.Policy()
    m.load_state_dict(torch.load(path, map_location='cpu'))
    m.eval()
    return m


def _onehot(v, n, out, start):
    if v is not None and 0 <= int(v) < n:
        out[start + int(v)] = 1


def build_state_obs(obs, deck=None):
    sel = obs.get('select') or {}
    cur = obs.get('current')
    st = np.zeros(11 * CARD_DIM, dtype=np.float32)
    sc = np.zeros(90, dtype=np.float32)
    o = np.zeros((K, O_DIM), dtype=np.float32)
    mk = np.zeros(K, dtype=np.float32)
    opts = sel.get('option') or []
    n_opts = len(opts)
    for k in range(min(K, n_opts)):
        mk[k] = 1
        op = opts[k] if isinstance(opts[k], dict) else {}
        base = 0
        _onehot(op.get('type'), STYPE_MAX + 1, o[k], base); base += STYPE_MAX + 1
        _onehot(op.get('area'), AREA_MAX + 1, o[k], base); base += AREA_MAX + 1
        _onehot(op.get('inPlayArea'), AREA_MAX + 1, o[k], base); base += AREA_MAX + 1
        for name in ('playerIndex', 'index', 'inPlayIndex', 'attackId',
                     'count', 'number', 'serial', 'energyIndex', 'toolIndex', 'cardId'):
            v = op.get(name)
            if name == 'cardId':
                o[k, base] = min(card_index(v, VOCAB), 255)
            elif isinstance(v, (int, float)) and v >= 0:
                o[k, base] = min(int(v), 255)
            base += 1
    if cur is None:
        return st, sc, o, mk, n_opts
    ps = cur.get('players') or []
    yi = cur.get('yourIndex', 0)
    if len(ps) < 2:
        ps = [{'active': [], 'bench': [], 'hand': [], 'discard': []} for _ in range(2)]
    mine, opp = ps[yi % len(ps)], ps[(yi + 1) % len(ps)]
    for c in mine.get('hand') or []:
        if isinstance(c, dict) and c.get('id') is not None:
            st[card_index(c['id'], VOCAB)] += 1
    for p, off in ((mine, CARD_DIM), (opp, 2 * CARD_DIM)):
        for c in p.get('discard') or []:
            if isinstance(c, dict) and c.get('id') is not None:
                st[off + card_index(c['id'], VOCAB)] += 1
    if deck:
        cnt = np.bincount([card_index(c, VOCAB) for c in deck], minlength=CARD_DIM)
        st[3 * CARD_DIM:4 * CARD_DIM] = cnt[:CARD_DIM]
    for p, off, attr in ((mine, 5 * CARD_DIM, 'active'), (opp, 6 * CARD_DIM, 'active'),
                         (mine, 7 * CARD_DIM, 'bench'), (opp, 8 * CARD_DIM, 'bench')):
        for c in p.get(attr) or []:
            if isinstance(c, dict) and c.get('id') is not None:
                st[off + card_index(c['id'], VOCAB)] += 1
    for p, off in ((mine, 9 * CARD_DIM), (opp, 10 * CARD_DIM)):
        for pm in (p.get('active') or []) + (p.get('bench') or []):
            if isinstance(pm, dict):
                for e in pm.get('energies') or []:
                    if isinstance(e, int):
                        st[off + card_index(e, VOCAB)] += 1
    m_a = (mine.get('active') or [None])[0]
    o_a = (opp.get('active') or [None])[0]
    m_a = m_a if isinstance(m_a, dict) else None
    o_a = o_a if isinstance(o_a, dict) else None
    mh, mmh = (m_a.get('hp', 0), m_a.get('maxHp', 1)) if m_a else (0, 1)
    oh, omh = (o_a.get('hp', 0), o_a.get('maxHp', 1)) if o_a else (0, 1)
    sc[0] = mh; sc[1] = mh / mmh; sc[2] = oh; sc[3] = oh / omh
    sc[4] = len(m_a.get('energies', [])) if m_a else 0
    sc[5] = len(o_a.get('energies', [])) if o_a else 0
    sc[6] = len(mine.get('bench', [])); sc[7] = len(opp.get('bench', []))
    sc[8] = len(mine.get('hand', [])); sc[9] = mine.get('deckCount', 0); sc[10] = opp.get('deckCount', 0)
    sc[11] = len(mine.get('prize', [])); sc[12] = len(opp.get('prize', []))
    for i, s_name in enumerate(('asleep', 'burned', 'confused', 'paralyzed', 'poisoned')):
        sc[13 + i] = 1 if mine.get(s_name) else 0
        sc[18 + i] = 1 if opp.get(s_name) else 0
    sc[23] = cur.get('turn', 0); sc[24] = cur.get('turnActionCount', 0)
    for j, fl in enumerate(('energyAttached', 'supporterPlayed', 'stadiumPlayed', 'retreated')):
        sc[25 + j] = 1 if cur.get(fl) else 0
    sc[29] = cur.get('firstPlayer', 0); sc[30] = yi
    _onehot(sel.get('context'), N_CTX, sc, 31)
    _onehot(sel.get('type'), N_STYPE, sc, 31 + N_CTX)
    sc[31 + N_CTX + N_STYPE] = sel.get('maxCount', 1)
    sc[32 + N_CTX + N_STYPE] = sel.get('minCount', 1)
    sc[33 + N_CTX + N_STYPE] = sel.get('remainDamageCounter', 0)
    sc[34 + N_CTX + N_STYPE] = sel.get('remainEnergyCost', 0)
    return st, sc, o, mk, n_opts


def agent(obs, model=None, deck=None, max_count_hint=None):
    """Same contract as main.agent: obs -> list[int] option indices."""
    if obs is None or obs.get('select') is None:
        return deck if deck else []
    sel = obs['select']
    opts = sel.get('option') or []
    n = len(opts)
    if n == 0:
        return []
    mc = max_count_hint or sel.get('maxCount', 1)
    if mc >= n:
        return list(range(n))
    if model is None:
        # [fix 08-09] 原为 return [0]: mc>1 时欠选(长度<maxCount 违反动作铁律),
        # 改为返回前 mc 个合法下标
        return list(range(mc))
    st, sc, o, mk, n_opts = build_state_obs(obs, deck)
    with torch.no_grad():
        t_st = torch.from_numpy(st).unsqueeze(0)
        t_sc = torch.from_numpy(sc).unsqueeze(0)
        t_o = torch.from_numpy(o).unsqueeze(0)
        t_mk = torch.from_numpy(mk).unsqueeze(0)
        logits = model(t_st, t_sc, t_o, t_mk)
    top = torch.topk(logits, mc).indices.flatten().tolist()
    top = [i for i in top if 0 <= i < n]
    if not top:
        top = [0]
    return top[:mc]


if __name__ == '__main__':
    deck = [int(l.strip()) for l in open(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'deck.csv')) if l.strip()]
    model = load_model()
    obs = {
        'select': {'type': 0, 'context': 0, 'maxCount': 1, 'minCount': 1,
                   'option': [{'type': 14}, {'type': 12}, {'type': 7, 'index': 0}]},
        'current': {'yourIndex': 0, 'turn': 5, 'players': [
            {'active': [{'id': 331, 'hp': 60, 'maxHp': 60, 'energies': [], 'energyCards': []}],
             'bench': [], 'hand': [{'id': 331}, {'id': 5}], 'discard': [], 'deckCount': 40, 'prize': [None] * 6},
            {'active': [{'id': 77, 'hp': 60, 'maxHp': 60, 'energies': [], 'energyCards': []}],
             'bench': [], 'hand': None, 'discard': [], 'deckCount': 40, 'prize': [None] * 6},
        ]},
    }
    print('deck phase:', agent({'select': None}, model=model, deck=deck)[:5], '... len', len(agent({'select': None}, model=model, deck=deck)))
    a = agent(obs, model=model, deck=deck)
    print('decision action:', a, '(valid range 0..2)')
