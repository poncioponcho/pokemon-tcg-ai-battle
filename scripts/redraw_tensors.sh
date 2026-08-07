#!/usr/bin/env bash
# =====================================================================
# redraw_tensors.sh — 训练结束后：停止污染训练 + 重抽张量 + 重传数据集
# =====================================================================
# 背景：extract.py 的 "my deck" 槽位 bug（对手牌组填入玩家0）污染了
#   8/6 打包的 ptcg-tensors。当前在线训练用的就是污染数据（作废）。
# 流程（幂等，可安全重跑）：
#   1. 前置检查：训练 kernel 已结束（RUNNING/QUEUED 则跳过）
#   2. 标记污染训练作废（state 文件，防 resume 误触发）
#   3. 本地重抽张量：extract.py --archive all_replays.jsonl.zst
#      （9-22 分钟，覆盖 inference/dataset/data/ 旧污染张量）
#   4. 打包 ptcg_tensors.tar.gz → 上传/更新数据集 daniel1547/ptcg-tensors
#   5. 写完成标记 + 通知
# 用法: bash redraw_tensors.sh    （由 Hermes cron 每 10 分钟触发）
# =====================================================================
set -uo pipefail

KAG="/opt/homebrew/bin/kaggle"
KERNEL="daniel1547/ptcg-gpu-train-teacher-distill"
PROJ="/Users/seyonmacbook/Desktop/Pokemon_TCG_AI_Battle_Challenge"
STATE_DIR="${HOME}/.hermes/state"
DONE_FLAG="${STATE_DIR}/tensor_redraw_done"
DATASET="daniel1547/ptcg-tensors"
DATASET_DIR="${PROJ}/experiments/.tensor_dataset"

# ---- 1. 训练是否已结束（幂等守卫） ----
STATUS="$(env -u PYTHONHOME -u PYTHONPATH "${KAG}" kernels status "${KERNEL}" 2>&1 | head -1)"
case "${STATUS}" in
  *RUNNING*|*QUEUED*|*PENDING*)
    exit 0 ;;   # 训练还在跑，等下一轮
esac
if [[ -f "${DONE_FLAG}" ]]; then
  echo "TENSOR_REDRAW: 已重抽过（$(cat "${DONE_FLAG}")），跳过"
  exit 0
fi

echo "TENSOR_REDRAW: 训练已结束（${STATUS}）→ 开始重抽张量 $(date '+%F %H:%M:%S')"

# ---- 2. 标记污染训练作废（防 resume_kernel.sh 误触发续训） ----
mkdir -p "${STATE_DIR}"
echo "poisoned-train-$(date '+%Y%m%d%H%M%S')" > "${STATE_DIR}/poisoned_train_flag"
echo "  已标记污染训练作废（state/poisoned_train_flag）"

# ---- 3. 本地重抽张量（修复版 extract.py，覆盖污染数据） ----
echo "=== [1/3] 重新抽取张量（all_replays.jsonl.zst → data/） ==="
cd "${PROJ}"
time env -u PYTHONHOME -u PYTHONPATH /opt/homebrew/bin/python3 \
  inference/dataset/extract.py \
  --archive inference/leaderboard_replay/archive/all_replays.jsonl.zst \
  --out inference/dataset/data --workers 8 2>&1 | tail -8
if [[ $? -ne 0 ]]; then
  echo "ERROR: extract.py 重抽失败"
  exit 1
fi
echo "  重抽完成，新 meta.json:"
python3 -c "import json; m=json.load(open('inference/dataset/data/meta.json')); print('   episodes:', m.get('n_episodes'), '| decisions:', m.get('n_decisions'))"

# ---- 4. 打包 + 上传数据集 ----
echo "=== [2/3] 打包 ptcg_tensors.tar.gz ==="
rm -rf "${DATASET_DIR}" && mkdir -p "${DATASET_DIR}"
COPYFILE_DISABLE=1 tar -czf "${DATASET_DIR}/ptcg_tensors.tar.gz" \
  -C inference/dataset/data \
  episode_ids.npy labels.npy masks.npy meta.npy meta.json opts_u8.npy scalars.npy states_u8.npy
ls -lh "${DATASET_DIR}/ptcg_tensors.tar.gz"

cat > "${DATASET_DIR}/dataset-metadata.json" <<EOF
{
  "id": "${DATASET}",
  "title": "PTCG training tensors (redrawn 2026-08-07, deck-fix)",
  "licenses": [{"name": "other"}]
}
EOF

echo "=== [3/3] 上传数据集（create 或 version） ==="
if env -u PYTHONHOME -u PYTHONPATH "${KAG}" datasets list -s "ptcg-tensors" 2>/dev/null | grep -q "${DATASET}"; then
  echo "  数据集已存在 → version 更新"
  env -u PYTHONHOME -u PYTHONPATH "${KAG}" datasets version \
    -p "${DATASET_DIR}" -r zip -m "redraw 2026-08-07 deck-fix $(date '+%m-%d %H:%M')" 2>&1 | tail -3
else
  echo "  数据集不存在 → 首次 create"
  env -u PYTHONHOME -u PYTHONPATH "${KAG}" datasets create -p "${DATASET_DIR}" -r zip 2>&1 | tail -3
fi

# ---- 5. 完成标记 ----
date '+%Y-%m-%d %H:%M:%S' > "${DONE_FLAG}"
osascript -e "display notification \"张量已重抽并重传 ptcg-tensors\" with title \"Hermes · 数据\"" 2>/dev/null || true
echo "TENSOR_REDRAW_DONE: 新张量已上传 ${DATASET}"
