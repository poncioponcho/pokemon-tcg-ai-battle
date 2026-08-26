#!/usr/bin/env python3
"""验证 2026-08-07 重抽张量的 deck 归属修复是否真正生效。

两项检查：
A. 对手牌组槽位 st[4D:5D] 必须全零（旧数据 49% 行非零 = 泄漏）
B. "my deck" 槽位 st[3D:4D] 必须等于 perspective 玩家自己的牌组计数，
   且不等于对手牌组（旧 bug：玩家0 槽位填了对手牌组）
"""
import json
import subprocess
import sys

import numpy as np

DATA = 'inference/dataset/data'
ARCHIVE = 'inference/leaderboard_replay/archive/all_replays.jsonl.zst'
VOCAB_PATH = 'inference/dataset/card_vocab_v1.json'

vocab = json.load(open(VOCAB_PATH))
CARD_DIM = int(vocab['size'])
ID2IDX = {int(cid): int(idx) for cid, idx in vocab['id_to_index'].items()}
D = CARD_DIM
print(f'CARD_DIM={CARD_DIM}')

states = np.load(f'{DATA}/states_u8.npy', mmap_mode='r')
ep_ids = np.load(f'{DATA}/episode_ids.npy', mmap_mode='r')
meta = np.load(f'{DATA}/meta.npy', mmap_mode='r')
n = states.shape[0]
print(f'rows={n}')

# ---- A. 对手牌组槽位泄漏检查（20 万行抽样） ----
idx = np.arange(0, n, max(1, n // 200_000))
opp_slot = np.asarray(states[idx, 4 * D:5 * D])
nonzero_rows = int((opp_slot.max(axis=1) > 0).sum())
print(f'[A] 对手牌组槽位: 抽样 {len(idx)} 行, 非零行 {nonzero_rows}'
      f' (旧数据约 49% 非零) -> {"PASS" if nonzero_rows == 0 else "FAIL"}')

# ---- B. deck 归属抽查 ----
# 先建 episode -> 行号索引（一次扫描，避免每局全表扫）
print('构建 episode 索引...')
ep_to_rows = {}
for i, e in enumerate(np.asarray(ep_ids)):
    ep_to_rows.setdefault(str(e), []).append(i)
print(f'索引完成: {len(ep_to_rows)} 局')

# 从存档流式读取前若干局，按修复后的规则提取双方牌组
deck_by_ep = {}
proc = subprocess.Popen(['zstd', '-dc', ARCHIVE], stdout=subprocess.PIPE,
                        text=True, bufsize=1024 * 1024)
assert proc.stdout is not None
for line in proc.stdout:
    if len(deck_by_ep) >= 120:
        break
    line = line.strip()
    if not line:
        continue
    try:
        row = json.loads(line)
    except json.JSONDecodeError:
        continue
    ep = str(row.get('episode_id', ''))
    if not ep:
        continue
    payload = row.get('raw_json', row)
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            continue
    if not isinstance(payload, dict):
        continue
    decks = [None, None]
    for step in payload.get('steps', []):
        if not isinstance(step, list):
            continue
        for ag_idx, ag in enumerate(step):
            act = ag.get('action') if isinstance(ag, dict) else None
            if (ag_idx < 2 and isinstance(act, list) and len(act) == 60
                    and all(isinstance(x, int) for x in act)
                    and decks[ag_idx] is None):
                decks[ag_idx] = act
    if decks[0] and decks[1]:
        deck_by_ep[ep] = decks
proc.kill()

mirror = sum(1 for d in deck_by_ep.values() if sorted(d[0]) == sorted(d[1]))
print(f'[B] 存档读取 {len(deck_by_ep)} 局 (其中镜像牌组 {mirror} 局)')

def deck_cnt(deck):
    return np.bincount([ID2IDX[c] for c in deck if c in ID2IDX],
                       minlength=D).astype(np.uint8)

ep_arr = None  # 不再全表扫
checked = own_ok = opp_hit = no_rows = 0
fails = []
for ep, decks in deck_by_ep.items():
    if sorted(decks[0]) == sorted(decks[1]):
        continue  # 镜像局无法区分归属，跳过
    rows = ep_to_rows.get(ep)
    if not rows:
        no_rows += 1
        continue
    own_cnts = [deck_cnt(decks[0]), deck_cnt(decks[1])]
    for r in rows[:20]:
        yi = int(meta[r, 1])
        slot = np.asarray(states[r, 3 * D:4 * D])
        checked += 1
        if np.array_equal(slot, own_cnts[yi]):
            own_ok += 1
        elif np.array_equal(slot, own_cnts[1 - yi]):
            opp_hit += 1
            if len(fails) < 3:
                fails.append((ep, int(r), yi, 'opponent-deck'))
        else:
            if len(fails) < 3:
                fails.append((ep, int(r), yi, 'neither'))

print(f'[B] 抽查 {checked} 决策行 (无张量行的局 {no_rows}): '
      f'own-deck 匹配 {own_ok}, 对手牌组 {opp_hit}, 其他不符 {checked - own_ok - opp_hit}')
for f in fails:
    print('   FAIL 样例:', f)
verdict = nonzero_rows == 0 and checked > 0 and own_ok == checked
print('总判定:', 'PASS' if verdict else 'FAIL')
sys.exit(0 if verdict else 1)
