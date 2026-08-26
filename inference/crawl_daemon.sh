#!/bin/zsh
# crawl_daemon.sh — launchd 守护：崩溃自重启、重启后自动拉起、每日 08:10 自动续跑
# 退出策略：
#   - 预算已耗尽（request_budget.json used >= budget）→ 合并归档后 exit 0（今日收工）
#   - rc==0（正常完成）→ 合并归档后 exit 0
#   - 其他异常 → 15s 后 exit 1（launchd KeepAlive 重启）
# 说明：
#   - --no-finalize 关闭爬取内置的慢速 finalize，归档统一由本脚本 merge 处理
#   - merge 把 raw/ 新增 replay 增量并入 canonical 归档 all_replays.jsonl.zst
#     （流式保留既有记录，按 episode_id 去重，原子替换）
source "$HOME/.zshrc" 2>/dev/null   # 提供 KAGGLE_API_TOKEN
OUT="/Users/seyonmacbook/Desktop/Pokemon_TCG_AI_Battle_Challenge/inference"
PY="$OUT/ptcg_replay_harvester.py"
ALL_ARCH="$OUT/leaderboard_replay/archive/all_replays.jsonl.zst"
RAW_DIR="$OUT/leaderboard_replay/raw"
BUDGET_FILE="$OUT/leaderboard_replay/request_budget.json"
DAEMON_LOG="$OUT/leaderboard_replay/crawl_daemon.log"

merge_archive() {
  echo "[$(date '+%F %H:%M')] 合并 raw -> all_replays.jsonl.zst" >> "$DAEMON_LOG"
  python3 "$OUT/dataset/replay_archive.py" merge \
    --archive "$ALL_ARCH" --raw-dir "$RAW_DIR" >> "$DAEMON_LOG" 2>&1
  echo "[$(date '+%F %H:%M')] 合并完成" >> "$DAEMON_LOG"
}

if pgrep -f "ptcg_replay_harvester.py --out" > /dev/null 2>&1; then
  echo "[$(date '+%F %H:%M')] 已有爬取进程在跑，本实例退出" >> "$DAEMON_LOG"
  exit 0
fi

budget_left() {
  python3 -c "
import json, time
try:
    s = json.load(open('$BUDGET_FILE'))
    today = time.strftime('%Y-%m-%d', time.gmtime())
    used = int(s.get('used', 0)) if s.get('date') == today else 0
    print(max(0, 3000 - used))
except Exception:
    print(3000)
" 2>/dev/null
}

LEFT=$(budget_left)
if [ "$LEFT" -le 0 ]; then
  echo "[$(date '+%F %H:%M')] 预算已用尽（今日收工），合并归档" >> "$DAEMON_LOG"
  merge_archive
  echo "[$(date '+%F %H:%M')] 归档完成，今日结束（明日 08:10 自动续跑）" >> "$DAEMON_LOG"
  exit 0
fi

echo "[$(date '+%F %H:%M')] daemon: 启动爬取（预算余量: $LEFT）" >> "$DAEMON_LOG"
caffeinate -i python3 "$PY" --out "$OUT/leaderboard_replay" --delay 7 --budget 3000 \
  incremental --top 0 --min-score 600 --max-score 99999 --no-finalize \
  >> "$OUT/leaderboard_replay/chunk_live_600_1000.log" 2>&1
RC=$?
echo "[$(date '+%F %H:%M')] daemon: 爬取退出 rc=$RC" >> "$DAEMON_LOG"

LEFT=$(budget_left)
if [ "$LEFT" -le 0 ]; then
  echo "[$(date '+%F %H:%M')] 预算用尽，合并归档后收工" >> "$DAEMON_LOG"
  merge_archive
  echo "[$(date '+%F %H:%M')] 归档完成，今日结束" >> "$DAEMON_LOG"
  exit 0
fi

if [ $RC -eq 0 ]; then
  echo "[$(date '+%F %H:%M')] daemon: 正常收工，合并归档" >> "$DAEMON_LOG"
  merge_archive
  echo "[$(date '+%F %H:%M')] daemon: 归档完成，今日结束" >> "$DAEMON_LOG"
  exit 0
fi

echo "[$(date '+%F %H:%M')] daemon: 异常退出，15s 后交还 launchd 重启" >> "$DAEMON_LOG"
sleep 15
exit 1
