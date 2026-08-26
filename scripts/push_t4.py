# -*- coding: utf-8 -*-
"""push_t4.py — Kaggle 训练 kernel 推送（GPU T4 x2 优先）

关键认知（来自踩坑复盘）：
- kaggle CLI push 的 --accelerator 不生效 / metadata 的 machine_shape 字段被忽略
  → 一直拿到默认 P100（sm_60，与 cu128 torch 不兼容，训练必崩）
- machine_shape 是在 create_kernel_session 阶段生效的（不是 save 阶段）
- 账号支持 GPU T4 x2（sm_75，与 cu128 torch 完全兼容，无需降级）

[2026-08-08 提交纪律] 任何 push 前必须先通过 preflight 强制校验。
  - --stage teacher|distill 必须显式指定（禁止默认推断，防 stage 漂移）
  - preflight 不通过 → 阻止 push（exit 1）
  - **没有 --skip-preflight 逃生开关**：想跳过只能在 preflight.sh 里手动改代码，
    且 push 本身不可跳过。--dry-run 只跑 preflight 不实际 push（测试用）。

用法:
  python3 push_t4.py --stage teacher [--shape "NvidiaTeslaT4"]   # 正常推送（先过 preflight）
  python3 push_t4.py --stage teacher --dry-run                    # 只跑 preflight，不 push
"""
import json
import sys
import time
from pathlib import Path

KD = Path('/Users/seyonmacbook/Desktop/Pokemon_TCG_AI_Battle_Challenge/.kaggle_kernel')
META = json.loads((KD / 'kernel-metadata.json').read_text(encoding='utf-8'))
CODE = (KD / 'run_experiment.py').read_text(encoding='utf-8')

# 数据集挂载来自 kernel-metadata.json 的 dataset_sources（默认训练数据+代码）。
# resume_kernel.sh 会把续训 ckpt dataset 插入该列表；此处必须读取它，
# 否则硬编码列表会让 ckpt 永不挂载 → 超时续训静默失效。
DEFAULT_SOURCES = ['daniel1547/ptcg-tensors', 'daniel1547/ptcg-code']
DATA_SOURCES = [s for s in (META.get('dataset_sources') or DEFAULT_SOURCES) if s]
if not DATA_SOURCES:
    DATA_SOURCES = list(DEFAULT_SOURCES)

SHAPE = 'NvidiaTeslaT4'
if '--shape' in sys.argv:
    # [fix 08-09] --shape 为最后一个参数时 index+1 越界 IndexError, 给清晰报错
    _i = sys.argv.index('--shape')
    if _i + 1 >= len(sys.argv):
        raise SystemExit('[错误] --shape 需要一个参数值, 例如 --shape NvidiaTeslaT4')
    SHAPE = sys.argv[_i + 1]

# [2026-08-08] 强制前置校验（不可绕过）：任何 push 前必须过 preflight。
# 灾难复盘：auto_fix 曾把 stage 覆盖成 'all' + cu118 降级失败 → CPU 兜底跑 19h 作废；
#           版本错配（kernel 带 --prefetch-* 参数但数据集 train_v2.py 旧版）→ ERROR。
# 期望 stage 必须显式指定。--dry-run 只跑 preflight 不实际 push。
DRY_RUN = '--dry-run' in sys.argv
if '--stage' not in sys.argv:
    print('PUSH BLOCKED: 必须显式指定 --stage teacher|distill（禁止默认推断，防 stage 漂移）')
    sys.exit(1)
expected_stage = sys.argv[sys.argv.index('--stage') + 1]
import subprocess as _sp
pf = _sp.run(['bash', str(KD.parent / 'scripts' / 'preflight.sh'),
              '--stage', expected_stage],
             capture_output=True, text=True)
print(pf.stdout)
if pf.returncode != 0:
    print('PUSH BLOCKED: preflight failed（先修复上述 FAIL 项再推）')
    sys.exit(1)
print('preflight PASSED')
if DRY_RUN:
    print('DRY-RUN: preflight 通过，未实际 push')
    sys.exit(0)
print('继续 push')

from kagglesdk import KaggleClient, KaggleEnv
from kagglesdk.kernels.types.kernels_api_service import (
    ApiSaveKernelRequest,
    ApiCreateKernelSessionRequest,
    ApiDeleteKernelRequest,
)

client = KaggleClient(env=KaggleEnv.PROD)
api = client.kernels.kernels_api_client
SLUG = 'ptcg-gpu-train-teacher-distill'
OWNER = 'daniel1547'

# 1) 删除旧 kernel（避免 409 / 旧 ERROR session 占用）
try:
    req = ApiDeleteKernelRequest()
    req.user_name = OWNER
    req.kernel_slug = SLUG
    api.delete_kernel(req)
    print('1. 旧 kernel 已删除')
except Exception as e:
    print('1. 删除跳过（不存在或冲突）:', str(e)[:80])
time.sleep(3)

# 2) 保存新代码
req = ApiSaveKernelRequest()
req.slug = f'{OWNER}/{SLUG}'
req.new_title = META.get('title', 'PTCG GPU Train')
req.text = CODE
req.language = 'python'
req.kernel_type = 'script'
req.is_private = True
req.enable_gpu = True
req.enable_internet = True
req.dataset_data_sources = DATA_SOURCES
req.competition_data_sources = ['pokemon-tcg-ai-battle']
try:
    resp = api.save_kernel(req)
    print('2. save_kernel OK (version', resp.version_number, ')')
except Exception as e:
    print('2. save FAIL:', type(e).__name__, str(e)[:200])
    sys.exit(1)
time.sleep(2)

# 3) 启动 session（关键：此处指定 machine_shape）
sreq = ApiCreateKernelSessionRequest()
sreq.slug = f'{OWNER}/{SLUG}'
sreq.language = 'python'
sreq.kernel_type = 'script'
sreq.enable_internet = True
sreq.machine_shape = SHAPE
try:
    sresp = api.create_kernel_session(sreq)
    md = sresp.metadata if hasattr(sresp, 'metadata') else sresp
    if isinstance(md, dict):
        sid = md.get('kernel_session_id') or md.get('kernelSessionId') or md
    else:
        sid = md.kernel_session_id
    print(f'3. session 已启动 (id={sid}, shape={SHAPE})')
except Exception as e:
    print('3. session FAIL:', type(e).__name__, str(e)[:200])
    sys.exit(1)

print(f'PUSH_OK shape={SHAPE}')
