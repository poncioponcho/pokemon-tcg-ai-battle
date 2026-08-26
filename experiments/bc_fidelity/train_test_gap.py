"""train_test_gap.py — BC 保真解剖 Phase1 实验②：train/test top1 差距（2026-08-13）

判别：人类克隆 top1≈0.54 是欠拟合（train≈test）还是过拟合（train>>test）。
v1 teacher（LB 真人 4432 局训练）在 LB-train / LB-fixed-test / rolling-canary 三 slice 上各测 top1。
v3 teacher（self-play 训练）在 self-play / LB-fixed-test 上测，作对照与跨分布参考。
多模态探针已证真人一致性≈规则一致性（0.875 vs 0.884）→ 天花板远高于 0.54，
故 train/test 差距直接路由 Phase2：欠拟合→表示/容量/训练；过拟合→数据规模/正则。

产物：experiments/runs/train_test_gap.json + stdout
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

OUT = ROOT / 'experiments/runs/train_test_gap.json'
TRAIN_SAMPLE = 200_000
t0 = time.time()

arrays = {}
for name in ('states_u8', 'scalars', 'opts_u8', 'labels', 'masks'):
    arrays[name] = np.load(DS / f'data/{name}.npy', mmap_mode='r')
meta_arr = np.load(DS / 'data/meta.npy', mmap_mode='r')
meta = {'ctx': np.asarray(meta_arr[:, 4])}
ep_ids = np.asarray(np.load(DS / 'data/episode_ids.npy', mmap_mode='r')).astype(str)
N = len(ep_ids)

# split 归属（08-04 冻结的 LB 4432 局才有 assignment）
assign = {}
for line in (DS / 'splits/episode_splits.jsonl').read_text().splitlines():
    row = json.loads(line)
    assign[str(row['episode_id'])] = row['split']
canary_ids = set(json.loads((DS / 'splits/rolling_canary.json').read_text())['episode_ids'])
fixed_ids = {e for e, s in assign.items() if s == 'fixed_test'}
train_ids = {e for e, s in assign.items() if s == 'train'} - canary_ids

import csv
lb_eps = set()
with (DS / 'manifest.csv').open(newline='', encoding='utf-8') as fh:
    for row in csv.DictReader(fh):
        lb_eps.add(str(row['episode_id']))

is_lb = np.fromiter((e in lb_eps for e in ep_ids), dtype=bool, count=N)
train_idx = np.where(np.isin(ep_ids, list(train_ids)))[0]
fixed_idx = np.where(np.isin(ep_ids, list(fixed_ids)))[0]
canary_idx = np.where(np.isin(ep_ids, list(canary_ids)))[0]
selfplay_idx = np.where(~is_lb)[0]
rng = np.random.default_rng(7)
train_idx = rng.choice(train_idx, min(TRAIN_SAMPLE, len(train_idx)), replace=False)
selfplay_idx = rng.choice(selfplay_idx, min(TRAIN_SAMPLE, len(selfplay_idx)), replace=False)
print(f'[{time.time()-t0:.0f}s] slices: lb_train={len(train_idx)} fixed={len(fixed_idx)} '
      f'canary={len(canary_idx)} selfplay={len(selfplay_idx)}', flush=True)

device = 'mps' if torch.backends.mps.is_available() else 'cpu'
print(f'device: {device}', flush=True)

def load_teacher(path):
    m = model_v2.PolicyTeacher(st_dim=4400, sc_dim=90, o_dim=52, k=64)
    m.load_state_dict(torch.load(path, map_location='cpu', weights_only=True))
    return m.to(device).eval()

report = {'device': device, 'elapsed_s': None}
for tag, path in (('v1_LBtrained', ROOT / 'reports/kerr_selfplay/ckpt/teacher_best.pt'),
                  ('v3_selfplay', ROOT / 'reports/kerr_selfplay_v3/ckpt/teacher_best.pt')):
    m = load_teacher(path)
    entry = {}
    for sname, idx in (('lb_train', train_idx), ('lb_fixed_test', fixed_idx),
                       ('canary', canary_idx), ('selfplay', selfplay_idx)):
        if len(idx) == 0:
            continue
        r, ctx_hit, ctx_n = train_bc.evaluate(m, arrays, idx, meta, device)
        entry[sname] = {'top1': round(r['top1'], 4), 'recall': round(r['recall'], 4), 'n': len(idx)}
        if sname == 'lb_fixed_test':
            entry['per_ctx_top1'] = {int(c): round(ctx_hit[c] / ctx_n[c], 3)
                                     for c in sorted(ctx_n) if ctx_n[c] >= 200}
        print(f'[{time.time()-t0:.0f}s] {tag} {sname}: {entry[sname]}', flush=True)
    report[tag] = entry

report['elapsed_s'] = round(time.time() - t0, 1)
OUT.write_text(json.dumps(report, ensure_ascii=False, indent=1))
print(f'→ {OUT}')
