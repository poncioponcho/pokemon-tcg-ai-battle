"""probe_pull_55468450.py — 探针 ref 55468450 replay 断点续拉 (#132 管线, 8/15 收官判读用)

复用 top_pilot_pull.py 逻辑: list_submission_episodes + kaggle competitions replay,
5s 基础限速, 已存在跳过。产物: experiments/runs/live_replays_probe/episode-<eid>-replay.json
"""
import subprocess
import sys
import time
from pathlib import Path

PROJ = Path('/Users/seyonmacbook/Desktop/Pokemon_TCG_AI_Battle_Challenge')
sys.path.insert(0, str(PROJ))
from submit import get_client  # noqa: E402
from kagglesdk.competitions.types.competition_api_service import (  # noqa: E402
    ApiListSubmissionEpisodesRequest)

REF = 55468450
OUT = PROJ / 'experiments/runs/live_replays_probe'
DELAY = 5.0


def main():
    api = get_client().competitions.competition_api_client
    req = ApiListSubmissionEpisodesRequest()
    req.submission_id = REF
    eps = list(api.list_submission_episodes(req).episodes)
    public = [e for e in eps if str(e.type).endswith('EPISODE_TYPE_PUBLIC')]
    print(f'[probe-pull] ref={REF} total={len(eps)} public={len(public)}', flush=True)
    OUT.mkdir(exist_ok=True)
    ok = fail = skip = 0
    for i, e in enumerate(public):
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
        print(f'  [probe-pull] {i+1}/{len(public)} ok={ok} skip={skip} fail={fail}',
              flush=True)
        time.sleep(DELAY)
    print(f'[probe-pull] done ok={ok} skip={skip} fail={fail}', flush=True)


if __name__ == '__main__':
    main()
