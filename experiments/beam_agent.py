"""beam_agent.py — 1-ply 搜索 + 规则 rollout 叶评估 (beam M2)

架构 (ledger#98 纪律): wrapper + 参数门控 + 规则 agent 当 leaf evaluator。
真实决策命中触发条件时: 对每个候选动作 search_step 进 child, 再用两个规则
agent 副本在搜索世界里对 rollout 至终局, 按 current.result 计分 (已校准:
0/1=绝对座位胜, 2=平, -1=未终局, 见 search_calib.py), argmax 胜出。
不命中/任何异常 → 回退纯规则, 行为与线上 main.py 完全一致。

触发 (默认窄, env 可调): ctx==0(MAIN) 且有 type==13 攻击选项 且 turn>=BEAM_MIN_TURN。

env 参数:
  BEAM_ENABLE=1|0        总开关 (默认 1; 0 = 纯规则直通)
  BEAM_MAX_CAND=6        每决策最多评估候选数
  BEAM_MIN_TURN=2        早于该 turn 不触发
  BEAM_TIME_MS=300       每真实决策的时间预算 (超出即停, 已评候选里取最优)
  BEAM_MAX_STEPS=400     单条 rollout 步数上限 (超限按 0.5 计)
  BEAM_OPP_DECK=mirror   对手牌组假设: 'mirror'=同 deck.csv | 'auto'=识别器
                         (deck_recognizer, 弃权时退化 mirror) | 一个 csv 路径
  BEAM_RECOG_MARGIN=2.0  auto 模式的识别判决 margin

arena 契约: agent(obs)->list[int]; obs 含 search_begin_input (arena_runner.OBS_KEYS)。
独立模块实例: 内部自载 3 份 main.py (self 决策 + 双座位 rollout), 互不串扰。
"""
import ctypes
import importlib.util
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

PROJ = Path(__file__).resolve().parent.parent
COMP = PROJ / 'inference/comp_data/sample_submission/sample_submission'
if str(COMP) not in sys.path:
    sys.path.insert(0, str(COMP))
from cg.sim import lib  # noqa: E402

DECK = [int(l) for l in (PROJ / 'deck.csv').read_text().splitlines() if l.strip()]

BEAM_ENABLE = os.environ.get('BEAM_ENABLE', '1') == '1'
BEAM_MAX_CAND = int(os.environ.get('BEAM_MAX_CAND', '6'))
BEAM_MIN_TURN = int(os.environ.get('BEAM_MIN_TURN', '2'))
BEAM_TIME_MS = float(os.environ.get('BEAM_TIME_MS', '300'))
BEAM_MAX_STEPS = int(os.environ.get('BEAM_MAX_STEPS', '400'))
_opp = os.environ.get('BEAM_OPP_DECK', 'mirror')
AUTO_OPP = _opp == 'auto'
OPP_DECK = None if AUTO_OPP else (DECK if _opp == 'mirror' else [
    int(l) for l in Path(_opp).read_text().splitlines() if l.strip()])
RECOG_MARGIN = float(os.environ.get('BEAM_RECOG_MARGIN', '2.0'))


def _load_module(name, path):
    """Load ``path`` under an isolated name, failing with path context."""
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f'cannot create module loader for {path}')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# auto 模式: 载识别器 (独立模块实例, 避免 sys.argv/路径串扰)
_recog = None
if AUTO_OPP:
    _recog = _load_module(
        'deck_recognizer', PROJ / 'experiments/deck_recognizer.py')

_stats = {'beam': 0, 'fallback': 0, 'abort': 0, 'rollouts': 0, 'ms': 0.0,
          'fb_no_sbi': 0, 'fb_no_hidden': 0, 'fb_no_cand': 0,
          'recog': Counter(), 'recog_none': 0, 'beam_deck': Counter()}


# ---------- 规则 agent 副本 (各自全局状态隔离) ----------
def _load_rule(tag):
    return _load_module(f'beam_rule_{tag}', PROJ / 'main.py')


_rule_self = _load_rule('self')
_rule_roll = [_load_rule('r0'), _load_rule('r1')]


# ---------- 官方 Search API 薄封装 (dict 进 dict 出) ----------
_agent_ptr = None


def _ptr():
    global _agent_ptr
    if _agent_ptr is None:
        _agent_ptr = lib.AgentStart()
    return _agent_ptr


def _iarr(xs):
    return (ctypes.c_int * len(xs))(*xs)


class _Ended(Exception):
    pass


def _sbegin(sbi, yd, yp, od, op, oh, oa):
    bs = lib.SearchBegin(_ptr(), sbi.encode('ascii'), len(sbi),
                         _iarr(yd), _iarr(yp), _iarr(od), _iarr(op),
                         _iarr(oh), _iarr(oa), 0)
    r = json.loads(bs)
    if r.get('error') != 0:
        raise RuntimeError(f'search_begin error={r.get("error")}')
    return r['state']


def _sstep(sid, pick):
    bs = lib.SearchStep(_ptr(), sid, _iarr(pick), len(pick))
    r = json.loads(bs)
    e = r.get('error')
    if e == 3:
        raise _Ended()
    if e != 0:
        raise RuntimeError(f'search_step error={e}')
    return r['state']


# ---------- 隐藏信息精确预测 (可见卡全减, 截到精确数量) ----------
def _zone_ids(p):
    """active/bench(含 attached) + discard 的可见卡 id。"""
    ids = []
    for zone in ('active', 'bench'):
        for pk in (p.get(zone) or []):
            if not isinstance(pk, dict):
                continue
            if pk.get('id'):
                ids.append(pk['id'])
            for key in ('energyCards', 'tools', 'preEvolution'):
                for c in (pk.get(key) or []):
                    if isinstance(c, dict) and c.get('id'):
                        ids.append(c['id'])
    for c in (p.get('discard') or []):
        if isinstance(c, dict) and c.get('id'):
            ids.append(c['id'])
    return ids


def _hidden_split(full_deck, known_ids, counts):
    """full_deck 减去 known_ids, 按 counts 顺序切分; 不够返回 None, 多余截断。"""
    rem = Counter(full_deck)
    rem.subtract(Counter(known_ids))
    if any(v < 0 for v in rem.values()):
        return None
    pool = [cid for cid, k in rem.items() for _ in range(k)]
    if len(pool) < sum(counts):
        return None
    out, off = [], 0
    for c in counts:
        out.append(pool[off:off + c])
        off += c
    return out


def _build_hidden(obs, my_idx, opp_deck=None):
    cur = obs['current']
    me, opp = cur['players'][my_idx], cur['players'][1 - my_idx]
    od = opp_deck if opp_deck is not None else OPP_DECK
    if od is None:
        return None
    # 对手 active 盖牌 → 放弃本次 beam (无法可靠预测)
    op_act = opp.get('active') or []
    if len(op_act) > 0 and op_act[0] is None:
        return None
    my_hand = [c['id'] for c in (me.get('hand') or [])
               if isinstance(c, dict) and c.get('id')]
    my_known = my_hand + _zone_ids(me)
    n_prize = len(me.get('prize') or [])
    mine = _hidden_split(DECK, my_known, [n_prize, me.get('deckCount', 0)])
    if mine is None:
        return None
    your_prize, your_deck = mine
    opps = _hidden_split(od, _zone_ids(opp),
                         [opp.get('handCount', 0), len(opp.get('prize') or []),
                          opp.get('deckCount', 0)])
    if opps is None:
        return None
    opp_hand, opp_prize, opp_deck = opps
    return your_deck, your_prize, opp_deck, opp_prize, opp_hand, []


# ---------- rollout 计分 ----------
def _score(res, my_idx):
    if res == my_idx:
        return 1.0
    if res in (2, -1, None):
        return 0.5
    return 0.0


def _valid_pick(pick, sel):
    opts = sel.get('option') or []
    n = len(opts)
    lo = sel.get('minCount')
    lo = 1 if lo is None else lo
    hi = sel.get('maxCount')
    hi = n if hi is None else min(hi, n)
    ok = (isinstance(pick, list) and pick
          and all(isinstance(i, int) and 0 <= i < n for i in pick))
    if ok and lo <= len(pick) <= hi:
        return pick
    if ok and len(pick) > hi:
        return pick[:hi]
    return list(range(min(lo, n)))  # 兜底: first


def _rollout(st, my_idx, deadline):
    steps = 0
    while steps < BEAM_MAX_STEPS:
        o = st['observation']
        cur = o.get('current') or {}
        res = cur.get('result', -1)
        if res is not None and res >= 0:
            _stats['rollouts'] += 1
            return _score(res, my_idx)
        sel = o.get('select')
        if not sel or not sel.get('option'):
            _stats['rollouts'] += 1
            return 0.5
        yi = cur.get('yourIndex', 0)
        try:
            pick = _rule_roll[yi].agent(o)
        except Exception:
            pick = None
        pick = _valid_pick(pick, sel)
        try:
            st = _sstep(st['searchId'], pick)
        except _Ended:
            res = (st['observation'].get('current') or {}).get('result', -1)
            _stats['rollouts'] += 1
            return _score(res, my_idx)
        steps += 1
        if time.perf_counter() > deadline:
            _stats['rollouts'] += 1
            return 0.5
    _stats['rollouts'] += 1
    return 0.5


# ---------- 候选择优 ----------
def _beam_pick(obs, sel, my_idx):
    cur = obs['current']
    opts = sel.get('option') or []
    n = len(opts)
    rule_pick = _rule_self.agent(obs)
    rule_pick = rule_pick if isinstance(rule_pick, list) else []
    cands = []
    for i in rule_pick:  # 规则自选永远第一优先 (同分时胜出 = 无退化兜底)
        if isinstance(i, int) and 0 <= i < n and i not in cands:
            cands.append(i)
    for i, o in enumerate(opts):  # 全部攻击选项
        if isinstance(o, dict) and o.get('type') == 13 and i not in cands:
            cands.append(i)
    for i, o in enumerate(opts):  # END
        if isinstance(o, dict) and o.get('type') == 14 and i not in cands:
            cands.append(i)
    for i in range(n):  # 其余补齐
        if len(cands) >= BEAM_MAX_CAND:
            break
        if i not in cands:
            cands.append(i)
    cands = cands[:BEAM_MAX_CAND]

    sbi = obs.get('search_begin_input')
    if not sbi:
        _stats['fb_no_sbi'] += 1
        return None
    # M3: auto 模式先识别对手牌组; 弃权 → 镜像假设 (M2 行为), 误识 → 负余量自动回退
    opp_deck = OPP_DECK
    deck_kind = 'fixed'
    if AUTO_OPP:
        try:
            r = _recog.classify_obs(obs, my_idx, margin=RECOG_MARGIN) if _recog else None
        except Exception:
            r = None
        if r is not None:
            _stats['recog'][r[0]] += 1
            opp_deck = r[1]
            deck_kind = 'recog:' + r[0]
        else:
            _stats['recog_none'] += 1
            opp_deck = DECK
            deck_kind = 'mirror_abstain'
    hid = _build_hidden(obs, my_idx, opp_deck)
    if hid is None:
        _stats['fb_no_hidden'] += 1
        return None
    root = _sbegin(sbi, *hid)
    best_i, best_s = None, -1.0
    deadline = time.perf_counter() + BEAM_TIME_MS / 1000.0
    try:
        for ci in cands:
            if time.perf_counter() > deadline:
                break
            try:
                child = _sstep(root['searchId'], [ci])
            except _Ended:
                s = 0.5
            else:
                s = _rollout(child, my_idx, deadline)
            if s > best_s:
                best_s, best_i = s, ci
    finally:
        lib.SearchEnd(_ptr())
    if best_i is None:
        _stats['fb_no_cand'] += 1
    else:
        _stats['beam_deck'][deck_kind] += 1
    return best_i


def _triggered(obs, sel):
    if not BEAM_ENABLE or not sel or not sel.get('option'):
        return False
    if sel.get('context') != 0:
        return False
    cur = obs.get('current') or {}
    if (cur.get('turn') or 0) < BEAM_MIN_TURN:
        return False
    return any(isinstance(o, dict) and o.get('type') == 13
               for o in sel['option'])


def agent(obs, config=None):
    sel = obs.get('select')
    if sel is None:
        return DECK
    if _triggered(obs, sel):
        t0 = time.perf_counter()
        try:
            bi = _beam_pick(obs, sel, (obs.get('current') or {}).get('yourIndex', 0))
        except Exception:
            bi = None
            _stats['abort'] += 1
        _stats['ms'] += (time.perf_counter() - t0) * 1000
        if bi is not None:
            _stats['beam'] += 1
            return [bi]
        _stats['fallback'] += 1
    return _rule_self.agent(obs)
