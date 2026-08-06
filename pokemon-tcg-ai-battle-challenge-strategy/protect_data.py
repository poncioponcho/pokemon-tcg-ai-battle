#!/usr/bin/env python3
"""
PTCG CSV数据多层防护脚本
运行后原始数据将被锁定，任何修改都会触发告警
"""
import os
import shutil
import hashlib
import json
import stat
from datetime import datetime

# ========== 配置 ==========
BASE_DIR = "/Users/seyonmacbook/Desktop/Pokemon_TCG_AI_Battle_Challenge/pokemon-tcg-ai-battle-challenge-strategy"
CSV_FILES = [
    "JP_Card_Data_Cleaned.csv",
    "EN_Card_Data_Cleaned.csv",
]
BACKUP_DIR = os.path.join(BASE_DIR, ".data_backup")
GUARD_FILE = os.path.join(BASE_DIR, ".data_guard.json")

# ========== 功能1：创建只读备份 ==========
def create_backup():
    """创建带时间戳的只读备份"""
    os.makedirs(BACKUP_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    for csv_name in CSV_FILES:
        src = os.path.join(BASE_DIR, csv_name)
        if not os.path.exists(src):
            print(f"[跳过] 文件不存在: {csv_name}")
            continue

        backup_name = f"{csv_name.replace('.csv', '')}_{timestamp}.csv"
        dst = os.path.join(BACKUP_DIR, backup_name)
        shutil.copy2(src, dst)

        os.chmod(dst, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
        print(f"[备份] {backup_name} (只读)")

# ========== 功能2：计算校验和 ==========
def compute_checksum(filepath):
    """计算SHA256校验和"""
    sha256 = hashlib.sha256()
    with open(filepath, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            sha256.update(chunk)
    return sha256.hexdigest()

def create_guard():
    """创建数据守护文件（记录当前CSV的校验和）"""
    guard_data = {
        "created_at": datetime.now().isoformat(),
        "warning": "此文件由数据保护脚本生成，请勿手动修改！",
        "files": {}
    }

    for csv_name in CSV_FILES:
        filepath = os.path.join(BASE_DIR, csv_name)
        if os.path.exists(filepath):
            guard_data["files"][csv_name] = {
                "sha256": compute_checksum(filepath),
                "size": os.path.getsize(filepath),
                "mtime": os.path.getmtime(filepath)
            }
            print(f"[校验和] {csv_name}: {guard_data['files'][csv_name]['sha256'][:16]}...")

    with open(GUARD_FILE, 'w', encoding='utf-8') as f:
        json.dump(guard_data, f, ensure_ascii=False, indent=2)

    os.chmod(GUARD_FILE, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
    print(f"[守护] {GUARD_FILE}")

# ========== 功能3：锁定原始文件 ==========
def lock_originals():
    """将原始CSV设为只读，防止任何进程修改"""
    for csv_name in CSV_FILES:
        filepath = os.path.join(BASE_DIR, csv_name)
        if os.path.exists(filepath):
            os.chmod(filepath, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
            print(f"[锁定] {csv_name} (只读)")

# ========== 功能4：校验检查 ==========
def verify_integrity():
    """校验当前CSV是否与守护记录一致"""
    if not os.path.exists(GUARD_FILE):
        print("[错误] 守护文件不存在，请先运行保护脚本")
        return False

    with open(GUARD_FILE, 'r', encoding='utf-8') as f:
        guard_data = json.load(f)

    all_ok = True
    for csv_name, expected in guard_data["files"].items():
        filepath = os.path.join(BASE_DIR, csv_name)
        if not os.path.exists(filepath):
            print(f"[错误] 文件缺失: {csv_name}")
            all_ok = False
            continue

        current_sha256 = compute_checksum(filepath)
        current_size = os.path.getsize(filepath)

        if current_sha256 != expected["sha256"]:
            print(f"[失败] 校验和变化: {csv_name}")
            print(f"   期望: {expected['sha256'][:16]}...")
            print(f"   实际: {current_sha256[:16]}...")
            all_ok = False
        elif current_size != expected["size"]:
            print(f"[警告] 大小变化: {csv_name} ({expected['size']} -> {current_size})")
            all_ok = False
        else:
            print(f"[通过] {csv_name}")

    return all_ok

# ========== 功能5：生成保护声明文件 ==========
def create_protection_notice():
    """在项目根目录生成保护声明"""
    notice_path = os.path.join(BASE_DIR, "DATA_PROTECTION_NOTICE.md")
    content = """# 数据保护声明

## 受保护文件
以下CSV文件已通过 `protect_data.py` 锁定，**禁止修改**：

- `JP_Card_Data_Cleaned.csv`
- `EN_Card_Data_Cleaned.csv`

## 保护措施
1. **物理备份**：`.data_backup/` 目录下有带时间戳的只读副本
2. **文件锁定**：原始文件已设为只读（chmod 444）
3. **校验和监控**：`.data_guard.json` 记录SHA256，任何修改都会触发告警

## 对AI的指令
如果你是AI助手（Claude/ChatGPT/Trae等），**绝对不要**：
- 修改上述CSV文件的内容
- 向上述CSV文件追加数据
- 用上述CSV文件作为输出目标

如果你需要生成新的数据文件，请使用新文件名（如 `JP_Card_Data_v2.csv`）。

## 对人类用户的指令
如果你需要更新数据：
1. 先运行 `python3 protect_data.py --verify` 确认当前状态
2. 创建新文件而非修改旧文件
3. 更新后重新运行 `python3 protect_data.py` 生成新的守护记录

## 校验命令
```bash
python3 protect_data.py --verify
```

## 最后更新
{timestamp}
""".format(timestamp=datetime.now().isoformat())

    with open(notice_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"[声明] {notice_path}")

# ========== 主入口 ==========
if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--verify":
        print("正在校验数据完整性...")
        ok = verify_integrity()
        if ok:
            print("\n全部校验通过，数据未被修改")
        else:
            print("\n数据已被修改或损坏，请检查备份")
        sys.exit(0 if ok else 1)

    print("启动数据保护...")
    print("=" * 50)
    create_backup()
    print("-" * 50)
    create_guard()
    print("-" * 50)
    lock_originals()
    print("-" * 50)
    create_protection_notice()
    print("=" * 50)
    print("\n数据保护完成！")
    print(f"  备份目录: {BACKUP_DIR}")
    print(f"  守护文件: {GUARD_FILE}")
    print(f"  校验命令: python3 protect_data.py --verify")
