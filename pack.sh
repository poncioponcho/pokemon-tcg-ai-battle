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

# ---- 3.5 交叉校验: main.py DECK / deck.csv / 内联牌组 / 卡池 四源一致 ----
# [审计-H3] 原校验把 DECK(由 deck.csv 加载) 与 deck.csv 对比, 是同义校验恒通过;
# 现改为: (1) DECK==内联牌组 (2) 卡 ID 均在卡池 (3) 非能量卡同卡<=4 (4) 长度60
TMPD=$(mktemp -d)
tar -xzf submission.tar.gz -C "$TMPD"
if ! (cd "$TMPD" && python3 -c "
from collections import Counter
import main
deck = [int(l.strip()) for l in open('deck.csv') if l.strip()]
if len(main.DECK) != 60 or len(deck) != 60:
    raise SystemExit(f'DECK/deck.csv 长度异常: {len(main.DECK)}/{len(deck)}')
if sorted(main.DECK) != sorted(deck):
    raise SystemExit('main.py DECK 与 deck.csv 内容不一致!')
if sorted(main.DECK) != sorted(main._INLINE_DECK):
    raise SystemExit('deck.csv 与 main.py 内联牌组 _INLINE_DECK 漂移!')
unknown = [cid for cid in set(main.DECK)
           if cid not in main._CARD_DB and cid not in main._TRAINER_IDS]
if unknown:
    raise SystemExit(f'卡 ID 不在卡池中: {sorted(unknown)}')
cnt = Counter(main.DECK)
over = [(cid, n) for cid, n in cnt.items()
        if not main._CARD_DB.get(cid, {}).get('is_energy') and n > 4]
if over:
    raise SystemExit(f'非能量卡超 4 张限制: {over}')
print('[OK] DECK == deck.csv == _INLINE_DECK, 全部卡 ID 在卡池, 非能量卡<=4 (60 张)')
"); then
  echo "[错误] 牌组一致性/合法性校验失败"
  rm -rf "$TMPD"
  exit 1
fi
rm -rf "$TMPD"

# ---- 4. 输出结果 ----
echo "[完成] submission.tar.gz 已生成"
ls -lh submission.tar.gz
echo "[内容] 压缩包内文件："
tar -tzf submission.tar.gz
