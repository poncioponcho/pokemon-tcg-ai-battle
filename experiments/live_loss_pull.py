"""live_loss_pull.py — 拉 live episode replay (ledger #131 管线 Tier1; A 补丁 A2 参数化)

用法:
  configA 默认 (行为逐字节不变): /opt/homebrew/bin/python3 experiments/live_loss_pull.py
  探针归因: /opt/homebrew/bin/python3 experiments/live_loss_pull.py \
      --rows experiments/runs/live_episodes_probe.json \
      --out experiments/runs/live_replays_probe [--limit 2 冒烟] [--include-wins 含胜局]
输入: --rows 指定的 episode 清单 (默认 experiments/runs/live_episodes_configA.json)
产物: <out>/*-replay.json (默认 experiments/runs/live_replays)
纪律: 5s 基础限速 (社区惯例); 已存在跳过 (断点续拉); 默认只拉败局 (configA 原行为)
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

PROJ = Path('/Users/seyonmacbook/Desktop/Pokemon_TCG_AI_Battle_Challenge')

ap = argparse.ArgumentParser()
ap.add_argument('--rows', default='experiments/runs/live_episodes_configA.json')
ap.add_argument('--out', default='experiments/runs/live_replays')
ap.add_argument('--limit', type=int, default=0, help='0=全量; >0 只拉前 N 局 (冒烟用)')
ap.add_argument('--include-wins', action='store_true',
                help='默认只拉败局 (configA 原行为); 加此旗标胜局也拉 (探针归因要全场次)')
args = ap.parse_args()

ROWS = json.load(open(PROJ / args.rows))
OUT = PROJ / args.out
OUT.mkdir(exist_ok=True)
DELAY = 5.0

targets = [r for r in ROWS if r['reward'] == -1]
if args.include_wins:
    targets = [r for r in ROWS if r['reward'] in (-1, 1)]
if args.limit:
    targets = targets[:args.limit]
print(f'[pull] {len(targets)} 局待拉 (rows={args.rows} out={args.out})', flush=True)
ok = fail = skip = 0
for i, r in enumerate(targets):
    eid = r['id']
    if list(OUT.glob(f'*{eid}*replay*.json')):
        skip += 1
        continue
    rc = subprocess.run(
        ['/opt/homebrew/bin/kaggle', 'competitions', 'replay', str(eid), '-p', str(OUT)],
        capture_output=True, text=True, timeout=120)
    if rc.returncode == 0 and list(OUT.glob(f'*{eid}*replay*.json')):
        ok += 1
        print(f'[pull] {i+1}/{len(targets)} ep{eid} ok', flush=True)
    else:
        fail += 1
        print(f'[pull] {i+1}/{len(targets)} ep{eid} FAIL rc={rc.returncode} {rc.stderr[-120:]}', flush=True)
    time.sleep(DELAY)
print(f'[pull] 完成 ok={ok} skip={skip} fail={fail}', flush=True)
