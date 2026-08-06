#!/usr/bin/env bash
# =====================================================================
# kaggle_status.sh — Kaggle 训练/提交状态巡检（确定性输出，供定时任务调用）
# =====================================================================
# 输出约定：
#   "=== KAGGLE STATUS ... ===" 开头
#   ALERT:  前缀行 = 需要关注/告警（提交失败、npz 缺失等）
#   NOTE:   前缀行 = 参考信息（最新分数、排队中等）
#   无 ALERT = 一切正常
# 依赖：python3 + ~/.kaggle OAuth（kagglehub / access_token）
# =====================================================================
set -uo pipefail

PROJ="$(cd "$(dirname "$0")" && pwd)"
COMP="pokemon-tcg-ai-battle"

echo "=== KAGGLE STATUS $(date '+%Y-%m-%d %H:%M') ==="

# ---- 1. 本地产物 ----
if [[ -f "$PROJ/model_student.npz" ]]; then
  echo "LOCAL npz: present ($(du -h "$PROJ/model_student.npz" | cut -f1), mtime $(stat -f %Sm "$PROJ/model_student.npz"))"
else
  echo "LOCAL npz: MISSING (Kaggle 训练未产出或未下载 model_student.npz)"
  echo "ALERT: 本地无 model_student.npz —— 若 Kaggle 训练已结束，请下载放回仓库根目录"
fi

if [[ -f "$PROJ/inference/dataset/data/train_v2_report.json" ]]; then
  python3 -c "
import json
r = json.load(open('$PROJ/inference/dataset/data/train_v2_report.json'))
t = r.get('teacher') or {}; s = r.get('student') or {}
print(f'LOCAL report: teacher_canary_top1={t.get(\"canary\",{}).get(\"top1\")} student_canary_top1={s.get(\"canary\",{}).get(\"top1\")} device={r.get(\"device\")}')" 2>/dev/null \
    || echo "LOCAL report: unreadable"
fi

echo "DISK: $(df -h /System/Volumes/Data | tail -1 | awk '{print $4" free ("$5" used)"}')"

# ---- 2. Kaggle 提交状态（REST + OAuth） ----
python3 - <<'EOF' || true
import json, os, sys, urllib.request

COMP = 'pokemon-tcg-ai-battle'
token = None
try:
    token = open(os.path.expanduser('~/.kaggle/access_token')).read().strip()
except OSError:
    pass
if not token:
    try:
        from kagglehub.auth import get_kaggle_credentials
        token = get_kaggle_credentials().api_key
    except Exception:
        token = None
if not token:
    print('KAGGLE: no credentials — 无法查询提交状态（需 ~/.kaggle/access_token）')
    sys.exit(0)

req = urllib.request.Request(
    f'https://www.kaggle.com/api/v1/competitions/submissions/list/{COMP}',
    headers={'Authorization': f'Bearer {token}'})
try:
    with urllib.request.urlopen(req, timeout=20) as r:
        subs = json.loads(r.read())
except Exception as e:
    print(f'KAGGLE: API error {e}')
    sys.exit(0)

if not subs:
    print('KAGGLE: 无提交记录')
    sys.exit(0)

newest = subs[0]
st = newest.get('status', '?')
err = newest.get('errorDescription') or ''
desc = (newest.get('description') or '')[:60]
score = newest.get('publicScore') or '-'
date = (newest.get('date') or '?')[:16]
print(f'KAGGLE newest: [{st}] score={score} at {date} desc="{desc}"')

if st == 'error':
    print(f'ALERT: 最新提交失败 — {err} (提交于 {date})')
elif st in ('complete', 'success'):
    print(f'NOTE: 最新提交已评分 {score}')
else:
    print('NOTE: 最新提交仍在排队/验证中')

errs = [s for s in subs[:5] if s.get('status') == 'error']
if errs:
    print(f'ALERT: 最近 5 条提交中 {len(errs)} 条 error（最近: {errs[0].get("errorDescription") or "无详情"}）')

done = [s for s in subs if s.get('status') in ('complete', 'success') and s.get('publicScore')]
if done:
    print(f'NOTE: 最近完成分数 {done[0]["publicScore"]}（历史共 {len(done)} 条完成）')
EOF

echo "=== END ==="
