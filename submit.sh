#!/usr/bin/env bash
# =====================================================================
# submit.sh —— 提交 submission.tar.gz 到 Kaggle 并查看状态
# =====================================================================
# 使用 KGAT token（~/.kaggle/access_token）直接调 REST API，
# 绕过 Kaggle CLI（v1.7.4.5 不支持 KGAT 格式）。
# =====================================================================
set -euo pipefail

cd "$(dirname "$0")"

COMMAND="${1:-help}"

case "$COMMAND" in
  submit)
    echo "=== 提交 submission.tar.gz 到 pokemon-tcg-ai-battle ==="
    python3 submit.py submit
    ;;

  status)
    echo "=== 最近提交记录 ==="
    python3 submit.py status
    ;;

  leaderboard)
    echo "=== 当前天梯排名 ==="
    python3 submit.py leaderboard
    ;;

  download-cardpool)
    echo "=== 下载比赛数据（含 CardPool.csv）==="
    python3 submit.py download-cardpool
    echo ""
    echo "如果这个命令没返回数据，说明比赛数据在 Kaggle 上只能通过 Notebook 挂载 /kaggle/input/ 访问。"
    echo "你可以在 Kaggle 上创建一个 Notebook，选择比赛数据源，然后用 !cp 命令下载。"
    ;;

  validate-local)
    echo "=== 本地验证提交包 ==="
    if [[ ! -f submission.tar.gz ]]; then
      echo "错误：找不到 submission.tar.gz"
      echo "请先运行 bash pack.sh"
      exit 1
    fi
    echo "文件大小：$(du -h submission.tar.gz | cut -f1)"
    echo "包内文件："
    tar -tzf submission.tar.gz
    echo ""
    if tar -xzf submission.tar.gz -O main.py | grep -q "def agent"; then
      echo "✓ main.py 包含 agent 函数"
    else
      echo "✗ main.py 缺少 agent 函数！"
      exit 1
    fi
    n=$(tar -xzf submission.tar.gz -O deck.csv | grep -c .)
    if [[ "$n" == "60" ]]; then
      echo "✓ deck.csv 有 60 张卡"
    else
      echo "✗ deck.csv 应有 60 行，实有 $n 行"
      exit 1
    fi
    echo "本地验证通过 ✓ 可以提交了"
    ;;

  help|*)
    echo "用法: bash submit.sh <命令>"
    echo ""
    echo "命令:"
    echo "  submit             提交 submission.tar.gz"
    echo "  status             查看最近提交状态"
    echo "  leaderboard        查看天梯排名"
    echo "  download-cardpool  下载比赛数据信息"
    echo "  validate-local     本地验证提交包"
    echo "  help               显示此帮助"
    ;;
esac