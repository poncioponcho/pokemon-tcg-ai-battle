"""long_train_probe.py — BC 保真解剖 Phase2a：长训练探针 v3（2026-08-13，设备常驻）

v2 瓶颈实测：float32 CPU 转换+逐批 250MB 传输 = 85s/epoch。v3：全部训练数据
一次性以 uint8 驻留 MPS（~2.4GB 统一内存），批内设备上索引+转 float，零逐批传输。
判据不变：60 epoch 内 train top1 爬 0.65+ → 训练预算不足；平台 0.55-0.60 → 模型类/特征天花板。
产物：experiments/runs/long_train_probe.json + .log
"""
import json
import sys
import time
from pathlib import Path

import numpy as np
import torch

ROOT = Path('/Users/seyonmacbook/Desktop/Pokemon_TCG_AI_Battle_Challenge')
DS = ROOT / 'inference/dataset'
sys.path.insert(0, str(DS))
import model_v2  # noqa: E402
import train_bc  # noqa: E402

OUT = ROOT / 'experiments/runs/long_train_probe.json'
EPOCHS, BS = 60, 8192
TRAIN_N, FIXED_EVAL_N = 300_000, 40_000
t0 = time.time()

mm = {n: np.load(DS / f'data/{n}.npy', mmap_mode='r') for n in
      ('states_u8', 'scalars', 'opts_u8', 'labels', 'masks')}
ep_ids = np.asarray(np.load(DS / 'data/episode_ids.npy', mmap_mode='r')).astype(str)
assign = {}
for line in (DS / 'splits/episode_splits.jsonl').read_text().splitlines():
    row = json.loads(line)
    assign[str(row['episode_id'])] = row['split']
canary_ids = set(json.loads((DS / 'splits/rolling_canary.json').read_text())['episode_ids'])
fixed_ids = {e for e, s in assign.items() if s == 'fixed_test'}
train_ids = {e for e, s in assign.items() if s == 'train'} - canary_ids
train_idx = np.where(np.isin(ep_ids, list(train_ids)))[0]
fixed_idx = np.where(np.isin(ep_ids, list(fixed_ids)))[0]
rng = np.random.default_rng(7)
train_sub = np.sort(rng.choice(train_idx, min(TRAIN_N, len(train_idx)), replace=False))
fixed_sub = np.sort(rng.choice(fixed_idx, min(FIXED_EVAL_N, len(fixed_idx)), replace=False))

device = 'mps' if torch.backends.mps.is_available() else 'cpu'
print(f'[{time.time()-t0:.0f}s] to device: train {len(train_sub)}, fixed_eval {len(fixed_sub)}', flush=True)
dtrain = {n: torch.from_numpy(np.asarray(mm[n][train_sub])).to(device) for n in mm}
dfixed = {n: torch.from_numpy(np.asarray(mm[n][fixed_sub])).to(device) for n in mm}
print(f'[{time.time()-t0:.0f}s] device-resident ready', flush=True)

torch.manual_seed(42)
np.random.seed(42)
model = model_v2.PolicyTeacher(st_dim=4400, sc_dim=90, o_dim=52, k=64).to(device)
opt = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-4)
print(f'device: {device} params={sum(p.numel() for p in model.parameters()) / 1e6:.2f}M', flush=True)


def batch(d, pos):
    st = d['states_u8'][pos].float()
    sc = d['scalars'][pos].float()
    op = d['opts_u8'][pos].float()
    return st, sc, op, d['labels'][pos], d['masks'][pos]


@torch.no_grad()
def top1(d, n_rows, model):
    model.eval()
    hit = 0
    for s in range(0, n_rows, BS):
        pos = torch.arange(s, min(s + BS, n_rows), device=device)
        st, sc, op, lb, mk = batch(d, pos)
        top = model(st, sc, op, mk).argmax(1)
        hit += (lb[torch.arange(len(top), device=device), top] == 1).sum().item()
    return hit / n_rows


history = []
n_tr = len(train_sub)
for ep in range(1, EPOCHS + 1):
    model.train()
    perm = torch.randperm(n_tr, device=device)
    tot, cnt = 0.0, 0
    for s in range(0, n_tr, BS):
        st, sc, op, lb, mk = batch(dtrain, perm[s:s + BS])
        loss = train_bc.ce_loss(model(st, sc, op, mk), lb, mk)
        opt.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0)
        opt.step()
        tot += loss.item()
        cnt += 1
    if ep % 5 == 0 or ep == 1:
        row = {'epoch': ep, 'loss': round(tot / max(cnt, 1), 4),
               'train_top1': round(top1(dtrain, 30_000, model), 4),
               'fixed_top1': round(top1(dfixed, len(fixed_sub), model), 4)}
        history.append(row)
        print(f'[{time.time() - t0:.0f}s] {row}', flush=True)

OUT.write_text(json.dumps({'epochs': EPOCHS, 'train_n': n_tr,
                           'history': history, 'elapsed_s': round(time.time() - t0, 1)}, indent=1))
print(f'→ {OUT}')
