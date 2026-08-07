# -*- coding: utf-8 -*-
"""
Kaggle 提交客户端 —— 使用 KGAT token 认证（kagglesdk 版）
========================================================
Kaggle CLI 1.7.4.5 不支持 KGAT token 格式，本脚本用 kagglesdk 完成：
  1. start_submission_upload → 获取签名上传 URL
  2. PUT 上传文件到签名 URL
  3. create_submission → 提交到比赛

用法: python3 submit.py <command>

命令:
  submit             提交 submission.tar.gz
  status             查看最近提交记录
  leaderboard        查看天梯排名
"""

import hashlib
import io
import json
import os
import sys
import tarfile
import time
import urllib.request

# ---------- 配置 ----------
TOKEN_FILE = os.path.expanduser("~/.kaggle/access_token")
COMPETITION = "pokemon-tcg-ai-battle"
WORK_DIR = os.path.dirname(os.path.abspath(__file__))
TAR_PATH = os.path.join(WORK_DIR, "submission.tar.gz")


def get_token():
    """获取 KGAT token，优先级：环境变量 > 文件"""
    token = os.environ.get("KAGGLE_API_TOKEN")
    if token:
        return token.strip()
    try:
        with open(TOKEN_FILE) as f:
            return f.read().strip()
    except OSError as e:
        print(f"错误：无法读取 token 文件 {TOKEN_FILE}: {e}")
        print("请设置环境变量 KAGGLE_API_TOKEN，或确认 ~/.kaggle/access_token 存在且可读。")
        raise SystemExit(1)


def get_client():
    """创建 kagglesdk 客户端（自动从 ~/.kaggle/kaggle_oauth.json 加载 KGAT token）

    [v22.3-fix] kagglehub 1.0.2 与 kagglesdk 0.1.28 版本不兼容
    (kagglehub 期望的 get_access_token_from_env 在新版不存在)，
    且 KaggleClient 不接受 api_token 参数 —— 直接依赖 kagglesdk
    自带的 oauth 文件加载机制。
    """
    from kagglesdk import KaggleClient, KaggleEnv
    return KaggleClient(env=KaggleEnv.PROD)


def _tar_main_sha() -> str:
    """计算 submission.tar.gz 内 main.py 的 sha256（无 tar 时返回 None）。"""
    try:
        with tarfile.open(TAR_PATH, "r:gz") as t:
            member = t.getmember("main.py")
            return hashlib.sha256(t.extractfile(member).read()).hexdigest()[:16]
    except Exception:
        return None


def cmd_submit():
    """提交 submission.tar.gz"""
    if not os.path.exists(TAR_PATH):
        print(f"错误：找不到 {TAR_PATH}，请先运行 bash pack.sh")
        return 1

    # [bugfix] 防呆：提交包可能来自旧 snapshot（如 submission/main.py 或 Aug-5 的
    # 旧 tar），与当前根 main.py 不一致时会静默提交旧 agent。若不一致直接拦截。
    try:
        with open(os.path.join(WORK_DIR, "main.py"), "rb") as f:
            live_sha = hashlib.sha256(f.read()).hexdigest()[:16]
        tar_sha = _tar_main_sha()
        if tar_sha is None:
            print(f"错误：{TAR_PATH} 内找不到 main.py，请重新 pack.sh")
            return 1
        if tar_sha != live_sha:
            print(f"错误：{TAR_PATH} 内的 main.py 与当前根 main.py 不一致！")
            print(f"  tar  sha256={tar_sha}")
            print(f"  live sha256={live_sha}")
            print("请先运行 bash pack.sh 重新打包，避免提交旧版 agent。")
            return 1
        print(f"校验通过：tar main.py 与根 main.py 一致 (sha256={live_sha})")
    except Exception as e:
        print(f"警告：提交包新鲜度校验跳过（{e}）")

    client = get_client()
    api = client.competitions.competition_api_client

    file_size = os.path.getsize(TAR_PATH)
    last_modified = int(os.path.getmtime(TAR_PATH))
    file_name = "submission.tar.gz"

    print(f"比赛: {COMPETITION}")
    print(f"文件: {file_name} ({file_size} bytes)")
    print()

    # ---- Step 1: 获取上传 URL ----
    print("=== Step 1/3: 获取上传 URL ===")
    from kagglesdk.competitions.types.competition_api_service import ApiStartSubmissionUploadRequest
    upload_req = ApiStartSubmissionUploadRequest()
    upload_req.competition_name = COMPETITION
    upload_req.content_length = file_size
    upload_req.last_modified_epoch_seconds = last_modified
    upload_req.file_name = file_name

    upload_resp = api.start_submission_upload(upload_req)
    blob_token = upload_resp.token
    create_url = upload_resp.create_url
    # [审计-M1] 不输出令牌内容, 仅输出长度与指纹
    token_fp = hashlib.sha256(blob_token.encode("utf-8")).hexdigest()[:8]
    print(f"  获取成功 → 上传令牌: {len(blob_token)} chars (sha256:{token_fp})")
    print()

    # ---- Step 2: PUT 上传文件 ----
    print("=== Step 2/3: 上传文件到 Google Cloud Storage ===")
    with open(TAR_PATH, "rb") as f:
        file_data = f.read()

    req = urllib.request.Request(create_url, data=file_data, method="PUT")
    req.add_header("Content-Type", "application/gzip")
    req.add_header("Content-Length", str(len(file_data)))
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            print(f"  上传完成 (HTTP {resp.status})")
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:300]
        print(f"  上传失败 ({e.code}): {body}")
        return 1
    except Exception as e:
        print(f"  上传异常: {e}")
        return 1
    print()

    # ---- Step 3: 提交到比赛 ----
    print("=== Step 3/3: 提交到比赛 ===")
    from kagglesdk.competitions.types.competition_api_service import ApiCreateSubmissionRequest
    submit_req = ApiCreateSubmissionRequest()
    submit_req.competition_name = COMPETITION
    submit_req.blob_file_tokens = blob_token
    submit_req.submission_description = f"PTCG Agent v23.1 P1策略调优+bug修复 {time.strftime('%Y-%m-%d_%H:%M')}"

    submit_resp = api.create_submission(submit_req)
    print(f"  提交成功！")
    print()

    print("✓ 完成！预计几分钟后验证赛开打")
    print("  查看状态: python3 submit.py status")
    return 0


def cmd_status():
    """查看最近提交记录"""
    client = get_client()
    api = client.competitions.competition_api_client

    from kagglesdk.competitions.types.competition_api_service import ApiListSubmissionsRequest
    req = ApiListSubmissionsRequest()
    req.competition_name = COMPETITION
    req.page = 1  # [v22.3-fix] kagglesdk 0.1.28 无 page_size 字段

    try:
        resp = api.list_submissions(req)
        subs = resp.submissions
        if not subs:
            print("暂无提交记录（提交后可能需要几分钟同步）")
            return
        print(f"{'时间':<22} {'状态':<14} {'分数':<8} {'描述'}")
        print("-" * 70)
        for s in subs:
            ts = str(s.date)[:19] if s.date else "-"
            status = s.status.name if s.status else "?"
            score = s.public_score or "-"
            desc = (s.description or "")[:40]
            print(f"{ts:<22} {status:<14} {score:<8} {desc}")
    except Exception as e:
        print(f"查询失败: {e}")


def cmd_leaderboard():
    """查看天梯排名"""
    client = get_client()
    api = client.competitions.competition_api_client

    from kagglesdk.competitions.types.competition_api_service import ApiGetLeaderboardRequest
    req = ApiGetLeaderboardRequest()
    req.competition_name = COMPETITION

    try:
        resp = api.get_leaderboard(req)
        rows = resp.submissions
        if not rows:
            print("天梯暂无数据（比赛尚未开始或提交未进入匹配池）")
            return
        print(f"{'#':<5} {'Team':<28} {'Score':<10} {'Date':<22}")
        print("-" * 65)
        for i, r in enumerate(rows, 1):
            team = (r.team_name or "?")[:28]
            score = str(r.score or "?")
            date = str(r.submission_date)[:19] if r.submission_date else "-"
            print(f"{i:<5} {team:<28} {score:<10} {date}")
        print()
        print(f"总计 {len(rows)} 支队伍")
    except Exception as e:
        print(f"查询失败: {e}")


def cmd_download_cardpool():
    """下载比赛数据（含 CardPool.csv）"""
    try:
        import kagglehub
        path = kagglehub.competition_download("pokemon-tcg-ai-battle")
        print(f"✓ 比赛数据已下载到: {path}")
        import glob
        for f in glob.glob(os.path.join(path, "**", "*"), recursive=True):
            if os.path.isfile(f):
                print(f"  {f}")
    except Exception as e:
        print(f"✗ 下载失败: {e}")
        print("提示: 比赛数据在 Kaggle 上通常只能通过 Notebook 挂载 /kaggle/input/ 访问。")
        print("可以创建一个 Notebook，选择比赛数据源，然后用 !cp 命令下载。")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return

    cmd = sys.argv[1]
    if cmd == "submit":
        sys.exit(cmd_submit())
    elif cmd == "status":
        cmd_status()
    elif cmd == "leaderboard":
        cmd_leaderboard()
    elif cmd == "download-cardpool":
        cmd_download_cardpool()
    else:
        print(f"未知命令: {cmd}")
        print(__doc__)


if __name__ == "__main__":
    main()