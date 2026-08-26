#!/usr/bin/env bash
# =====================================================================
# preflight.sh — Kaggle push 前强制校验（2026-08-08 灾难后新增）
# =====================================================================
# 背景：8/8 事故链 —— auto_fix_kernel.sh FIX-6 把 stage 强制还原成 'all'
#   + cu118 降级验证失败 → CPU 兜底 --stage all 跑 19h 全部作废。
#   教训：任何 push 到 Kaggle 前必须彻底本地测试/debug。
#
# 本脚本作为 push 前置门禁，校验失败即 exit 非 0 阻止 push。
# 用法:
#   bash scripts/preflight.sh [--stage teacher|distill] [--fix]
#     --fix    自动修复可修复项（当前：还原 stage；不可修复项仍 FAIL）
#
# 校验项：
#   P1. 本地 .kaggle_kernel/run_experiment.py 存在且语法 OK
#   P2. stage 默认值 = 期望值（默认 teacher；可 --stage 覆盖）
#   P3. auto_fix_kernel.sh 已加 FIX-6 保护开关（ALLOW_STAGE_ALL_FORCE guard）
#   P4. prefetch 参数已在 run_experiment.py（新代码标志）
#   P5. ptcg-code 数据集里的 train_v2.py 含 BatchPrefetcher（代码包一致）
#   P6. 本地 smoke test：train_v2.py --limit 跑 1 epoch 不崩
#   P7. kernel-metadata.json dataset_sources 不含污染来源
# =====================================================================
set -uo pipefail

PROJ="/Users/seyonmacbook/Desktop/Pokemon_TCG_AI_Battle_Challenge"
KD="${PROJ}/.kaggle_kernel"
RUN_PY="${KD}/run_experiment.py"
AUTOFIX="${HOME}/.hermes/scripts/auto_fix_kernel.sh"
STAGE="teacher"
DO_FIX=0
PY="/opt/homebrew/bin/python3"
KAG="/opt/homebrew/bin/kaggle"
CODE_DS="daniel1547/ptcg-code"

for arg in "$@"; do
  case "$arg" in
    --stage) STAGE="${2:-teacher}" ;;
    --fix) DO_FIX=1 ;;
  esac
done

FAIL=0
WARN=0

echo "===== PUSH PREFLIGHT (stage=${STAGE}) $(date '+%F %H:%M:%S') ====="

# ---------- P1: 语法 ----------
if [[ ! -f "${RUN_PY}" ]]; then
  echo "P1 FAIL: ${RUN_PY} 不存在"; FAIL=1
else
  "${PY}" -c "import ast; ast.parse(open('${RUN_PY}').read())" 2>/dev/null \
    && echo "P1 OK: run_experiment.py 语法正确" \
    || { echo "P1 FAIL: run_experiment.py 语法错误"; FAIL=1; }
fi

# ---------- P1b: 关键修复必须落位（防 auto_fix 覆盖回退） ----------
# 1) cu118 pin 版本（未 pin 会装无 sm_60 的最新 torch → P100 上 no kernel image）
# 2) fail-fast（CPU 兜底改 SystemExit，防静默慢跑烧配额）
# 3) export 保护（teacher 阶段不导出 npz，防尾部 ERROR）
for fix_pat in "torch==2.5.1" "KAGGLE_ALLOW_CPU_FALLBACK" "student_best.pt').exists()" "/kaggle/working/ptcg_restart.py" "link.symlink_to(DATA_DIR)"; do
  if grep -q "${fix_pat}" "${RUN_PY}" 2>/dev/null; then
    echo "P1b OK: run_experiment.py 含修复「${fix_pat}」"
  else
    echo "P1b FAIL: run_experiment.py 缺修复「${fix_pat}」（可能被 auto_fix 覆盖）"
    FAIL=1
  fi
done

# ---------- P2: stage ----------
CUR_STAGE=$(grep -oE "KAGGLE_STAGE', '[a-z]+'" "${RUN_PY}" 2>/dev/null | grep -oE "'[a-z]+'" | tr -d "'")
if [[ "${CUR_STAGE}" == "${STAGE}" ]]; then
  echo "P2 OK: stage=${CUR_STAGE} 符合期望"
else
  echo "P2 FAIL: stage=${CUR_STAGE} (期望 ${STAGE})"
  if [[ "${DO_FIX}" == "1" ]]; then
    sed -i '' "s/KAGGLE_STAGE', '[a-z]*'/KAGGLE_STAGE', '${STAGE}'/" "${RUN_PY}"
    echo "  --fix: 已还原 stage → ${STAGE}"
    CUR_STAGE="${STAGE}"
  else
    FAIL=1
  fi
fi

# ---------- P3: auto_fix FIX-6 保护 ----------
if [[ -f "${AUTOFIX}" ]] && grep -q "ALLOW_STAGE_ALL_FORCE" "${AUTOFIX}"; then
  echo "P3 OK: auto_fix FIX-6 已加保护开关"
else
  echo "P3 FAIL: auto_fix_kernel.sh 未加 FIX-6 保护（会覆盖 stage→all）"
  if [[ "${DO_FIX}" == "1" ]]; then
    echo "  --fix: 无法自动修复，请手动给 auto_fix_kernel.sh 加 ALLOW_STAGE_ALL_FORCE guard"
  fi
  FAIL=1
fi

# ---------- P4: prefetch 标志 ----------
if grep -q "prefetch-workers\|BatchPrefetcher" "${RUN_PY}" 2>/dev/null; then
  echo "P4 OK: run_experiment.py 含 prefetch 参数（新代码）"
else
  echo "P4 WARN: run_experiment.py 无 prefetch 参数（可能被 auto_fix 覆盖回旧版）"
  WARN=1
fi

# ---------- P5: ptcg-code 数据集的 train_v2.py ----------
# [2026-08-08] 改为 FAIL：线上数据集必须与 kernel 的 run_experiment.py 参数集匹配。
# 事故：kernel 新版带 --prefetch-* 参数，线上 ptcg-code 数据集 train_v2.py 是旧版
# → train_v2.py: error: unrecognized arguments → session ERROR。
STAGE_TAR="${PROJ}/.kaggle_stage_code/ptcg_code.tar.gz"
if [[ -f "${STAGE_TAR}" ]] && tar -xOf "${STAGE_TAR}" train_v2.py 2>/dev/null | grep -q "class BatchPrefetcher"; then
  echo "P5 OK: ptcg-code tar 内含 BatchPrefetcher（优化代码）"
else
  echo "P5 FAIL: ptcg-code tar 缺失或无 BatchPrefetcher（推送前需先重建打包并上传）"
  FAIL=1
fi
# P5b: kernel 的 prefetch 参数与 tar 内 train_v2.py 参数集一致（防版本错配）
if [[ -f "${STAGE_TAR}" ]]; then
  KERNEL_PF=$(grep -c "prefetch-workers" "${RUN_PY}")
  TAR_PF=$(tar -xOf "${STAGE_TAR}" train_v2.py 2>/dev/null | grep -c "prefetch-workers")
  if [[ "${KERNEL_PF}" -ge 1 && "${TAR_PF}" -ge 1 ]]; then
    echo "P5b OK: kernel 与 ptcg-code 的 train_v2.py 均含 prefetch 参数（版本一致）"
  elif [[ "${KERNEL_PF}" -eq 0 && "${TAR_PF}" -eq 0 ]]; then
    echo "P5b OK: 双方均无 prefetch（旧版一致，可推）"
  else
    echo "P5b FAIL: 版本错配 — kernel prefetch=${KERNEL_PF} vs tar prefetch=${TAR_PF}（会 unrecognized arguments）"
    FAIL=1
  fi
fi
# P5c: 用线上 ptcg-code 数据集的 train_v2.py 实际跑 --help，验证 kernel 的
#      参数集全部被支持（直接复现上次 "unrecognized arguments" ERROR 的检查）。
echo "P5c: 从线上 ptcg-code 数据集下载 train_v2.py 验证参数集..."
REMOTE_TMP=$(mktemp -d)
if env -u PYTHONHOME -u PYTHONPATH "${KAG}" datasets download -d "${CODE_DS}" \
    --unzip -p "${REMOTE_TMP}" >/dev/null 2>&1; then
  # 数据集解压后平铺：train_v2.py 在根目录
  RPY=$(find "${REMOTE_TMP}" -name "train_v2.py" 2>/dev/null | head -1)
  if [[ -n "${RPY}" ]] && [[ -s "${RPY}" ]]; then
    # 提取 kernel TRAIN_ARGS 块的 --xxx 参数（排除 pip/export 等其他命令的参数），
    # 逐一在远程 train_v2.py 里确认存在
    MISSING=""
    for arg in $(RUN_PY="${RUN_PY}" "${PY}" - <<'PYEOF'
import os, re
src = open(os.environ['RUN_PY']).read()
# 只取 TRAIN_ARGS = [ ... ] 之间的 '--xxx'
m = re.search(r'TRAIN_ARGS\s*=\s*\[(.*?)\]', src, re.S)
if m:
    args = re.findall(r"'--([a-z-]+)'", m.group(1))
else:
    args = []
print('\n'.join(sorted(set(args))))
PYEOF
); do
      if ! grep -qE "\-\-${arg}([^a-z-]|$)|'--${arg}'" "${RPY}"; then
        MISSING="${MISSING} ${arg}"
      fi
    done
    if [[ -n "${MISSING}" ]]; then
      echo "P5c FAIL: 远程 train_v2.py 不支持参数:${MISSING}（会 unrecognized arguments，禁止 push）"
      FAIL=1
    else
      echo "P5c OK: 远程 train_v2.py 支持 kernel 全部参数"
    fi
  else
    echo "P5c WARN: 数据集内未找到 train_v2.py（结构异常）"
    WARN=1
  fi
else
  echo "P5c WARN: 线上数据集下载失败（检查网络/权限）"
  WARN=1
fi
rm -rf "${REMOTE_TMP}"
# P5d: 远程 export_student.py 必须含 shape 推断（student_hidden 可调时 export 要自适应）。
# 事故：student_hidden 384→768 时，export 若硬编码 384 会 size mismatch → ERROR。
echo "P5d: 检查线上 export_student.py 含 shape 推断..."
DTMP=$(mktemp -d)
if env -u PYTHONHOME -u PYTHONPATH "${KAG}" datasets download -d "${CODE_DS}" \
    --unzip -p "${DTMP}" >/dev/null 2>&1; then
  EXPORT_PY=$(find "${DTMP}" -name "export_student.py" 2>/dev/null | head -1)
  if [[ -n "${EXPORT_PY}" ]] && grep -q "shape-infer" "${EXPORT_PY}"; then
    echo "P5d OK: 远程 export_student.py 含 shape 推断"
  else
    echo "P5d FAIL: 远程 export_student.py 缺 shape 推断（student_hidden>384 会 size mismatch）"
    FAIL=1
  fi
else
  echo "P5d WARN: 线上数据集下载失败"
  WARN=1
fi
rm -rf "${DTMP}"

# P5e: tar 内 train_v2.py 含 resume 架构容错（student_hidden 变更不崩）。
if [[ -f "${STAGE_TAR}" ]] && tar -xOf "${STAGE_TAR}" train_v2.py 2>/dev/null | grep -q "架构不匹配"; then
  echo "P5e OK: tar 内 train_v2.py 含 resume 架构容错"
else
  echo "P5e FAIL: tar 内 train_v2.py 缺 resume 架构容错（student_hidden 变更会 size mismatch）"
  FAIL=1
fi

# ---------- P6: 本地 smoke test ----------
SMOKE_TS=$(mktemp)
echo "P6: 本地 smoke（limit=30000, 1 epoch）..."
# distill 阶段需要 teacher_best.pt 存在才能启动；用已下载的真实 teacher ckpt
# 作为种子（若有），否则先跑 teacher 1 epoch 生成（limit 下 teacher 部分极快）。
TEACHER_SEED=""
if [[ "${STAGE}" == "distill" ]]; then
  for cand in "${PROJ}/reports/kerr_teacher/ckpt/teacher_best.pt" \
              "${PROJ}/reports/kerr_teacher/teacher_best.pt" \
              "${PROJ}/.kaggle_stage_ckpt/teacher_best.pt"; do
    if [[ -f "${cand}" ]]; then TEACHER_SEED="${cand}"; break; fi
  done
  if [[ -n "${TEACHER_SEED}" ]]; then
    cp "${TEACHER_SEED}" "${SMOKE_TS}.teacher.pt"
    echo "  P6: 用真实 teacher_best.pt 作为 distill 种子（${TEACHER_SEED}）"
  fi
fi
if (cd "${PROJ}/inference/dataset" && "${PY}" train_v2.py \
    --stage "${STAGE}" --epochs-bc 1 --epochs-awr 0 --epochs-distill 1 \
    --limit 30000 --device cpu \
    --data-dir data --ckpt-path "${SMOKE_TS}.pt" \
    --teacher-best "${SMOKE_TS}.teacher.pt" \
    --student-best "${SMOKE_TS}.student.pt" \
    --logs-dir "${SMOKE_TS}.logs" \
    --split-manifest splits/episode_splits.jsonl \
    --canary-manifest splits/rolling_canary.json \
    > /dev/null 2>&1); then
  echo "P6 OK: smoke test 通过"
else
  echo "P6 FAIL: smoke test 崩溃（distill 阶段需 teacher_best.pt 种子，见 --teacher-best）"
  FAIL=1
fi
rm -f "${SMOKE_TS}"* 2>/dev/null; rm -rf "${SMOKE_TS}.logs"

# ---------- P7: dataset_sources ----------
if grep -q "ptcg-tensors" "${KD}/kernel-metadata.json" && grep -q "ptcg-code" "${KD}/kernel-metadata.json"; then
  echo "P7 OK: dataset_sources 含 ptcg-tensors + ptcg-code"
else
  echo "P7 FAIL: dataset_sources 缺失训练数据/代码"
  FAIL=1
fi

echo ""
if [[ "${FAIL}" -eq 1 ]]; then
  echo "===== PREFLIGHT FAILED（阻止 push）====="
  exit 1
elif [[ "${WARN}" -gt 0 ]]; then
  echo "===== PREFLIGHT PASSED（有 WARN，需确认）====="
  exit 0
else
  echo "===== PREFLIGHT PASSED ====="
  exit 0
fi
