"""lb_watch.py — 天梯结算观测器: last-2 提交的 publicScore + episode 数直读

观测能力 (2026-08-11 实证):
  - list_submissions → public_score, ref, status
  - list_submission_episodes(ref) → episodes 列表 (含 end_time) — 直接数对局,
    "连续4h无新对战" = now_utc - max(end_time) > 4h, 无需 publicScore 旁敲。

判读纪律 (ledger #98 / #111): 采样只是原始数据, 瞬读不记账; 触发器只标事实,
"收工/提交"判断由人+模型按闸纪律做, 脚本不自动下结论。

触发器:
  QUIET_4H  : 该提交最新 episode 距今 >4h (匹配池已不排它)
  PLATEAU   : 最近 ≥3 个样本跨 ≥4h 且分数极差 <3 分 → 已收敛
  EP_100    : episode 数首次破 100 (结算局数推荐锚)
  CRASH     : 比上一样本跌 >30 分 (异常, 值得人看)

用法: /opt/homebrew/bin/python3 experiments/lb_watch.py
产物: experiments/runs/lb_score_history.jsonl (逐样本追加)
"""
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PROJ = Path('/Users/seyonmacbook/Desktop/Pokemon_TCG_AI_Battle_Challenge')
sys.path.insert(0, str(PROJ))
from submit import get_client  # noqa: E402

HIST = PROJ / 'experiments/runs/lb_score_history.jsonl'
QUIET_H = 4.0
PLATEAU_SPAN_H = 4.0
PLATEAU_RANGE = 3.0
PLATEAU_MIN_SAMPLES = 3
CRASH_DROP = 30.0
EP_ANCHOR = 100


def _dt(v):
    if isinstance(v, datetime):
        return v.replace(tzinfo=timezone.utc) if v.tzinfo is None else v
    return datetime.fromisoformat(str(v).replace('Z', '+00:00')).replace(tzinfo=timezone.utc)


def collect():
    api = get_client().competitions.competition_api_client
    from kagglesdk.competitions.types.competition_api_service import (
        ApiListSubmissionEpisodesRequest, ApiListSubmissionsRequest)
    req = ApiListSubmissionsRequest()
    req.competition_name = 'pokemon-tcg-ai-battle'
    req.page = 1
    subs = api.list_submissions(req).submissions
    done = [s for s in subs if s.status and s.status.name == 'COMPLETE'][:2]
    now = datetime.now(timezone.utc)
    samples = []
    for s in done:
        score = float(s.public_score) if s.public_score not in (None, '', '-') else None
        ep_req = ApiListSubmissionEpisodesRequest()
        ep_req.submission_id = s.ref
        eps = list(api.list_submission_episodes(ep_req).episodes)
        ends = [_dt(e.end_time) for e in eps if getattr(e, 'end_time', None)]
        last_end = max(ends) if ends else None
        samples.append({
            'ref': s.ref, 'desc': (s.description or '')[:46], 'score': score,
            'episodes': len(eps),
            'last_ep_end': last_end.isoformat() if last_end else None,
            'quiet_h': round((now - last_end).total_seconds() / 3600, 2) if last_end else None,
        })
    return now, samples


def history(ref):
    out = []
    if HIST.exists():
        for line in HIST.read_text().splitlines():
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            for smp in ev.get('samples', []):
                if smp['ref'] == ref:
                    out.append((ev['ts'], smp))
    return out


def analyze(samples):
    triggers = []
    for smp in samples:
        ref, score = smp['ref'], smp['score']
        if smp['quiet_h'] is not None and smp['quiet_h'] > QUIET_H:
            triggers.append(f'QUIET_4H ref={ref} 已 {smp["quiet_h"]:.1f}h 无新对战')
        hist = history(ref)
        if len(hist) >= PLATEAU_MIN_SAMPLES - 1:
            seq = [h for h in hist if h[1]['score'] is not None][- (PLATEAU_MIN_SAMPLES - 1):]
            if score is not None and len(seq) == PLATEAU_MIN_SAMPLES - 1:
                vals = [h[1]['score'] for h in seq] + [score]
                span = time.time() - seq[0][0]
                if span >= PLATEAU_SPAN_H * 3600 and max(vals) - min(vals) < PLATEAU_RANGE:
                    triggers.append(f'PLATEAU ref={ref} {PLATEAU_MIN_SAMPLES}样本/'
                                    f'{span/3600:.1f}h 极差{max(vals)-min(vals):.1f}<3 → 已收敛')
                # CRASH 双样本确认 (顾问 guardrail): 连续 2 次采样各跌 >30 才开火,
                # 防波动相尖峰回落单点误报
                if (len(hist) >= 2
                        and score - hist[-1][1]['score'] < -CRASH_DROP
                        and hist[-1][1]['score'] - hist[-2][1]['score'] < -CRASH_DROP):
                    triggers.append(f'CRASH ref={ref} {hist[-2][1]["score"]}→'
                                    f'{hist[-1][1]["score"]}→{score} (连续2次)')
        if smp['episodes'] >= EP_ANCHOR and (not hist or hist[-1][1]['episodes'] < EP_ANCHOR):
            triggers.append(f'EP_100 ref={ref} 对局数破百 ({smp["episodes"]})')
    return triggers


def main():
    now, samples = collect()
    ev = {'ts': time.time(), 'ts_iso': now.isoformat(timespec='seconds'), 'samples': samples}
    with open(HIST, 'a') as f:
        f.write(json.dumps(ev, ensure_ascii=False) + '\n')
    for smp in samples:
        print(f"LBWATCH ref={smp['ref']} score={smp['score']} eps={smp['episodes']} "
              f"quiet={smp['quiet_h']}h | {smp['desc']}")
    triggers = analyze(samples)
    for t in triggers:
        print(f'TRIGGER: {t}')
    if not triggers:
        print('LBWATCH: 无触发 (继续观察)')


if __name__ == '__main__':
    main()
