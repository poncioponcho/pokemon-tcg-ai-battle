#!/usr/bin/env bash
# =====================================================================
# param_tune_guard.sh —— param_tune 静默死亡自动重开看守
# =====================================================================
# 背景: jetsam 曾两次无声杀掉调权进程(08-09 07:05 PID3973 / 08:25 PID49842),
# 断点(param_tune_ckpt.jsonl)可无损续跑, 但靠人工发现会白等数小时。
# 本看守每 60s 巡检一次:
#   - 进程存活 → 继续睡
#   - 进程消失且事件流中本轮(最后一个 start 之后)已出 param_tune_final → 正常完成, 退出
#   - 否则判定异常死亡 → 90s 冷静期后 nice -n 10 重开(断点自动续),
#     并写 ledger(source=auto_guard)。最多重开 MAX_RELAUNCH 次。
#
# 用法: nohup bash experiments/param_tune_guard.sh >> /dev/null 2>&1 &
# 环境变量: GUARD_WORKERS(默认4) GUARD_MAX_RELAUNCH(默认6)
# 注意: 若调权期间改动 main.py/deck.csv, 重开会自动进入新命名空间(旧断点不污染),
#       但进度会从头开始 —— 调权期间勿动这两个文件。
# =====================================================================
set -uo pipefail
cd "$(dirname "$0")/.."

EVENTS=experiments/runs/param_tune.jsonl
LOG=experiments/runs/param_tune_guard.log
WORKERS="${GUARD_WORKERS:-4}"
MAX_RELAUNCH="${GUARD_MAX_RELAUNCH:-6}"

log(){ echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG"; }

# 存活性以「进程映像为 python 且参数含 param_tune.py」为准,
# 避免误判 nohup/bash 包装进程或本看守自身。
alive(){
  local p
  for p in $(pgrep -f "param_tune\.py" 2>/dev/null); do
    if ps -p "$p" -o comm= 2>/dev/null | grep -qi python; then
      return 0
    fi
  done
  return 1
}

# 完成判定: 事件流(append-only)中最后一个 param_tune_final 行号 > 最后一个 start 行号
run_finished(){
  [[ -f "$EVENTS" ]] || return 1
  python3 - "$EVENTS" <<'PY'
import sys
last_start = last_final = -1
with open(sys.argv[1], encoding='utf-8') as f:
    for i, line in enumerate(f):
        if '"ev": "start"' in line:
            last_start = i
        elif '"ev": "param_tune_final"' in line:
            last_final = i
sys.exit(0 if (last_start >= 0 and last_final > last_start) else 1)
PY
}

log "guard start: pid=$$ workers=$WORKERS max_relaunch=$MAX_RELAUNCH"
n=0
while true; do
  if alive; then
    sleep 60
    continue
  fi
  if run_finished; then
    log "param_tune_final 已出现，本轮调权正常完成，guard 退出"
    break
  fi
  if (( n >= MAX_RELAUNCH )); then
    log "已达最大重开次数 $MAX_RELAUNCH，guard 停止（需人工介入）"
    break
  fi
  n=$((n + 1))
  log "检测到 param_tune 消失且无 final（疑似再次被杀），90s 冷静期后第 $n 次重开..."
  sleep 90
  if alive; then
    log "重开前发现进程已复活，跳过本次重开"
    continue
  fi
  # [fix 08-09 B4-3] rounds/workers 不再硬编码: 从事件流最后一个 start 的
  # msg(含 rounds=N workers=N)解析继承原轮配置, GUARD_WORKERS 仍可强制覆盖
  read -r ROUNDS USE_WORKERS <<< "$(python3 - "$EVENTS" "$WORKERS" <<'PY'
import re, sys
rounds, workers = 2, int(sys.argv[2])
try:
    last = ""
    with open(sys.argv[1], encoding='utf-8') as f:
        for line in f:
            if '"ev": "start"' in line:
                last = line
    m = re.search(r'rounds=(\d+)', last)
    if m:
        rounds = int(m.group(1))
except Exception:
    pass
print(rounds, workers)
PY
)"
  nohup nice -n 10 python3 experiments/param_tune.py --rounds "$ROUNDS" --workers "$USE_WORKERS" \
    >> experiments/runs/param_tune_stdout.log 2>&1 &
  newpid=$!
  log "已重开: pid=$newpid rounds=$ROUNDS workers=$USE_WORKERS (第 $n 次)"
  python3 - "$newpid" "$USE_WORKERS" "$n" "$ROUNDS" <<'PY'
import json, sys, time
ev = {
    "ts": time.time(),
    "event": "param_tune_launch",
    "pid": int(sys.argv[1]),
    "workers": int(sys.argv[2]),
    "rounds": int(sys.argv[4]),
    "source": "auto_guard",
    "note": f"guard 自动重开(第{sys.argv[3]}次): 进程无声死亡自愈, 断点自动续跑",
    "cmd": f"nohup nice -n 10 python3 experiments/param_tune.py --rounds {sys.argv[4]} --workers {sys.argv[2]} >> experiments/runs/param_tune_stdout.log 2>&1 &",
}
with open('experiments/ledger.jsonl', 'a', encoding='utf-8') as f:
    f.write(json.dumps(ev, ensure_ascii=False) + '\n')
PY
  sleep 120
done
