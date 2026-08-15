"""live_episodes_probe.py — 活跃提交 episode 清单生成器 + WR 主路径。

双用途:
  1) 生成 experiments/runs/live_episodes_probe.json
     (含 episode type/state；PUBLIC 与 validation 可可靠分离)
  2) stdout 直读 n/W/L/WR —— 8/15 会师判读包「WR 主路径」工具
     (episode rewards 直读, #132 同款; 不依赖 replay 拉取)

纪律: 只读 API (lb_watch 同款 list_submission_episodes); 瞬读 WR 只是原始数据,
  #98 瞬读不记账。认知层只有 WR>0.62 才宣称正效应；行动层不得把这个
  显著性阈值当作提交/归档开关，本脚本不下结论。

用法:
  /opt/homebrew/bin/python3 experiments/live_episodes_probe.py
  /opt/homebrew/bin/python3 experiments/live_episodes_probe.py --ref 55495594 \
      --out experiments/runs/live_episodes_grimmsnarl.json
"""
import argparse
import json
import os
import sys
from pathlib import Path

PROJ = Path('/Users/seyonmacbook/Desktop/Pokemon_TCG_AI_Battle_Challenge')
sys.path.insert(0, str(PROJ))
from submit import get_client  # noqa: E402
from scripts.safe_json_output import reserve_json_output  # noqa: E402

# 2026-08-15 受控实验已封口：团队榜显示 best-of-latest-2。默认跟踪当前最新的
# exact-v22 实例；可用 --ref 或 PTCG_PROBE_REF 显式覆盖。
PROBE_REF = int(os.environ.get('PTCG_PROBE_REF', '55516725'))
OUT = PROJ / os.environ.get(
    'PTCG_PROBE_OUT', 'experiments/runs/live_episodes_probe.json')


def fetch_episodes(ref=None):
    """list_submission_episodes → rows, schema 对齐 configA 件 (新→旧排序)."""
    ref = PROBE_REF if ref is None else int(ref)
    api = get_client().competitions.competition_api_client
    from kagglesdk.competitions.types.competition_api_service import (
        ApiListSubmissionEpisodesRequest)
    req = ApiListSubmissionEpisodesRequest()
    req.submission_id = ref
    eps = list(api.list_submission_episodes(req).episodes)
    rows = []
    for e in eps:
        agents = e.agents or []
        me = next((a for a in agents if a.submission_id == ref), None)
        opp = next((a for a in agents if a.submission_id != ref), None)
        dur = ((e.end_time - e.create_time).total_seconds()
               if e.end_time and e.create_time else None)
        rows.append({
            'id': e.id,
            'created': str(e.create_time) if e.create_time else None,
            'end': str(e.end_time) if e.end_time else None,
            'type': str(e.type),
            'state': str(e.state),
            'is_public': str(e.type).endswith('EPISODE_TYPE_PUBLIC'),
            'reward': me.reward if me else None,
            'seat': me.index if me else None,
            'me_state': str(me.state) if me else None,
            'me_team_id': me.team_id if me else None,
            'dur_s': round(dur, 1) if dur is not None else None,
            'opp': opp.team_name if opp else None,
            'opp_sub': opp.submission_id if opp else None,
            'opp_state': str(opp.state) if opp else None,
            'opp_team_id': opp.team_id if opp else None,
        })
    rows.sort(key=lambda r: r['end'] or '', reverse=True)
    return rows


def summarize(rows):
    # New snapshots use the official episode type.  The opp_sub fallback keeps
    # old snapshots readable without silently counting validation self-play.
    public = [
        r for r in rows
        if r.get('is_public', r.get('opp_sub') is not None)
    ]
    scored = [r for r in public if r['reward'] in (-1, 1)]
    w = sum(1 for r in scored if r['reward'] == 1)
    losses = sum(1 for r in scored if r['reward'] == -1)
    wr = w / len(scored) if scored else None
    return len(rows), len(scored), w, losses, wr


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--ref', type=int, default=PROBE_REF,
                    help='Kaggle submission ref (default: env PTCG_PROBE_REF or latest exact-v22 ref)')
    ap.add_argument('--out', default=str(OUT),
                    help='episode JSON output path (default: env PTCG_PROBE_OUT)')
    args = ap.parse_args()
    out = Path(args.out)
    if not out.is_absolute():
        out = PROJ / out
    out.parent.mkdir(parents=True, exist_ok=True)
    rows = fetch_episodes(args.ref)
    reserve_json_output(out, overwrite=True).write(rows)
    n, ns, w, losses, wr = summarize(rows)
    validation = n - sum(
        1 for row in rows
        if row.get('is_public', row.get('opp_sub') is not None)
    )
    if wr is not None:
        print(
            f'[probe] ref={args.ref} episodes={n} public_scored={ns} '
            f'validation={validation} W={w} L={losses} WR={wr:.4f}'
        )
    else:
        print(f'[probe] ref={args.ref} episodes={n} (尚无结算局)')
    try:
        shown = out.relative_to(PROJ)
    except ValueError:
        shown = out
    print(f'[probe] saved -> {shown} ({n} rows)')
    print('[probe] 纪律: 瞬读不记账 (#98); 判读走 reports/2026-08-15_会师判读包.md 决策树')


if __name__ == '__main__':
    main()
