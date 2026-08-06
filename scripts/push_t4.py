# -*- coding: utf-8 -*-
"""push_t4.py — Kaggle 训练 kernel 推送（GPU T4 x2 优先）

关键认知（来自踩坑复盘）：
- kaggle CLI push 的 --accelerator 不生效 / metadata 的 machine_shape 字段被忽略
  → 一直拿到默认 P100（sm_60，与 cu128 torch 不兼容，训练必崩）
- machine_shape 是在 create_kernel_session 阶段生效的（不是 save 阶段）
- 账号支持 GPU T4 x2（sm_75，与 cu128 torch 完全兼容，无需降级）

用法: python3 push_t4.py [--shape "GPU T4 x2"|"GPU"]
流程: 删除旧 kernel → save 代码 → create_kernel_session(machine_shape)
"""
import json
import sys
import time
from pathlib import Path

KD = Path('/Users/seyonmacbook/Desktop/Pokemon_TCG_AI_Battle_Challenge/.kaggle_kernel')
META = json.loads((KD / 'kernel-metadata.json').read_text(encoding='utf-8'))
CODE = (KD / 'run_experiment.py').read_text(encoding='utf-8')

SHAPE = 'GPU T4 x2'
if '--shape' in sys.argv:
    SHAPE = sys.argv[sys.argv.index('--shape') + 1]

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
req.dataset_data_sources = ['daniel1547/ptcg-tensors', 'daniel1547/ptcg-code']
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
