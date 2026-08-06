# -*- coding: utf-8 -*-
"""lab_render.py — Hermes Lab Loop L1：experiments.yaml 出队 → 渲染 kernel 配置

把一个 queued 实验渲染进 .kaggle_kernel/run_experiment.py（模板化 TRAIN_ARGS），
并写实验上下文供 arena_runner 关联。

用法:
  python3 lab_render.py --id exp001
  # 读取 experiments/experiments.yaml 的 exp001，生成:
  #   .kaggle_kernel/run_experiment.py        (TRAIN_ARGS 注入实验超参)
  #   .kaggle_kernel/experiment_ctx.json      (实验 id/name/arena 配置，供 kernel 内使用)
  #   experiments/exp001.rendered             (渲染完成标记)
"""
import argparse
import json
import sys
from pathlib import Path

PROJ = Path('/Users/seyonmacbook/Desktop/Pokemon_TCG_AI_Battle_Challenge')
EXP_DIR = PROJ / 'experiments'
YAML = EXP_DIR / 'experiments.yaml'
KD = PROJ / '.kaggle_kernel'
RENDER_SRC = KD / 'run_experiment.py'
CTX = KD / 'experiment_ctx.json'

# TRAIN_ARGS 中的参数名 → train_v2 CLI 参数名
KEY_MAP = {
    'teacher_hidden': '--teacher-hidden',
    'teacher_blocks': '--teacher-blocks',
    'teacher_dropout': '--teacher-dropout',
    'student_hidden': '--student-hidden',
    'distill_temp': '--distill-temp',
    'distill_alpha': '--distill-alpha',
    'bs': '--bs',
    'lr': '--lr',
    'weight_decay': '--weight-decay',
    'tau': '--tau',
    'wcap': '--wcap',
    'epochs_bc': '--epochs-bc',
    'epochs_awr': '--epochs-awr',
    'epochs_distill': '--epochs-distill',
    'seed': '--seed',
}


def load_yaml():
    """无第三方 yaml 依赖时用简单解析（骨架期够用；有 pyyaml 则优先）。"""
    try:
        import yaml
        return yaml.safe_load(YAML.read_text(encoding='utf-8'))
    except ImportError:
        pass
    # 兜底：极简 yaml 子集解析（本项目结构固定）
    import re
    data = {'version': 1, 'meta': {}, 'experiments': []}
    cur = None
    for line in YAML.read_text(encoding='utf-8').splitlines():
        line = line.rstrip()
        if not line or line.lstrip().startswith('#'):
            continue
        m = re.match(r'^(\s*)(\S+):\s*(.*)$', line)
        if not m:
            continue
        indent, key, val = m.group(1), m.group(2), m.group(3).strip()
        if key == 'experiments' and val == '':
            continue
        if indent == '' and key in ('version', 'meta', 'experiments'):
            if key == 'experiments':
                pass
            continue
        # 实验条目: "  - id: exp001"
        if key == '- id':
            if cur is not None:
                data['experiments'].append(cur)
            cur = {'id': val}
            continue
        if cur is not None:
            if val == '':
                cur[key] = {}
                cur = None  # 简化：嵌套结构不深入解析
            else:
                cur[key] = val
    if cur is not None:
        data['experiments'].append(cur)
    return data


def render(exp_id: str) -> int:
    data = load_yaml()
    exp = next((e for e in data.get('experiments', []) if e.get('id') == exp_id), None)
    if exp is None:
        print(f'ERROR: 实验 {exp_id} 不在队列中')
        return 1
    if exp.get('status') != 'queued':
        print(f'ERROR: 实验 {exp_id} 状态为 {exp.get("status")}（仅 queued 可渲染）')
        return 1

    src = RENDER_SRC.read_text(encoding='utf-8')
    train = exp.get('train', {})
    flags = []
    for k, v in train.items():
        cli = KEY_MAP.get(k)
        if cli is None:
            print(f'WARN: 忽略未映射参数 {k}')
            continue
        if isinstance(v, bool):
            flags.append(f"'{cli}'") if v else None
        else:
            flags.append(f"'{cli}', '{v}'")
    body = ',\n'.join('        ' + f for f in flags)
    block = f"TRAIN_ARGS = [\n{body},\n    ]"
    # 替换现有 TRAIN_ARGS 定义块
    import re
    new_src = re.sub(r'TRAIN_ARGS = \[[^\]]*\]', block, src, count=1, flags=re.S)
    if new_src == src:
        print('ERROR: 未找到 TRAIN_ARGS 定义块，无法渲染')
        return 1
    RENDER_SRC.write_text(new_src, encoding='utf-8')

    ctx = {
        'experiment': exp_id,
        'name': exp.get('name', ''),
        'train': train,
        'arena': exp.get('arena', {}),
    }
    CTX.write_text(json.dumps(ctx, ensure_ascii=False, indent=2), encoding='utf-8')
    (EXP_DIR / f'{exp_id}.rendered').touch()
    print(f'渲染完成: {exp_id} → {RENDER_SRC.name} (+{CTX.name})')
    print(f'  超参: {json.dumps(train, ensure_ascii=False)}')
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--id', required=True)
    args = ap.parse_args()
    sys.exit(render(args.id))


if __name__ == '__main__':
    main()
