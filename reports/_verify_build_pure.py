#!/usr/bin/env python3
"""纯 Python 提交生成器（无 numpy 依赖，Kaggle 验证环境无 numpy）。

用法:
  uv run build_pure.py          # 读 exports/weights.npz -> exports/submission_pure.tar.gz

生成的 main.py 自包含：特征构建 + 策略前向 + 权重（base64）全部内嵌，
仅依赖 stdlib（base64/io/json/os/struct）。伴生文件仅 deck.csv。
"""
import argparse
import base64
import json
import struct
import tarfile
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent
EXPORTS = REPO / 'exports'
DEFAULT_DECK = (
    [5] * 10 + [9] * 2 + [77] * 4 + [156] * 4 + [157] * 4 + [331] * 4 +
    [408] * 4 + [474] * 4 + [528] * 4 + [530] * 4 + [532] + [554] * 3 +
    [576] * 4 + [585] * 4 + [630] * 4
)

K = 64
CARD_DIM = 400
ST_DIM = 11 * CARD_DIM
SC_DIM = 90
O_DIM = 52
N_CTX = 45
N_STYPE = 10
AREA_MAX = 12
STYPE_MAX = 15

MAIN_TMPL = '''# -*- coding: utf-8 -*-
"""NN agent 提交入口（build_pure.py 生成，勿手改）。纯 Python 实现，无 numpy 依赖。"""
import base64
import json
import os
import struct
import sys
from operator import mul

try:
    _BASE = os.path.dirname(os.path.abspath(__file__))
except NameError:
    # Kaggle harness exec 源码时无 __file__（champion main.py 已验证此行为，
    # 2026-08-08 定位：这是 NN 提交 6 连 validation 失败的根因）
    _BASE = os.getcwd()

_WEIGHTS_B64 = "{weights_b64}"


def _load_weights():
    data = base64.b64decode(_WEIGHTS_B64)
    magic, n = struct.unpack("<4sI", data[:8])
    assert magic == b"PTW1", "weights magic mismatch"
    off = 8
    w = {{}}
    for _ in range(n):
        (nl,) = struct.unpack("<I", data[off:off + 4]); off += 4
        name = data[off:off + nl].decode("utf-8"); off += nl
        (nd,) = struct.unpack("<I", data[off:off + 4]); off += 4
        shape = struct.unpack("<" + "I" * nd, data[off:off + 4 * nd]); off += 4 * nd
        (sz,) = struct.unpack("<I", data[off:off + 4]); off += 4
        vals = struct.unpack("<" + "f" * (sz // 4), data[off:off + sz]); off += sz
        if nd == 2:
            out, inn = shape
            w[name] = [list(vals[r * inn:(r + 1) * inn]) for r in range(out)]
        else:
            w[name] = list(vals)
    return w


_W = _load_weights()


def _lin(prefix, seq, inp):
    w = _W[prefix + "." + str(seq) + ".weight"]
    b = _W[prefix + "." + str(seq) + ".bias"]
    return [sum(map(mul, wj, inp)) + bj for wj, bj in zip(w, b)]


def _relu(x):
    return [max(v, 0.0) for v in x]


# Kaggle 评测环境读不到 deck.csv（champion main.py 已验证此行为），
# 内联牌组兜底，缺文件时降级而非 import 崩溃。
_INLINE_DECK = {inline_deck}


def _load_deck():
    try:
        deck = []
        with open(os.path.join(_BASE, "deck.csv"), encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    deck.append(int(line))
        if len(deck) == 60:
            return deck
        raise ValueError(f"deck.csv 应为 60 行, 实际 {{len(deck)}} 行")
    except Exception as e:
        sys.stderr.write(f"[PTCG-NN] deck.csv 读取失败, 回退内联牌组: {{e}}\\n")
        return list(_INLINE_DECK)


DECK = _load_deck()

_VOCAB_JSON = r"""{vocab_json}"""

_VOCAB = json.loads(_VOCAB_JSON)
_ID2IDX = {{int(c): int(i) for c, i in _VOCAB["id_to_index"].items()}}
_DIM = int(_VOCAB["size"])

_DIV = [60.0] * (5 * {CARD_DIM}) + [1.0] * (2 * {CARD_DIM}) + [5.0] * (2 * {CARD_DIM}) + [20.0] * (2 * {CARD_DIM})


def _f32(v):
    return struct.unpack("<f", struct.pack("<f", v))[0]


def _card_index(cid):
    if isinstance(cid, dict):
        cid = cid.get("id")
    try:
        return int(_ID2IDX.get(int(cid), 0))
    except (TypeError, ValueError):
        return 0


def _onehot(v, n, out, start):
    if v is not None:
        try:
            iv = int(v)
            if 0 <= iv < n:
                out[start + iv] = 1
        except (TypeError, ValueError):
            pass


def build_features(obs):
    sel = obs.get("select") or {{}}
    cur = obs.get("current")
    st = [0] * {ST_DIM}
    sc = [0.0] * {SC_DIM}
    o = [[0] * {O_DIM} for _ in range({K})]
    mask = [0] * {K}
    opts = sel.get("option") or []
    n_opts = len(opts)
    for k in range(min({K}, n_opts)):
        mask[k] = 1
        op = opts[k] if isinstance(opts[k], dict) else {{}}
        base = 0
        _onehot(op.get("type"), {STYPE_MAX} + 1, o[k], base); base += {STYPE_MAX} + 1
        _onehot(op.get("area"), {AREA_MAX} + 1, o[k], base); base += {AREA_MAX} + 1
        _onehot(op.get("inPlayArea"), {AREA_MAX} + 1, o[k], base); base += {AREA_MAX} + 1
        for name in ("playerIndex", "index", "inPlayIndex", "attackId",
                     "count", "number", "serial", "energyIndex", "toolIndex", "cardId"):
            v = op.get(name)
            if name == "cardId":
                o[k][base] = min(_card_index(v), 255)
            elif isinstance(v, (int, float)):
                o[k][base] = 255 if v > 255 else max(int(v), 0)
            base += 1
    if cur is None:
        return st, sc, o, mask
    ps = cur.get("players") or []
    if not ps:
        ps = [{{"active": [], "bench": [], "hand": [], "discard": [], "deckCount": 0}} for _ in range(2)]
    yi = cur.get("yourIndex", 0)
    mine, opp = ps[yi % len(ps)], ps[(yi + 1) % len(ps)]

    def card_vec(ids, out, start):
        for c in ids or []:
            idx = start + _card_index(c)
            out[idx] = (out[idx] + 1) % 256

    def deck_bag(d, out, start):
        for c in d or []:
            idx = start + _card_index(c)
            out[idx] = (out[idx] + 1) % 256

    card_vec(mine.get("hand"), st, 0)
    card_vec(mine.get("discard"), st, {CARD_DIM})
    card_vec(opp.get("discard"), st, 2 * {CARD_DIM})
    deck_bag(DECK, st, 3 * {CARD_DIM})
    # slot4 (对手牌组) 留零 —— 与训练侧 extract.py 一致（对手牌组不可观测，
    # 训练填充会造成泄漏 + 推理分布偏移；推理侧同样置零保持同分布）
    card_vec(mine.get("active"), st, 5 * {CARD_DIM})
    card_vec(opp.get("active"), st, 6 * {CARD_DIM})
    card_vec(mine.get("bench"), st, 7 * {CARD_DIM})
    card_vec(opp.get("bench"), st, 8 * {CARD_DIM})

    def energy_bag(p, out, start):
        for pm in (p.get("active") or []) + (p.get("bench") or []):
            if isinstance(pm, dict):
                for e in pm.get("energies") or []:
                    if isinstance(e, int):
                        idx = _ID2IDX.get(e, 0)
                        if idx < {CARD_DIM}:
                            out[start + idx] = (out[start + idx] + 1) % 256
    energy_bag(mine, st, 9 * {CARD_DIM})
    energy_bag(opp, st, 10 * {CARD_DIM})

    m_a = (mine.get("active") or [None])[0]
    o_a = (opp.get("active") or [None])[0]
    m_a = m_a if isinstance(m_a, dict) else None
    o_a = o_a if isinstance(o_a, dict) else None
    mh, mmh = (m_a.get("hp", 0), m_a.get("maxHp", 1)) if m_a else (0, 1)
    oh, omh = (o_a.get("hp", 0), o_a.get("maxHp", 1)) if o_a else (0, 1)
    sc[0] = mh; sc[1] = _f32(mh / mmh); sc[2] = oh; sc[3] = _f32(oh / omh)
    sc[4] = len(m_a.get("energies", [])) if m_a else 0
    sc[5] = len(o_a.get("energies", [])) if o_a else 0
    sc[6] = len(mine.get("bench", [])); sc[7] = len(opp.get("bench", []))
    sc[8] = len(mine.get("hand", [])); sc[9] = mine.get("deckCount", 0)
    sc[10] = opp.get("deckCount", 0)
    sc[11] = len(mine.get("prize", [])); sc[12] = len(opp.get("prize", []))
    for i, sname in enumerate(("asleep", "burned", "confused", "paralyzed", "poisoned")):
        sc[13 + i] = 1 if mine.get(sname) else 0
        sc[18 + i] = 1 if opp.get(sname) else 0
    sc[23] = cur.get("turn", 0); sc[24] = cur.get("turnActionCount", 0)
    for j, fl in enumerate(("energyAttached", "supporterPlayed", "stadiumPlayed", "retreated")):
        sc[25 + j] = 1 if cur.get(fl) else 0
    sc[29] = cur.get("firstPlayer", 0); sc[30] = yi
    _onehot(sel.get("context"), {N_CTX}, sc, 31)
    _onehot(sel.get("type"), {N_STYPE}, sc, 31 + {N_CTX})
    sc[31 + {N_CTX} + {N_STYPE}] = sel.get("maxCount", 1)
    sc[32 + {N_CTX} + {N_STYPE}] = sel.get("minCount", 1)
    sc[33 + {N_CTX} + {N_STYPE}] = sel.get("remainDamageCounter", 0)
    sc[34 + {N_CTX} + {N_STYPE}] = sel.get("remainEnergyCost", 0)
    return st, sc, o, mask


_NUM_HEADS = {num_heads}


def forward(st, sc, opts, mask, option_types=None):
    x = [st[i] / _DIV[i] for i in range({ST_DIM})] + sc
    e = _relu(_lin("enc", 0, x))
    e = _relu(_lin("enc", 2, e))
    e = _relu(_lin("enc", 4, e))
    logits = []
    for k in range({K}):
        if not mask[k]:
            logits.append(-1e30)
            continue
        h = e + opts[k]
        if option_types is not None:
            ot = option_types[k]
            if ot > _NUM_HEADS - 1:
                ot = _NUM_HEADS - 1
        else:
            ot = 0
        for i in range(_NUM_HEADS):
            if i == ot:
                hh = _relu(_lin("heads." + str(i), 0, h))
                logits.append(_lin("heads." + str(i), 2, hh)[0])
                break
    return logits


def _safe_maxcount(sel):
    mc = sel.get("maxCount", 1)
    return mc if isinstance(mc, int) and mc > 0 else 1


def agent(obs, config=None):
    if obs is None:
        return []
    sel = obs.get("select")
    if sel is None:
        return DECK
    if not isinstance(sel, dict):
        return []
    try:
        st, sc, opts, mask = build_features(obs)
        logits = forward(st, sc, opts, mask)
        valid = [i for i, m in enumerate(mask) if m]
        mc = min(_safe_maxcount(sel), len(valid))
        valid.sort(key=lambda i: -logits[i])
        return valid[:mc]
    except Exception:
        opts_sel = sel.get("option") or []
        if not isinstance(opts_sel, list):
            return []
        mc = min(_safe_maxcount(sel), len(opts_sel))
        return list(range(mc))
'''


def cmd_build(args):
    weights = np.load(EXPORTS / 'weights.npz')
    keys = sorted(weights.files)
    buf = bytearray()
    buf += struct.pack('<4sI', b'PTW1', len(keys))
    for k in keys:
        a = np.ascontiguousarray(weights[k], dtype=np.float32)
        nb = struct.pack('<I', len(k.encode())) + k.encode()
        nb += struct.pack('<I', a.ndim) + struct.pack('<' + 'I' * a.ndim, *a.shape)
        nb += struct.pack('<I', a.nbytes) + a.tobytes()
        buf += nb
    weights_b64 = base64.b64encode(bytes(buf)).decode()
    vocab = json.loads((REPO / 'docker' / 'card_vocab_v1.json').read_text())
    # Detect num_heads from weights (train.py Policy always uses 'heads.{i}.*' prefix)
    nh = 1
    for k in weights.files:
        if k.startswith('heads.1.'):
            nh = 4
            break
    if args.deck:
        deck = [int(l.strip()) for l in open(args.deck, encoding='utf-8') if l.strip()]
        if len(deck) != 60:
            raise SystemExit(f'deck 必须为 60 张，当前 {len(deck)}')
    else:
        deck = list(DEFAULT_DECK)
    main_py = MAIN_TMPL.format(
        weights_b64=weights_b64,
        vocab_json=json.dumps(vocab, ensure_ascii=False),
        CARD_DIM=CARD_DIM, ST_DIM=ST_DIM, SC_DIM=SC_DIM, O_DIM=O_DIM,
        K=K, N_CTX=N_CTX, N_STYPE=N_STYPE, AREA_MAX=AREA_MAX, STYPE_MAX=STYPE_MAX,
        num_heads=nh,
        inline_deck=repr(deck),
    )
    pkg = EXPORTS / 'pure_submission'
    pkg.mkdir(exist_ok=True)
    (pkg / 'main.py').write_text(main_py)
    (pkg / 'deck.csv').write_text('\n'.join(str(c) for c in deck) + '\n')
    tar = EXPORTS / 'submission_pure.tar.gz'
    with tarfile.open(tar, 'w:gz') as tf:
        tf.add(pkg / 'main.py', arcname='main.py')
        tf.add(pkg / 'deck.csv', arcname='deck.csv')
    print(f'pure: {tar} (deck={len(deck)}张 {args.deck or "DEFAULT_DECK"} '
          f'{main_py.count(chr(10))} lines main.py, weights {len(weights_b64) // 1024} KB b64)')


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--weights', default=str(EXPORTS / 'weights.npz'))
    ap.add_argument('--deck', default=None,
                    help='deck.csv 路径（60 张，默认 DEFAULT_DECK）')
    args = ap.parse_args()
    cmd_build(args)
