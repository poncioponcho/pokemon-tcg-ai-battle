#!/usr/bin/env bash
# =====================================================================
# redraw_tensors.sh — 训练结束后：停止污染训练 + 重抽张量 + 重传数据集
# =====================================================================
# 背景：extract.py 的 "my deck" 槽位 bug（对手牌组填入玩家0）污染了
#   8/6 打包的 ptcg-tensors。当前在线训练用的就是污染数据（作废）。
# 修复记录（2026-08-07 audit）：
#   - fail-closed 状态守卫：仅明确匹配 COMPLETE/SUCCESS/ERROR/FAIL 才继续；
#     kaggle CLI 异常/未知状态一律跳过（防训练仍在跑时覆盖 14G 张量）
#   - 上传 exit code 校验：create/version 失败 → 不写 DONE_FLAG、退出码非 0，
#     下轮重试；杜绝"上传失败还标记完成"
#   - 部署位置：必须同时存在于 ~/.hermes/scripts/（Hermes cron 解析目录）
#     与项目 scripts/（版本控制）；本项目版本为主，部署时同步
# 测试：DRY_RUN=1 bash redraw_tensors.sh  —— 跳过 extract/上传，验证守卫
# 流程：
#   1. 前置检查：训练 kernel 已明确结束（RUNNING/CLI异常 则跳过）
#   2. 标记污染训练作废（poisoned_train_flag；resume_kernel.sh 会检查它）
#   3. 本地重抽：extract.py --archive all_replays.jsonl.zst（9-22 分钟）
#   4. 打包 ptcg_tensors.tar.gz → 上传/更新数据集 daniel1547/ptcg-tensors
#      （上传失败 → 退出非 0，不写完成标记，下轮重试）
#   5. 写完成标记 + 通知
# =====================================================================
set -uo pipefail

KAG="/opt/homebrew/bin/kaggle"
KERNEL="daniel1547/ptcg-gpu-train-teacher-distill"
PROJ="/Users/seyonmacbook/Desktop/Pokemon_TCG_AI_Battle_Challenge"
STATE_DIR="${HOME}/.hermes/state"
DONE_FLAG="${STATE_DIR}/tensor_redraw_done"
POISON_FLAG="${STATE_DIR}/poisoned_train_flag"
DATASET="daniel1547/ptcg-tensors"
DATASET_DIR="${PROJ}/experiments/.tensor_dataset"
DRY_RUN="${DRY_RUN:-0}"

# ---- 1. 状态守卫（fail-closed） ----
STATUS_LINE="$(env -u PYTHONHOME -u PYTHONPATH "${KAG}" kernels status "${KERNEL}" 2>&1 | head -1)"
case "${STATUS_LINE}" in
  *RUNNING*|*QUEUED*|*PENDING*|*CANCEL_REQUESTED*)
    # 仅这些是真正的"未结束"：CANCEL_REQUESTED 是取消中的瞬态。
    echo "TENSOR_REDRAW: 训练未完全结束（${STATUS_LINE}），跳过"
    exit 0 ;;
  *COMPLETE*|*SUCCESS*|*complete*|*success*|*ERROR*|*FAIL*|*CANCEL*|*cancel*)
    # [bugfix3] CANCEL_ACKNOWLEDGED 归入"已结束"：2026-08-07 实测 TLE 被砍后
    # 该状态持续 ≥1.5h 不翻转，是事实终态；第二轮修复曾把它放入 skip 分支，
    # 会导致 TLE 场景下重抽永远不触发（静默死锁）。kernel 输出从不写本地
    # data/，重抽覆盖与其无竞争，归入已结束是安全的。
    echo "TENSOR_REDRAW: 训练已结束（${STATUS_LINE}）→ 开始重抽 $(date '+%F %H:%M:%S')"
    ;;
  *)
    # CLI 异常 / 未知状态 / token 失效 → fail-closed：不触碰本地张量
    echo "TENSOR_REDRAW: 状态查询异常或未知（${STATUS_LINE}），跳过（fail-closed）"
    exit 0 ;;
esac

# 幂等：已重抽完成则跳过
if [[ -f "${DONE_FLAG}" ]]; then
  echo "TENSOR_REDRAW: 已重抽过（$(cat "${DONE_FLAG}")），跳过"
  exit 0
fi

# ---- 并发锁（macOS 无 flock(1)，用 mkdir 原子锁；防 cron 多实例并发） ----
# 背景：extract 单次 ~51 分钟，期间每 10 分钟的 cron 轮次在 DONE_FLAG
# 未写时会重复启动实例（2026-08-07 曾因此 exit 2 中断打包上传）。
LOCK_DIR="${STATE_DIR}/tensor_redraw.lock"
_acquire_lock() {
  if mkdir "${LOCK_DIR}" 2>/dev/null; then
    echo $$ > "${LOCK_DIR}/pid"
    return 0
  fi
  # 锁已存在：仅当持锁进程已死（stale）才抢锁
  local lp=""
  [[ -f "${LOCK_DIR}/pid" ]] && lp="$(cat "${LOCK_DIR}/pid" 2>/dev/null)"
  if [[ -z "${lp}" ]] || ! kill -0 "${lp}" 2>/dev/null; then
    /bin/rm -rf "${LOCK_DIR}"
    if mkdir "${LOCK_DIR}" 2>/dev/null; then
      echo $$ > "${LOCK_DIR}/pid"
      return 0
    fi
  fi
  return 1
}
if ! _acquire_lock; then
  echo "TENSOR_REDRAW: 另一实例运行中（${LOCK_DIR}），跳过"
  exit 0
fi
trap '/bin/rm -rf "${LOCK_DIR}"' EXIT

# ---- 2. 标记污染训练作废（resume_kernel.sh 会检查此 flag） ----
# [bugfix] DRY_RUN 检查提前：dry-run 只是验证状态守卫，不应留下 POISON_FLAG，
# 否则测试一次会让 resume_kernel.sh 永久拒绝续训（数据其实没动）。
if [[ "${DRY_RUN}" == "1" ]]; then
  echo "DRY_RUN: 跳过标记/重抽/上传，守卫验证通过"
  exit 0
fi
mkdir -p "${STATE_DIR}"
echo "poisoned-train-$(date '+%Y%m%d%H%M%S')" > "${POISON_FLAG}"
echo "  已标记污染训练作废 → ${POISON_FLAG}"

# ---- 3. 本地重抽张量（修复版 extract.py，覆盖污染数据） ----
echo "=== [1/3] 重新抽取张量（all_replays.jsonl.zst → data/） ==="
cd "${PROJ}"
if ! env -u PYTHONHOME -u PYTHONPATH /opt/homebrew/bin/python3 \
  inference/dataset/extract.py \
  --archive inference/leaderboard_replay/archive/all_replays.jsonl.zst \
  --out inference/dataset/data --workers 8 2>&1 | tail -8; then
  echo "ERROR: extract.py 重抽失败（exit=${PIPESTATUS[0]}），不写完成标记，下轮重试"
  exit 1
fi
echo "  重抽完成，新 meta.json:"
env -u PYTHONHOME -u PYTHONPATH /opt/homebrew/bin/python3 -c "import json; m=json.load(open('inference/dataset/data/meta.json')); print('   episodes:', m.get('n_episodes'), '| decisions:', m.get('n_decisions'))"

# ---- 4. 打包 + 上传数据集（上传失败 → 退出非 0，不写 DONE_FLAG） ----
echo "=== [2/3] 打包 ptcg_tensors.tar.gz ==="
rm -rf "${DATASET_DIR}" && mkdir -p "${DATASET_DIR}"
COPYFILE_DISABLE=1 tar -czf "${DATASET_DIR}/ptcg_tensors.tar.gz" \
  -C inference/dataset/data \
  episode_ids.npy labels.npy masks.npy meta.npy meta.json opts_u8.npy scalars.npy states_u8.npy
ls -lh "${DATASET_DIR}/ptcg_tensors.tar.gz"

cat > "${DATASET_DIR}/dataset-metadata.json" <<EOF
{
  "id": "${DATASET}",
  "title": "PTCG tensors (deck-fix redraw)",
  "licenses": [{"name": "other"}]
}
EOF

echo "=== [3/3] 上传数据集（create 或 version） ==="
# [bugfix] kaggle CLI 的 `datasets list -s` 只搜公开数据集，私有 ptcg-tensors
# 永远搜不到 → 永远走 create 分支 → 对已存在数据集静默 exit 0 但不更新
# （create 已存在时只打印 "already in use" 错误且不抛异常，UP_RC 误判成功）。
# 必须用 `datasets list -m -s`（-m 只看自己的数据集）才能命中私有数据集。
UP_RC=1
if env -u PYTHONHOME -u PYTHONPATH "${KAG}" datasets list -m -s "ptcg-tensors" 2>/dev/null | grep -q "${DATASET}"; then
  echo "  数据集已存在 → version 更新"
  env -u PYTHONHOME -u PYTHONPATH "${KAG}" datasets version \
    -p "${DATASET_DIR}" -r zip -m "redraw 2026-08-07 deck-fix $(date '+%m-%d %H:%M')" 2>&1 | tail -3
  UP_RC=${PIPESTATUS[0]}
else
  echo "  数据集不存在 → 首次 create"
  env -u PYTHONHOME -u PYTHONPATH "${KAG}" datasets create -p "${DATASET_DIR}" -r zip 2>&1 | tail -3
  UP_RC=${PIPESTATUS[0]}
fi
if [[ "${UP_RC}" -ne 0 ]]; then
  echo "ERROR: 数据集上传失败（rc=${UP_RC}），不写完成标记，下轮重试"
  exit 1
fi

# ---- 5. 完成标记（仅上传成功后） ----
date '+%Y-%m-%d %H:%M:%S' > "${DONE_FLAG}"
# [bugfix] 数据已重抽并重传成功 → 清除污染标记，否则 resume_kernel.sh
# 看到 POISON_FLAG 仍会 exit 3 永久拒绝续训（重抽完成即死锁）。
rm -f "${POISON_FLAG}"
osascript -e "display notification \"张量已重抽并重传 ptcg-tensors\" with title \"Hermes · 数据\"" 2>/dev/null || true
echo "TENSOR_REDRAW_DONE: 新张量已上传 ${DATASET}（污染标记已清除）"
