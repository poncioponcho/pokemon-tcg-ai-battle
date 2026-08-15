"""probe_wr_watch.py — 当前 exact-v22 提交 WR 轨迹采样器。

每次调用: 拉 episode 清单 → 刷新 live_episodes_probe.json → 追加一行轨迹到
experiments/runs/probe_wr_trajectory.jsonl {status, ts, ts_iso, eps, scored, W, L, WR}。

自灭闸: 2026-08-17 07:30 (Asia/Shanghai) 之后调用 → 返回 expired, 不碰 API。
默认 ref 与 live_episodes_probe.py 保持同一来源，避免主探针已切 exact-v22
而轨迹器仍静默采样旧 recovery 件。

纪律: 只读 API (lb_watch 同款); 瞬读不记账 (#98) —— 轨迹只是原始数据流,
  判读走 reports/2026-08-15_会师判读包.md 决策树, 本脚本不下结论。

用法:
  /opt/homebrew/bin/python3 experiments/probe_wr_watch.py
  /opt/homebrew/bin/python3 experiments/probe_wr_watch.py --ref 55495594 \
      --trajectory experiments/runs/grimmsnarl_wr.jsonl \
      --probe-json experiments/runs/live_episodes_grimmsnarl.json
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJ = Path('/Users/seyonmacbook/Desktop/Pokemon_TCG_AI_Battle_Challenge')
sys.path.insert(0, str(PROJ / 'experiments'))
from live_episodes_probe import OUT as PROBE_JSON  # noqa: E402
from live_episodes_probe import PROBE_REF, fetch_episodes, summarize  # noqa: E402
sys.path.insert(0, str(PROJ))
from scripts.safe_json_output import reserve_json_output  # noqa: E402

TRAJ = PROJ / 'experiments/runs/probe_wr_trajectory.jsonl'
CST = timezone(timedelta(hours=8))
ACTIVE_REF = PROBE_REF
CUTOFF = datetime(2026, 8, 17, 7, 30, tzinfo=CST)


def sample_once(now=None, ref=None, probe_json=None, trajectory=None,
                cutoff=CUTOFF):
    """采样一次并追加轨迹; 过自灭闸则只返回 expired 标记。"""
    now = now or datetime.now(CST)
    ref = ACTIVE_REF if ref is None else int(ref)
    if now >= cutoff:
        return {'status': 'expired', 'ts_iso': now.isoformat(timespec='seconds'),
                'note': f'已过 {cutoff.isoformat()} 自灭闸, 未碰 API; 截止收官接管'}
    probe_json = Path(probe_json) if probe_json else PROBE_JSON
    trajectory = Path(trajectory) if trajectory else TRAJ
    if not probe_json.is_absolute():
        probe_json = PROJ / probe_json
    if not trajectory.is_absolute():
        trajectory = PROJ / trajectory
    probe_json.parent.mkdir(parents=True, exist_ok=True)
    trajectory.parent.mkdir(parents=True, exist_ok=True)
    rows = fetch_episodes(ref)
    reserve_json_output(probe_json, overwrite=True).write(rows)
    n, ns, w, losses, wr = summarize(rows)
    public_n = sum(
        1 for row in rows
        if row.get('is_public', row.get('opp_sub') is not None)
    )
    ev = {'status': 'sampled', 'ts': time.time(), 'ts_iso': now.isoformat(timespec='seconds'),
          'ref': int(ref), 'eps': n, 'public': public_n,
          'validation': n - public_n, 'scored': ns, 'W': w, 'L': losses,
          'WR': round(wr, 4) if wr is not None else None}
    # Keep each JSONL event in one O_APPEND write so concurrent samplers cannot
    # interleave partial text records.  The snapshot JSON above remains guarded
    # by the stronger exclusive-reservation + atomic-replace protocol.
    payload = (json.dumps(ev, ensure_ascii=False) + '\n').encode('utf-8')
    fd = os.open(trajectory, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        os.write(fd, payload)
    finally:
        os.close(fd)
    return ev


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--ref', type=int, default=ACTIVE_REF)
    ap.add_argument('--probe-json', default=os.environ.get(
        'PTCG_PROBE_OUT', str(PROBE_JSON)))
    ap.add_argument('--trajectory', default=os.environ.get(
        'PTCG_PROBE_TRAJECTORY', str(TRAJ)))
    ap.add_argument('--cutoff', default=os.environ.get(
        'PTCG_PROBE_CUTOFF', '2026-08-17T07:30:00+08:00'),
        help='ISO cutoff; use a later cutoff for a newly launched candidate')
    args = ap.parse_args()
    cutoff = datetime.fromisoformat(args.cutoff)
    ev = sample_once(ref=args.ref, probe_json=args.probe_json,
                     trajectory=args.trajectory, cutoff=cutoff)
    print('[probe_wr]', json.dumps(ev, ensure_ascii=False))


if __name__ == '__main__':
    main()
