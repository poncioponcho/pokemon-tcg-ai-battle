#!/usr/bin/env bash
# =====================================================================
# resume_kernel.sh — Kaggle 训练超时/中断恢复（12h 上限被砍后的续训）
# =====================================================================
# Kaggle kernel（含 Save & Run All 后台 script）单 session 上限 12h
# （官方确认，由早期 9h 提升）。若训练未完成被砍：
#   1. 从 kernel output 下载 ckpt_v2_last.pt + teacher_best.pt + student_best.pt
#      （被 cancel 的 version 其 output 不能直接挂载为 input，须走 dataset）
#   2. 上传/更新为 dataset daniel1547/ptcg-ckpt（首次 create，之后 version）
#   3. 重推训练 kernel（metadata 挂载 ptcg-ckpt）→ prepare() 自动恢复
#      → train_v2 --resume auto 从断点续训（seed 须与 TRAIN_ARGS 一致=42）
# 捷径提示：若 output 里已有 student_best.pt（distill 跑过至少一个 eval 点），
#   可跳过续训，直接用它在 CPU kernel 跑 export_student.py 导出 npz。
# 用法: bash resume_kernel.sh
# 依赖: ~/.kaggle/access_token (KGAT) + kaggle CLI 2.x
# =====================================================================
set -uo pipefail

KAG="/opt/homebrew/bin/kaggle"
KERNEL="daniel1547/ptcg-gpu-train-teacher-distill"
DATASET="daniel1547/ptcg-ckpt"
PROJ="/Users/seyonmacbook/Desktop/Pokemon_TCG_AI_Battle_Challenge"
RECOVER="${PROJ}/reports/kerr_resume"
META="${PROJ}/.kaggle_kernel/kernel-metadata.json"

echo "=== [1/4] 下载 kernel output（找 ckpt，只下 .pt/.npz） ==="
rm -rf "${RECOVER}"
env -u PYTHONHOME -u PYTHONPATH "${KAG}" kernels output "${KERNEL}" \
    -p "${RECOVER}" --file-pattern ".*\.(pt|npz)$" 2>&1 | tail -3

for n in ckpt_v2_last.pt teacher_best.pt student_best.pt; do
  found=$(find "${RECOVER}" -name "${n}" -print -quit 2>/dev/null)
  if [[ -n "${found}" ]]; then
    echo "  找到 ${n}: $(du -h "${found}" | cut -f1)"
  else
    echo "  - 无 ${n}"
  fi
done

STUDENT_BEST=$(find "${RECOVER}" -name "student_best.pt" -print -quit 2>/dev/null)
CKPT=$(find "${RECOVER}" -name "ckpt_v2_last.pt" -print -quit 2>/dev/null)

if [[ -n "${STUDENT_BEST}" ]]; then
  echo ""
  echo "💡 发现 student_best.pt —— distill 已有 best-so-far，可考虑捷径："
  echo "   不续训，直接 CPU kernel 跑 export_student.py 导出 npz（省 GPU 配额）。"
  echo "   （仍继续下方续训流程，二选一不影响）"
fi

if [[ -z "${CKPT}" ]]; then
  echo "ERROR: output 中无 ckpt_v2_last.pt（被砍前未保存到 epoch？）"
  find "${RECOVER}" -type f 2>/dev/null | head -10
  exit 1
fi

echo ""
echo "=== [2/4] 上传 ckpt 为 dataset (${DATASET}) ==="
STAGE_DIR="${PROJ}/experiments/.ckpt_dataset"
rm -rf "${STAGE_DIR}" && mkdir -p "${STAGE_DIR}"
cp "${CKPT}" "${STAGE_DIR}/ckpt_v2_last.pt"
for n in teacher_best.pt student_best.pt; do
  f=$(find "${RECOVER}" -name "${n}" -print -quit 2>/dev/null)
  [[ -n "${f}" ]] && cp "${f}" "${STAGE_DIR}/${n}"
done
cat > "${STAGE_DIR}/dataset-metadata.json" <<EOF
{
  "id": "${DATASET}",
  "title": "PTCG training checkpoint (resume)",
  "licenses": [{"name": "other"}]
}
EOF

# 首次 create，已存在则 version（datasets version 不能创建新 dataset）
if env -u PYTHONHOME -u PYTHONPATH "${KAG}" datasets list -s "ptcg-ckpt" 2>/dev/null | grep -q "${DATASET}"; then
  echo "  dataset 已存在 → version 更新"
  env -u PYTHONHOME -u PYTHONPATH "${KAG}" datasets version \
      -p "${STAGE_DIR}" -r zip -m "resume ckpt $(date '+%m-%d %H:%M')" 2>&1 | tail -3
else
  echo "  dataset 不存在 → 首次 create"
  env -u PYTHONHOME -u PYTHONPATH "${KAG}" datasets create \
      -p "${STAGE_DIR}" -r zip 2>&1 | tail -3
fi

echo ""
echo "=== [3/4] 挂载 ckpt dataset 到 kernel metadata ==="
META_PATH="${META}" DATASET="${DATASET}" python3 - <<'PYEOF'
import json, os, sys
from pathlib import Path
meta_p = Path(os.environ['META_PATH'])
meta = json.loads(meta_p.read_text(encoding='utf-8'))
ds = os.environ['DATASET']
dss = meta.get('dataset_sources', [])
if ds not in dss:
    dss.insert(0, ds)
    meta['dataset_sources'] = dss
    meta_p.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')
    print('dataset_sources 已加', ds, ':', dss)
else:
    print('已存在，无需修改')
PYEOF
if [[ $? -ne 0 ]]; then
  echo "ERROR: metadata 更新失败，中止（不重推，避免无 ckpt 从零重训）"
  exit 1
fi

echo ""
echo "=== [4/4] 重推 kernel（自动 resume） ==="
cd "${PROJ}"
python3 scripts/push_t4.py 2>&1 | tail -4
echo ""
echo "RESUME_DONE: 训练已从 ckpt 续跑（prepare() 自动恢复 + --resume auto）"
echo "验证: kaggle kernels status ${KERNEL} 应为 RUNNING，日志应出现 [resume]"
