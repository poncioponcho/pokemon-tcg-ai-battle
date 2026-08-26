"""multimodal_probe.py — BC 保真解剖 Phase1 实验①：人类决策的多模态上限（2026-08-13）

问题：克隆 top-500 真人 top1≈0.54 vs 克隆规则 self-play top1≈0.77 的 23pp 差，
多少是不可约的「同局面多手好棋」（客观形式问题）vs 可修的「模型/特征不足」。

方法：对 1.8M 决策帧做 128-bit 随机投影哈希分组（state bags + context + 选项集签名），
组内 label 众数占比 = 人类一致性；按回合桶 / 数据源（LB真人 vs self-play规则）/ 队内 vs 跨队分层。
self-play 组是内置对照（规则 agent 近确定性 → 一致性应≈1.0，否则哈希太粗或 agent 有 RNG）。

产物：experiments/runs/multimodal_probe.json + stdout 摘要
"""
import csv
import json
import time
from pathlib import Path

import numpy as np

ROOT = Path('/Users/seyonmacbook/Desktop/Pokemon_TCG_AI_Battle_Challenge')
DS = ROOT / 'inference/dataset'
OUT = ROOT / 'experiments/runs/multimodal_probe.json'
CHUNK = 25_000
MASK = (1 << 61) - 1

t0 = time.time()
meta_json = json.loads((DS / 'data/meta.json').read_text())
N = meta_json['n_decisions']
st = np.load(DS / 'data/states_u8.npy', mmap_mode='r')        # N×4400 u8
opts = np.load(DS / 'data/opts_u8.npy', mmap_mode='r')        # N×64×52 u8
labels = np.load(DS / 'data/labels.npy', mmap_mode='r')       # N×64 u8
masks = np.load(DS / 'data/masks.npy', mmap_mode='r')         # N×64 u8
meta = np.load(DS / 'data/meta.npy', mmap_mode='r')           # N×9
ep_ids = np.load(DS / 'data/episode_ids.npy', mmap_mode='r')  # N×U

rng = np.random.default_rng(20260813)
R1 = rng.integers(1, MASK, size=st.shape[1], dtype=np.uint64)
R2 = rng.integers(1, MASK, size=st.shape[1], dtype=np.uint64)
RO = rng.integers(1, MASK, size=64, dtype=np.uint64)

sig1 = np.empty(N, np.uint64)
sig2 = np.empty(N, np.uint64)
osig = np.empty(N, np.uint64)
lsig = np.empty(N, np.uint64)
for s in range(0, N, CHUNK):
    e = min(s + CHUNK, N)
    a = np.asarray(st[s:e], dtype=np.uint64)
    sig1[s:e] = (a * R1).sum(1) & MASK
    sig2[s:e] = (a * R2).sum(1) & MASK
    card = np.asarray(opts[s:e, :, 51], dtype=np.uint64)      # cardId 列（数值末位，index 51）
    mk = np.asarray(masks[s:e], dtype=np.uint64)
    card = np.where(mk == 1, card, np.uint64(255))
    card.sort(1)
    osig[s:e] = (card * RO).sum(1) & MASK
    lb = np.packbits(np.asarray(labels[s:e]), axis=1)         # N×8 bytes
    lsig[s:e] = lb.view(np.uint64).reshape(-1)
print(f'[{time.time()-t0:.0f}s] hashed {N} rows')

turn = np.asarray(meta[:, 3]).astype(np.int32)
ctx = np.asarray(meta[:, 4]).astype(np.int32)
nopts = np.asarray(meta[:, 5]).astype(np.int32)
team = np.asarray(meta[:, 7]).astype(np.int64)

# LB 真人局 = manifest.csv 里的 episode；其余 = self-play
lb_eps = set()
with (DS / 'manifest.csv').open(newline='', encoding='utf-8') as fh:
    for row in csv.DictReader(fh):
        lb_eps.add(str(row['episode_id']))
is_lb = np.fromiter((str(x) in lb_eps for x in ep_ids), dtype=bool, count=N)
print(f'[{time.time()-t0:.0f}s] LB rows={is_lb.sum()} / selfplay rows={(~is_lb).sum()}')

key = np.zeros(N, dtype=[('a', np.uint64), ('b', np.uint64), ('c', np.int32), ('d', np.int32), ('e', np.uint64)])
key['a'], key['b'], key['c'], key['d'], key['e'] = sig1, sig2, ctx, nopts, osig
uniq, inv, counts = np.unique(key, return_inverse=True, return_counts=True)
print(f'[{time.time()-t0:.0f}s] groups={len(uniq)} (rows in ≥2: {counts[inv][counts[inv] >= 2].size / N:.3%})')

# 组内众数 label 占比（向量化：按 (inv, lsig) 排序 + run-length）
order = np.lexsort((lsig, inv))
inv_s, lsig_s = inv[order], lsig[order]
same_gid = np.r_[True, inv_s[1:] != inv_s[:-1]]
same_lab = np.r_[True, lsig_s[1:] != lsig_s[:-1]]
run_start = np.where(same_gid | same_lab)[0]
gid_of_run = inv_s[run_start]
run_len = np.diff(np.r_[run_start, N])
best = np.zeros(len(uniq), np.int64)
np.maximum.at(best, gid_of_run, run_len)
agree_per_row_group = best / counts                                # 每组的众数占比
row_agree = agree_per_row_group[inv]                               # 展开到行

def strat(mask_rows, name, min_turn=None):
    m = mask_rows & (counts[inv] >= 2)
    if min_turn is not None:
        lo, hi = min_turn
        m &= (turn >= lo) & (turn <= hi)
    n_rows = int(m.sum())
    if n_rows == 0:
        return {'name': name, 'rows': 0}
    w = counts[inv][m].astype(np.float64)
    return {'name': name, 'rows': n_rows,
            'weighted_agreement': round(float((row_agree[m] * w).sum() / w.sum()), 4),
            'groups': int(np.unique(inv[m]).size)}

report = {'n_decisions': N, 'n_groups': int(len(uniq)), 'elapsed_s': None, 'strata': []}
report['strata'].append(strat(np.ones(N, bool), 'ALL_dup_rows'))
report['strata'].append(strat(is_lb, 'LB_human_dup'))
report['strata'].append(strat(~is_lb, 'selfplay_rule_dup_CONTROL'))
for lo, hi, nm in ((0, 2, 't0-2'), (3, 10, 't3-10'), (11, 999, 't11+')):
    report['strata'].append(strat(is_lb, f'LB_{nm}', (lo, hi)))
# 队内 vs 跨队：组内全部同队 → within；混合 → cross（向量化：组内 team min==max）
tmin = np.full(len(uniq), np.iinfo(np.int64).max)
tmax = np.full(len(uniq), np.iinfo(np.int64).min)
np.minimum.at(tmin, inv, team)
np.maximum.at(tmax, inv, team)
within_team_gid = set(np.where((tmin == tmax) & (counts >= 2))[0].tolist())
wt = np.fromiter((g in within_team_gid for g in inv), dtype=bool, count=N)
report['strata'].append(strat(is_lb & wt, 'LB_within_team_dup'))
report['strata'].append(strat(is_lb & ~wt, 'LB_cross_team_dup'))
report['elapsed_s'] = round(time.time() - t0, 1)

OUT.write_text(json.dumps(report, ensure_ascii=False, indent=1))
print(json.dumps(report, ensure_ascii=False, indent=1))
print(f'→ {OUT}')
