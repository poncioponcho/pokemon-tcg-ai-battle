"""top_pilot_pull.py — 拉顶尖 pilot 最近 N 局 replay (top_pilot_diff_plan Step2 采样)

用法:
  /opt/homebrew/bin/python3 experiments/top_pilot_pull.py --player SixthSense --n 5   # 冒烟
  /opt/homebrew/bin/python3 experiments/top_pilot_pull.py                              # 全量 3 人 × 25
产物: experiments/runs/top_pilot_replays/episode-<eid>-replay.json
纪律: 5s 基础限速 (社区惯例); 已存在跳过 (断点续拉)
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path

PROJ = Path('/Users/seyonmacbook/Desktop/Pokemon_TCG_AI_Battle_Challenge')
sys.path.insert(0, str(PROJ))
from submit import get_client  # noqa: E402
from kagglesdk.competitions.types.competition_api_service import (  # noqa: E402
    ApiListSubmissionEpisodesRequest)

TARGETS = {'SixthSense': 55439076, 'Dipam': 55449184, 'MiwaHaruki': 55449976}
OUT = PROJ / 'experiments/runs/top_pilot_replays'
DELAY = 5.0


def list_eps(sub_id):
    api = get_client().competitions.competition_api_client
    req = ApiListSubmissionEpisodesRequest()
    req.submission_id = sub_id
    return list(api.list_submission_episodes(req).episodes)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--player', default=None, choices=list(TARGETS))
    ap.add_argument('--n', type=int, default=25)
    args = ap.parse_args()
    OUT.mkdir(exist_ok=True)
    targets = {args.player: TARGETS[args.player]} if args.player else TARGETS
    for name, sid in targets.items():
        eps = list_eps(sid)[:args.n]
        print(f'[{name}] sub {sid}: 可得 {len(eps)} eps, 目标 {args.n}', flush=True)
        ok = fail = skip = 0
        for i, e in enumerate(eps):
            eid = e.id
            if list(OUT.glob(f'*{eid}*replay*.json')):
                skip += 1
                continue
            rc = subprocess.run(
                ['/opt/homebrew/bin/kaggle', 'competitions', 'replay',
                 str(eid), '-p', str(OUT)],
                capture_output=True, text=True, timeout=120)
            if rc.returncode == 0 and list(OUT.glob(f'*{eid}*replay*.json')):
                ok += 1
            else:
                fail += 1
                print(f'  [fail] ep{eid}: {(rc.stderr or rc.stdout)[-150:]}', flush=True)
            print(f'  [{name}] {i+1}/{len(eps)} ok={ok} skip={skip} fail={fail}',
                  flush=True)
            time.sleep(DELAY)
        print(f'[{name}] done ok={ok} skip={skip} fail={fail}', flush=True)


if __name__ == '__main__':
    main()
