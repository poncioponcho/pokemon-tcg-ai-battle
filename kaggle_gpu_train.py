# -*- coding: utf-8 -*-
"""
Kaggle GPU 一体化训练脚本（Teacher→Distill→导出 npz）
=====================================================

用法（Kaggle Notebook）：
  1. Notebook 设置：Accelerator = GPU P100/T4，Internet = On（首次）
  2. Add Data 挂载两个私有 Dataset：
     - ptcg-tensors: 内含 ptcg_tensors.tar.gz（本地 inference/dataset/data/ 打包）
     - ptcg-code:    内含 ptcg_code.tar.gz（本地 inference/dataset/*.py + splits/ 打包）
  3. 把本文件内容粘贴到 notebook cell，或作为 .py 上传后 %run
  4. Save & Run All (Commit) —— 关闭标签页后后台继续跑

断点续跑：
  - 每 epoch 自动写 /kaggle/working/ckpt/ckpt_v2_last.pt（含 optimizer/AMP/RNG）
  - Session 到 9h 上限被掐断后：新建 notebook，Add Data 选「Your Work」里
    上次 notebook 的 output，把 ckpt 目录挂进来，重跑本脚本即自动续训
  - 续跑检测：代码解压后若发现工作区已存在 ckpt_v2_last.pt 会直接从断点开始

本地打包命令（在仓库根目录执行）：
  tar -czf ptcg_tensors.tar.gz -C inference/dataset/data \
      states_u8.npy scalars.npy opts_u8.npy labels.npy masks.npy \
      meta.npy episode_ids.npy meta.json
  tar -czf ptcg_code.tar.gz -C inference/dataset \
      train_bc.py train_v2.py model_v2.py export_student.py \
      mlops_registry.py card_vocab.py card_vocab_v1.json \
      -C ../.. inference/dataset/splits
"""

import json
import os
import shutil
import subprocess
import sys
import tarfile
import time
from pathlib import Path

WORK = Path('/kaggle/working')
DATA_DIR = WORK / 'data'
CODE_DIR = WORK / 'ptcg_code'
CKPT_DIR = WORK / 'ckpt'
OUT_DIR = WORK / 'output'

# 训练超参（30h/周预算内：单配置全流程 T4 约 40-70 分钟）
TRAIN_ARGS = [
    '--stage', 'all',
    '--device', 'auto',
    '--bs', '16384',
    '--epochs-bc', '8',
    '--epochs-awr', '5',
    '--epochs-distill', '8',
    '--early-stop-patience', '3',
    '--lr', '1e-3',
    '--seed', '42',
]


def log(msg):
    print(f'[{time.strftime("%H:%M:%S")}] {msg}', flush=True)


def dump_input_tree(root='/kaggle/input'):
    """打印挂载目录树，帮助定位 Dataset 挂载 / 文件名问题。"""
    root = Path(root)
    if not root.exists():
        print(f'[INPUT] {root} 不存在 — 未挂载任何 Dataset', flush=True)
        return
    for dirpath, dirnames, filenames in os.walk(root):
        rel = Path(dirpath).relative_to(root)
        indent = '  ' * len(rel.parts)
        print(f'{indent}{rel.name}/', flush=True)
        for f in sorted(filenames)[:30]:
            print(f'{indent}  {f}', flush=True)
        if len(filenames) > 30:
            print(f'{indent}  ...({len(filenames) - 30} more)', flush=True)


def find_in_input(*patterns):
    """宽松查找：先精确名、再子串包含；返回第一个命中的文件。

    Kaggle Dataset 挂载后文件名可能被规范化（大小写/后缀），
    用子串匹配提高容错；找不到返回 None。
    """
    for p in Path('/kaggle/input').rglob('*'):
        if not p.is_file():
            continue
        name = p.name
        for pat in patterns:
            if name == pat or pat in name:
                return p
    return None


def untar(archive, dest):
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive) as tf:
        tf.extractall(dest)
    log(f'extracted {archive.name} -> {dest}')


def _find_input_dir(substr):
    """按子串找 /kaggle/input 下的目录（Kaggle 会把 .tar.gz 自动解包成目录）。"""
    inp = Path('/kaggle/input')
    try:
        entries = list(inp.iterdir())
    except Exception as e:
        log(f'[diag] /kaggle/input 遍历失败: {e}')
        return None
    log(f'[diag] /kaggle/input 共 {len(entries)} 项: {[e.name for e in entries][:12]}')
    for d in entries:
        if d.is_dir() and substr in d.name:
            log(f'[diag] 命中目录: {d} (isdir={d.is_dir()})')
            try:
                sub = sorted(p.name for p in d.iterdir() if p.is_file())[:12]
                log(f'[diag] 该目录文件: {sub}')
            except Exception as e:
                log(f'[diag] 该目录遍历失败: {e}')
            return d
    log(f'[diag] 未找到含 "{substr}" 的目录')
    return None


def _load_tensors():
    """加载张量：优先已解包目录，其次 .tar.gz 解包，最后尝试文件名子串匹配。

    meta.json 仅作说明性元数据（train_v2.py 只依赖 meta.npy 等 npy），
    不作为必需项，避免上传版本缺该文件时误报。
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    NEEDED = ('states_u8.npy', 'scalars.npy', 'opts_u8.npy', 'labels.npy',
              'masks.npy', 'meta.npy', 'episode_ids.npy')
    OPTIONAL = ('meta.json',)
    if all((DATA_DIR / n).exists() for n in NEEDED):
        return True
    # 1) Kaggle 自动解包：/kaggle/input/ptcg-tensors/*.npy 平铺
    ds = _find_input_dir('ptcg-tensors')
    if ds and (ds / 'states_u8.npy').exists():
        for name in NEEDED + OPTIONAL:
            if not (DATA_DIR / name).exists() and (ds / name).exists():
                shutil.copy(ds / name, DATA_DIR / name)
        log(f'tensors: loaded from unpacked dataset {ds.name} '
            f'({len(NEEDED)} files)')
        return all((DATA_DIR / n).exists() for n in NEEDED)
    # 2) tar.gz 原样挂载
    tgz = find_in_input('ptcg_tensors.tar.gz')
    if tgz:
        untar(tgz, DATA_DIR)
        return all((DATA_DIR / n).exists() for n in NEEDED)
    return False


def _load_code():
    """加载训练代码：优先已解包目录，其次 tar.gz。"""
    CODE_DIR.mkdir(parents=True, exist_ok=True)
    NEEDED = ('train_v2.py', 'train_bc.py', 'model_v2.py', 'export_student.py',
              'mlops_registry.py', 'card_vocab.py', 'card_vocab_v1.json')
    if all((CODE_DIR / n).exists() for n in NEEDED):
        return True
    ds = _find_input_dir('ptcg-code')
    if ds and (ds / 'train_v2.py').exists():
        for name in NEEDED:
            if not (CODE_DIR / name).exists() and (ds / name).exists():
                shutil.copy(ds / name, CODE_DIR / name)
        # splits 摊平（若 dataset 里带 inference/dataset/splits 结构）
        for cand in (ds / 'inference' / 'dataset' / 'splits', ds / 'splits'):
            if cand.is_dir() and not (CODE_DIR / 'splits').exists():
                shutil.copytree(str(cand), str(CODE_DIR / 'splits'))
                break
        log(f'code: loaded from unpacked dataset {ds.name}')
        return all((CODE_DIR / n).exists() for n in NEEDED)
    tgz = find_in_input('ptcg_code.tar.gz')
    if tgz:
        untar(tgz, CODE_DIR)
        return all((CODE_DIR / n).exists() for n in NEEDED)
    return False


def prepare():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CODE_DIR.mkdir(parents=True, exist_ok=True)
    CKPT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if not _load_tensors():
        print('ERROR: 未找到训练张量（ptcg-tensors 未挂载或文件名异常）', flush=True)
        print('下面打印 /kaggle/input 实际挂载内容：', flush=True)
        dump_input_tree()
        raise SystemExit('missing tensors: 请对照上方目录树排查。'
                         'Kaggle 会把上传的 .tar.gz 自动解包成平铺文件，'
                         '脚本已兼容两种情况（解包目录 / tar.gz 原样）。')
    if not _load_code():
        print('ERROR: 未找到训练代码（ptcg-code 未挂载或文件名异常）', flush=True)
        dump_input_tree()
        raise SystemExit('missing code: 请对照上方目录树排查 ptcg-code Dataset 挂载/命名。')

    # splits 目录（tar 解包路径兜底摊平）
    nested = CODE_DIR / 'inference' / 'dataset' / 'splits'
    splits = CODE_DIR / 'splits'
    if nested.exists() and not splits.exists():
        shutil.move(str(nested), str(splits))

    # splits 目录（tar 里若带 inference/dataset/splits 结构，摊平）
    nested = CODE_DIR / 'inference' / 'dataset' / 'splits'
    splits = CODE_DIR / 'splits'
    if nested.exists() and not splits.exists():
        shutil.move(str(nested), str(splits))

    # 断点续跑：把上次 output 挂载进来的 ckpt 恢复到工作位置
    prev_ckpt = find_in_input('ckpt_v2_last.pt')
    work_ckpt = CKPT_DIR / 'ckpt_v2_last.pt'
    if prev_ckpt and not work_ckpt.exists():
        shutil.copy(prev_ckpt, work_ckpt)
        log(f'resume checkpoint restored from {prev_ckpt}')
    for name in ('teacher_best.pt', 'student_best.pt'):
        prev = find_in_input(name)
        if prev and not (CKPT_DIR / name).exists():
            shutil.copy(prev, CKPT_DIR / name)


def check_gpu():
    import torch
    ok = torch.cuda.is_available()
    name = torch.cuda.get_device_name(0) if ok else 'CPU-ONLY'
    log(f'torch {torch.__version__} | cuda_available={ok} | device={name}')
    if not ok:
        log('WARNING: GPU not detected — Accelerator 未开启？将用 CPU 慢跑')
    return ok


def run(cmd, cwd):
    log('+ ' + ' '.join(cmd))
    proc = subprocess.run(cmd, cwd=str(cwd))
    if proc.returncode != 0:
        raise SystemExit(f'command failed ({proc.returncode}): {cmd}')


def main():
    prepare()
    check_gpu()
    py = sys.executable

    train_cmd = [
        py, 'train_v2.py',
        '--data-dir', str(DATA_DIR),
        '--ckpt-path', str(CKPT_DIR / 'ckpt_v2_last.pt'),
        '--teacher-best', str(CKPT_DIR / 'teacher_best.pt'),
        '--student-best', str(CKPT_DIR / 'student_best.pt'),
        '--logs-dir', str(OUT_DIR),
        '--split-manifest', str(CODE_DIR / 'splits' / 'episode_splits.jsonl'),
        '--canary-manifest', str(CODE_DIR / 'splits' / 'rolling_canary.json'),
    ] + TRAIN_ARGS
    run(train_cmd, CODE_DIR)

    run([py, 'export_student.py',
         '--student', str(CKPT_DIR / 'student_best.pt'),
         '--out', str(OUT_DIR / 'model_student.npz')], CODE_DIR)

    # 训练报告归档到 output（notebook 结束后可下载/作为下次 input）
    for name in ('train_v2_report.json', 'model_student.npz',
                 'teacher_best.pt', 'student_best.pt', 'ckpt_v2_last.pt'):
        src = (OUT_DIR / name) if (OUT_DIR / name).exists() else (CKPT_DIR / name)
        if src.exists():
            log(f'artifact ready: {src} ({src.stat().st_size/1024:.0f} KiB)')

    log('DONE. 下载 output/model_student.npz 回本地，放入仓库根目录后 bash pack.sh 即可带模型提交。')
    log('若 session 中断：新 notebook 挂载本次 output 作为 input，重跑本脚本自动续训。')


if __name__ == '__main__':
    main()
