# -*- coding: utf-8 -*-
"""arena_pool 冻结对手注册表

对手池是 arena 评测的"环境"，任何实验不得修改（防 reward hacking）。
注册表记录每个对手的来源 + 校验和；实际 agent 代码冻结在 arena_pool/<name>.py。

v23_2 与 v22_5 为规则基线快照；random/first 为 kaggle_environments 内建。
首次使用某个文件型对手时，运行 snapshot_opponents.py 从 main.py 生成冻结快照。
"""
import json
import hashlib
from pathlib import Path
from typing import Any

POOL = Path(__file__).resolve().parent
REGISTRY = POOL / 'opponents.json'

# 内建对手（kaggle_environments 自带）
BUILTIN = {'random', 'first'}

REGISTRY_DATA: dict[str, Any] = {
    'version': 1,
    'frozen_at': None,
    'note': '对手池冻结：arena 评测环境，L3 不得修改。文件型对手由 snapshot_opponents.py 生成。',
    'opponents': {
        'v23_2': {'type': 'file', 'path': 'arena_pool/v23_2_rules.py', 'sha256': None},
        'v22_5': {'type': 'file', 'path': 'arena_pool/v22_5_rules.py', 'sha256': None},
        # [2026-08-13] config A 行为等价 pristine 镜像（三 flag 全 False，内联 deck 2a541d7b，
        # 溯源见文件头）。新增而非覆盖——旧镜像保留，drift 对照用（D0 教训）。
        'configA_pristine_79653e2c63b1': {'type': 'file', 'path': 'arena_pool/configA_pristine_79653e2c63b1.py', 'sha256': None},
        'random': {'type': 'builtin', 'module': 'kaggle_environments', 'agent': 'random'},
        'first': {'type': 'builtin', 'module': 'kaggle_environments', 'agent': 'first'},
    },
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()[:16]


def refresh() -> None:
    """重算文件型对手的校验和并落盘注册表。"""
    reg = REGISTRY_DATA
    opponents = reg.get('opponents')
    if not isinstance(opponents, dict):
        raise TypeError("registry opponents must be an object")
    for name, raw_spec in opponents.items():
        if not isinstance(raw_spec, dict):
            raise TypeError(f"registry opponent {name!r} must be an object")
        spec: dict[str, Any] = raw_spec
        if spec.get('type') == 'file':
            # [bugfix] spec['path'] 形如 'arena_pool/v23_2_rules.py'，POOL 已是
            # experiments/ 目录，旧代码再 strip 前缀导致解析到 experiments/v23_2_rules.py
            # （不存在）→ sha256 恒为 None，冻结校验形同虚设。
            raw_path = spec.get('path')
            if not isinstance(raw_path, str):
                raise TypeError(f"registry opponent {name!r} has invalid path")
            p = POOL / raw_path
            spec['sha256'] = sha256(p) if p.exists() else None
    reg['frozen_at'] = str(__import__('datetime').datetime.now())
    REGISTRY.write_text(json.dumps(reg, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'注册表已刷新 → {REGISTRY}')


if __name__ == '__main__':
    refresh()
