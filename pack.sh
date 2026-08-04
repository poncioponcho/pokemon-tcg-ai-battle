#!/usr/bin/env bash
# =====================================================================
# pack.sh —— 打包提交文件为 submission.tar.gz
# =====================================================================
# Kaggle 提交要求：submission.tar.gz，顶层目录含 main.py 和 deck.csv，
# 大小不超过 197.7 MiB。本脚本只打包运行所需的 main.py + deck.csv，
# 不打包开发文件（sdk/、gen_deck.py、CardPool.csv、test_agent.py 等）。
# =====================================================================
set -euo pipefail

# 切换到脚本所在目录（确保相对路径正确）
cd "$(dirname "$0")"

# ---- 1. 检查必需文件 ----
for f in main.py deck.csv; do
  if [[ ! -f "$f" ]]; then
    echo "[错误] 缺少必需文件：$f"
    exit 1
  fi
done

# ---- 2. 校验 deck.csv 恰好 60 张卡 ----
n=$(python3 -c "print(sum(1 for l in open('deck.csv') if l.strip()))")
if [[ "$n" != "60" ]]; then
  echo "[错误] deck.csv 必须为 60 行，当前 $n 行"
  exit 1
fi

# ---- 3. 打包 ----
rm -f submission.tar.gz
# [v19 修复] 使用 COPYFILE_DISABLE=1 排除 macOS 元数据文件 (._*)
# tar 从当前目录打包，保证 main.py / deck.csv 在压缩包顶层
COPYFILE_DISABLE=1 tar -czf submission.tar.gz main.py deck.csv

# ---- 3.5 交叉校验: main.py 内联 DECK 与 deck.csv 必须一致 ----
# 引擎实际使用 agent 返回的牌组 (main.py DECK), deck.csv 是提交校验基准,
# 双源漂移会导致"校验通过但实际打的是另一副牌"。
TMPD=$(mktemp -d)
tar -xzf submission.tar.gz -C "$TMPD"
if ! (cd "$TMPD" && python3 -c "
import main
deck = [int(l.strip()) for l in open('deck.csv') if l.strip()]
if len(main.DECK) != 60 or len(deck) != 60:
    raise SystemExit(f'DECK/deck.csv 长度异常: {len(main.DECK)}/{len(deck)}')
if sorted(main.DECK) != sorted(deck):
    raise SystemExit('main.py DECK 与 deck.csv 内容不一致!')
print('[OK] main.py DECK 与 deck.csv 一致 (60 张)')
"); then
  echo "[错误] DECK/deck.csv 一致性校验失败"
  rm -rf "$TMPD"
  exit 1
fi
rm -rf "$TMPD"

# ---- 4. 输出结果 ----
echo "[完成] submission.tar.gz 已生成"
ls -lh submission.tar.gz
echo "[内容] 压缩包内文件："
tar -tzf submission.tar.gz
