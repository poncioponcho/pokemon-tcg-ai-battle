# -*- coding: utf-8 -*-
"""probe_torch_p100.py — 独立诊断 kernel：P100 (sm_60) 与 torch 二进制兼容性

背景：run_experiment.py 的 cu118 降级链连续两次失败（rc=1），stderr 被截断看不清。
本脚本隔离探测（不挂 14GB 数据，2-3 分钟）：
  1. 预装 torch 的 get_arch_list() —— 是否含 sm_60
  2. 若缺 → pip install pin 版 torch==2.5.1+cu118 torchvision==0.20.1+cu118
  3. 打印新 __version__ + get_arch_list() + cuda probe matmul
  4. 完整 stderr 输出（不截断）
结论打印为标志行，供决策：
  P100_OK    sm_60 可用，可 GPU 训练
  P100_FAIL  sm_60 仍不可用，需其他路径
"""
import subprocess
import sys

print('=== PROBE: 预装 torch ===', flush=True)
import torch
print('torch', torch.__version__, flush=True)
print('cuda available:', torch.cuda.is_available(), flush=True)
if torch.cuda.is_available():
    print('device:', torch.cuda.get_device_name(0), flush=True)
    print('capability:', torch.cuda.get_device_capability(0), flush=True)
try:
    print('preinstalled arch_list:', torch.cuda.get_arch_list(), flush=True)
except Exception as e:
    print('get_arch_list FAIL:', repr(e), flush=True)

# 预装 torch 探测 matmul（预期 fail no kernel image）
try:
    x = torch.zeros(8, device='cuda')
    (x + 1).sum().item()
    torch.cuda.synchronize()
    print('preinstalled cuda probe: OK', flush=True)
except Exception as e:
    print('preinstalled cuda probe FAIL:', repr(e)[:400], flush=True)

print('=== PROBE: pin 版 torch 2.5.1+cu118 ===', flush=True)
r = subprocess.run(
    [sys.executable, '-m', 'pip', 'install', '--quiet',
     '--index-url', 'https://download.pytorch.org/whl/cu118',
     'torch==2.5.1', 'torchvision==0.20.1'],
    capture_output=True, text=True)
print('pip install rc=', r.returncode, flush=True)
if r.returncode != 0:
    print('pip stderr tail:', (r.stderr or r.stdout)[-2000:], flush=True)
    print('P100_FAIL: pip install pin 版失败', flush=True)
    sys.exit(1)
print('pip ok', flush=True)

print('=== PROBE: 子进程验证 pin 版 ===', flush=True)
check_code = (
    "import torch;"
    "print('VERSION', torch.__version__);"
    "print('ARCH', torch.cuda.get_arch_list());"
    "print('DEV', torch.cuda.get_device_name(0));"
    "print('CAP', torch.cuda.get_device_capability(0));"
    "torch.zeros(8, device='cuda') + 1;"
    "torch.cuda.synchronize();"
    "print('P100_OK: cuda matmul on pin torch OK')"
)
r2 = subprocess.run([sys.executable, '-c', check_code],
                    capture_output=True, text=True, timeout=180)
print('verify rc=', r2.returncode, flush=True)
print('--- stdout ---', flush=True)
print(r2.stdout[-2000:], flush=True)
print('--- stderr ---', flush=True)
print(r2.stderr[-2000:], flush=True)
if r2.returncode == 0 and 'P100_OK' in r2.stdout:
    print('P100_OK', flush=True)
else:
    print('P100_FAIL', flush=True)
