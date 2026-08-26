#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ptcg_replay_harvester.py — Kaggle simulation 竞赛 replay 批量下载 + 解析工具
===============================================================================

针对 pokemon-tcg-ai-battle（也兼容任何 Kaggle simulation 竞赛）。

前置条件
--------
1. 安装 Kaggle CLI:   pip install kaggle
2. 放置凭证:          ~/.kaggle/kaggle.json   （Kaggle 个人页 → Settings → API → Create New Token）
3. 重要：你必须在 Kaggle 网站上点过该竞赛的 "Join Competition" 并同意规则，
   否则 team-submissions / episodes / replay 接口会 403。

用法
----
# 第一步：扒取 Top 20 队伍、每队最佳提交、每个提交最近 30 局 replay
python3 ptcg_replay_harvester.py harvest --top 20 --max-episodes 30

# 日常（推荐）：增量 sync——每次都检查 episode ID，提交没变也能补下新对局；
# 另写 leaderboard_snapshot.csv + leaderboard_snapshots.jsonl（排名趋势/阶段快照）
python3 ptcg_replay_harvester.py incremental --top 20 --max-episodes 30

# 竞赛最后 48 小时榜单波动大：强制全量增量（--force），重查所有队伍但只下缺失对局
python3 ptcg_replay_harvester.py incremental --force

# 第二步：把所有 replay 解析成 JSONL（episodes.jsonl / steps.jsonl）+ 汇总 corpus.json
python3 ptcg_replay_harvester.py parse

# 第三步：快速统计（动作类型分布、对局长度、奖励分布等）
python3 ptcg_replay_harvester.py stats

输出目录结构
------------
ptcg_replays/
├── manifest.jsonl            # 抓取清单：team -> submission -> episodes（断点续传依据）
├── episode_catalog.jsonl     # episode_id 唯一目录：SHA256 + rank_at_capture
├── leaderboard_snapshots.jsonl
├── snapshots/                # 不覆盖的时间快照
├── raw/                      # 原始 replay：episode-<id>-replay.json
├── parsed/
│   ├── episodes.jsonl        # 每局一条：双方 agent、奖励、步数、胜负
│   ├── steps.jsonl           # 每步一条：observation / action / reward / status
│   └── corpus.json           # 汇总单文件（供 LLM / EDA 直接加载，体积较大）
└── harvest.log               # 运行日志

注意
----
- Kaggle API 限流规范（社区经验 + 本项目实测，官方未证实）：
  · 两次请求之间至少 5-10s，批量文件下载 3-5s/个，单线程优先；
  · 不是纯速率限制，而是动态累计配额：实测 ~4,000 次/UTC 日触发硬限流，
    恢复后剩余额度极小；--budget 默认 3000 留安全余量，耗尽自动停止（状态
    持久化到 out/request_budget.json，UTC 零点自动刷新）；
  · SSL 断连/超时是服务器压力早期信号（实测比 429 早 ~50 分钟），已计入压力；
  · 滑窗压力（最近 50 次/10 分钟）>5% 预警 → 间隔自适应上调，≥60% 长冷却 15 分钟；
  · 错峰下载：UTC 凌晨（北京时间上午）是低峰期，限流阈值相对宽松；
  · 断点续传：manifest.jsonl + raw/ 文件存在性双重去重，已下载 replay 不会重复请求；
  · 429 风暴后不要急着重启（实测重启 10 分钟 0 产出），等窗口恢复或预算刷新。
- 用网页爬虫抓 replay 更容易触发 WAF 限流，优先走 Kaggle API（本脚本即 CLI API）。
- replay JSON 的具体 schema 取决于竞赛环境版本，parser 对字段做了防御性处理；
  如果解析结果里 action 是空的，先 `python3 ptcg_replay_harvester.py inspect` 看真实结构。
"""

import argparse
import csv
import io
import json
import logging
import os
import re
import subprocess
import sys
import threading
import time
from collections import Counter, defaultdict, deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

try:
    from dataset.mlops_registry import (
        EpisodeCatalog,
        append_leaderboard_snapshot as append_registry_snapshot,
        competition_phase,
        phase_policy,
    )
    from dataset.replay_archive import finalize as finalize_replay_archive
except ImportError:  # Allows running the file from inside inference/ directly.
    from mlops_registry import (  # type: ignore
        EpisodeCatalog,
        append_leaderboard_snapshot as append_registry_snapshot,
        competition_phase,
        phase_policy,
    )
    from replay_archive import finalize as finalize_replay_archive  # type: ignore

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------
DEFAULT_COMP = "pokemon-tcg-ai-battle"
DEFAULT_DIR = Path("./ptcg_replays")
DEFAULT_DELAY = 5.0          # 每次 CLI 调用基础间隔（秒），社区建议 5-10s
MAX_RETRIES = 4              # 单个请求最大重试次数
BACKOFF_BASE = 8.0           # 限流退避基数（秒）: 8, 16, 32, 64
COOLDOWN_429_SECONDS = 900   # 高压力长冷却（秒）：窗口内停止消耗额度
BUDGET_DEFAULT = 3000        # 每日(UTC)请求预算：实测 ~4000 次触发硬限流，留安全余量
PRESSURE_WINDOW = 50         # 压力滑窗大小（最近 N 次请求）
PRESSURE_WINDOW_SECONDS = 600  # 滑窗时间窗（秒）
LEADERBOARD_PAGE_SIZE = 200  # 排行榜分页大小（CLI 上限 200）

log = logging.getLogger("harvester")


def finalize_replay_artifacts(out_dir, args):
    """Scan raw, repack, and verify the archive after every crawl."""
    if getattr(args, "no_finalize", False):
        log.warning("已显式跳过 replay finalize；下次 crawl 必须执行 finalize")
        return None
    archive_dir = Path(out_dir) / "archive"
    output = archive_dir / "raw_replays.jsonl.zst"
    result = finalize_replay_archive(
        Path(out_dir) / "raw",
        output,
        level=getattr(args, "archive_level", 5),
    )
    log.info(
        "✅ raw 全量校验+归档通过: %d records / %d steps / %d decisions -> %s",
        result["raw"]["records"],
        result["raw"]["steps"],
        result["raw"]["valid_decisions"],
        output,
    )
    return result


class RateGate:
    """
    滑窗自适应限流器（进程级共享，线程安全）：
    - 最近 PRESSURE_WINDOW 次请求/10 分钟内，429 与连接异常的占比 = 限流压力；
      · >5%  早期预警，间隔 ×1.15（连接异常 ×1.1，提前 50 分钟预警的例子）
      · >20% 升档，间隔 ×1.3
      · >50% 硬限流，间隔 ×1.6
      · ≥60% 长冷却 COOLDOWN_429_SECONDS，期间不消耗额度
    - 健康（压力≤2%）时间隔缓慢回降到 base；
    - 每日(UTC)请求预算持久化到 budget_file，耗尽后 run_kaggle 返回 -2，爬取停止。
    """

    def __init__(self, base_delay=DEFAULT_DELAY, budget=0, budget_file=None):
        self.base = max(3.0, float(base_delay))
        self.delay = self.base
        self.window = deque(maxlen=PRESSURE_WINDOW)  # [(ts, kind)], kind: ok/throttle/conn
        self.lock = threading.Lock()
        self.budget = budget
        self.budget_file = budget_file
        self._today_utc = None
        self._used = 0
        if budget:
            self._load_budget()

    def configure(self, base_delay, budget, budget_file):
        self.base = max(3.0, float(base_delay))
        self.delay = max(self.delay, self.base)
        self.budget = budget
        self.budget_file = budget_file
        if budget:
            self._load_budget()

    # ---- 预算 ----
    def _load_budget(self):
        if not self.budget_file:
            return
        try:
            state = json.loads(Path(self.budget_file).read_text(encoding="utf-8"))
        except Exception:
            state = {}
        today = time.strftime("%Y-%m-%d", time.gmtime())  # UTC 日，凌晨刷新
        self._today_utc = today
        self._used = state.get("used", 0) if state.get("date") == today else 0
        self._save_budget()
        log.info("今日(UTC)请求预算: %d/%d（%s）", self._used, self.budget,
                 "跨日已重置" if state.get("date") != today else "续用")

    def _save_budget(self):
        if not self.budget_file:
            return
        try:
            Path(self.budget_file).write_text(
                json.dumps({"date": self._today_utc, "used": self._used},
                           ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

    def exhausted(self):
        return bool(self.budget) and self._used >= self.budget

    def spend(self):
        if not self.budget:
            return
        self._used += 1
        if self._used % 25 == 0 or self._used == self.budget:
            self._save_budget()
            log.info("请求预算进度: %d/%d", self._used, self.budget)

    def save(self):
        """进程结束时调用，保证预算进度落盘。"""
        if self.budget:
            self._save_budget()

    # ---- 压力检测 ----
    def _pressure(self):
        now = time.time()
        recent = [k for t, k in self.window if now - t <= PRESSURE_WINDOW_SECONDS]
        if not recent:
            return 0.0
        bad = sum(1 for k in recent if k in ("throttle", "conn"))
        return bad / len(recent)

    def record(self, kind):
        """kind: ok / throttle / conn（连接异常=服务器压力早期信号）。返回当前压力。"""
        with self.lock:
            self.window.append((time.time(), kind))
            p = self._pressure()
            if kind == "throttle":
                if p > 0.5:
                    self.delay = min(self.delay * 1.6, 60.0)
                    log.warning("⚠ 限流压力 %.0f%%，间隔升至 %.1fs（硬限流）", p * 100, self.delay)
                elif p > 0.2:
                    self.delay = min(self.delay * 1.3, 40.0)
                    log.warning("限流压力 %.0f%%，间隔升至 %.1fs", p * 100, self.delay)
                elif p > 0.05:
                    self.delay = min(self.delay * 1.15, 30.0)
                    log.info("限流压力 %.0f%%，间隔升至 %.1fs（早期预警）", p * 100, self.delay)
            elif kind == "conn":
                self.delay = min(self.delay * 1.1, 25.0)
                log.warning("连接异常（服务器压力早期信号），间隔升至 %.1fs", self.delay)
            else:  # ok
                if p <= 0.02 and self.delay > self.base:
                    self.delay = max(self.base, self.delay * 0.85)
            return p

    def cooldown(self):
        """压力 ≥60% 时返回长冷却秒数，否则 0。"""
        with self.lock:
            p = self._pressure()
            if p >= 0.6:
                log.warning("限流压力 %.0f%% ≥ 60%%，长冷却 %ds", p * 100, COOLDOWN_429_SECONDS)
                return COOLDOWN_429_SECONDS
            return 0

    def sleep(self):
        time.sleep(self.delay)


_gate = RateGate()


# ---------------------------------------------------------------------------
# CLI 调用封装（滑窗限流 + 预算 + 退避 + 长冷却）
# ---------------------------------------------------------------------------
def run_kaggle(cmd_args, delay=DEFAULT_DELAY):
    """
    调用 kaggle CLI，返回 (returncode, stdout)。
    - 每次调用前按自适应间隔 sleep，429/连接异常计入滑窗压力；
    - 高压力 → 长冷却；预算耗尽 → 返回 -2（调用方停止爬取）。
    """
    gate = _gate
    cmd = ["kaggle"] + cmd_args
    for attempt in range(1, MAX_RETRIES + 1):
        if gate.exhausted():
            log.error("今日(UTC)请求预算 %d 已用尽，自动停止。加 --budget 调大或等 UTC 零点刷新。", gate.budget)
            return -2, ""
        gate.spend()
        gate.sleep()
        log.debug("RUN: %s (attempt %d)", " ".join(cmd), attempt)
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        except subprocess.TimeoutExpired:
            gate.record("conn")
            log.warning("请求超时（服务器压力），%ds 后重试 (%d/%d)", BACKOFF_BASE, attempt, MAX_RETRIES)
            time.sleep(BACKOFF_BASE)
            continue
        err = (proc.stderr or "").lower()

        if proc.returncode == 0 and proc.stdout.strip():
            gate.record("ok")
            return 0, proc.stdout

        # 429 / 明确限流 → 计入压力
        if any(k in err for k in ("429", "too many", "rate limit", "retry")):
            gate.record("throttle")
            cd = gate.cooldown()
            if cd:
                time.sleep(cd)
                continue
            wait = BACKOFF_BASE * (2 ** (attempt - 1))
            log.warning("限流，%ds 后重试 (%d/%d): %s",
                        wait, attempt, MAX_RETRIES, proc.stderr.strip()[:160])
            time.sleep(wait)
            continue

        # 网络/连接异常 = 服务器压力早期信号（实证：比 429 早 ~50 分钟出现）
        if any(k in err for k in ("connection", "timed out", "ssl", "unexpected eof", "eof")):
            gate.record("conn")
            wait = BACKOFF_BASE * (2 ** (attempt - 1))
            log.warning("网络异常（服务器压力），%ds 后重试 (%d/%d): %s",
                        wait, attempt, MAX_RETRIES, proc.stderr.strip()[:160])
            time.sleep(wait)
            continue

        # 403 一般是没 Join 竞赛或权限问题，重试无意义
        if "403" in err or "forbidden" in err or "permission" in err:
            log.error("403 拒绝（没 Join 竞赛？kaggle.json 失效？）: %s", proc.stderr.strip()[:300])
            return 403, proc.stdout

        log.error("命令失败 (rc=%d): %s\nstderr: %s",
                  proc.returncode, " ".join(cmd), proc.stderr.strip()[:300])
        return proc.returncode, proc.stdout

    log.error("重试 %d 次仍失败: %s", MAX_RETRIES, " ".join(cmd))
    return -1, ""


def parse_csv(stdout):
    """把 kaggle CLI -v 输出的 CSV 解析成 list[dict]，跳过表头告警行。"""
    lines = [l for l in stdout.splitlines() if l.strip()]
    # 找到真正的表头行（第一个含逗号的行，兼容 CLI 偶尔打印的 warning）
    for i, line in enumerate(lines):
        if "," in line:
            reader = csv.DictReader(io.StringIO("\n".join(lines[i:])))
            return [dict(r) for r in reader]
    return []


def find_col(row, *candidates):
    """在一行 dict 里按候选名（大小写/下划线不敏感）找列值。"""
    norm = {k.lower().replace("_", "").replace(" ", ""): v for k, v in row.items() if k}
    for cand in candidates:
        key = cand.lower().replace("_", "").replace(" ", "")
        if key in norm and norm[key] not in (None, ""):
            return norm[key]
    return None


# ---------------------------------------------------------------------------
# 前置检查
# ---------------------------------------------------------------------------
def check_prereqs():
    creds = Path.home() / ".kaggle" / "kaggle.json"
    if not creds.exists() and not os.environ.get("KAGGLE_API_TOKEN") \
            and not os.environ.get("KAGGLE_USERNAME"):
        sys.exit("❌ 未找到 ~/.kaggle/kaggle.json 或 KAGGLE_API_TOKEN 环境变量，请先配置 Kaggle 凭证。")
    rc, out = run_kaggle(["competitions", "list", "-s", DEFAULT_COMP[:10]], delay=0.5)
    if rc != 0:
        sys.exit("❌ kaggle CLI 调用失败，请检查网络与凭证（是否已 Join 该竞赛）。")


# ---------------------------------------------------------------------------
# HARVEST: 排行榜 → 提交 → 对局 → replay
# ---------------------------------------------------------------------------
def get_leaderboard(comp, top_n, delay, min_score=None, max_score=None):
    """
    分页拉取排行榜，返回 [(rank, team_id, team_name, score), ...]。
    - CLI 每页最多 200 行，输出带 "Next Page Token" 行，循环翻页直到取完；
    - top_n <= 0 表示全量；
    - min_score / max_score 按分数过滤（含边界，先全量再过滤，rank 保持原始排名）。
    """
    teams, seen = [], set()
    page_token, page = None, 0
    while True:
        cmd = ["competitions", "leaderboard", comp, "-s", "-v",
               "--page-size", str(LEADERBOARD_PAGE_SIZE)]
        if page_token:
            cmd += ["--page-token", page_token]
        rc, out = run_kaggle(cmd, delay)
        if rc == -2:
            sys.exit("❌ 今日(UTC)请求预算用尽，自动停止。加 --budget 调大或等 UTC 零点刷新。")
        if rc != 0:
            sys.exit("❌ 拉取排行榜失败。确认竞赛 slug 正确且已 Join。")

        m = re.search(r"Next\s+Page\s+Token\s*=\s*(\S+)", out)
        page_token = m.group(1) if m else None

        for row in parse_csv(out):
            tid = find_col(row, "teamId", "team_id", "id")
            if not tid or str(tid) in seen:
                continue
            seen.add(str(tid))
            teams.append((len(seen), str(tid).strip(),
                          find_col(row, "teamName", "team_name", "name") or "?",
                          find_col(row, "score", "publicScore") or "?"))

        log.info("排行榜分页 %d: 累计 %d 支%s", page + 1, len(teams),
                 "（还有下一页）" if page_token else "（最后一页）")
        if not page_token:
            break
        if 0 < top_n <= len(teams):
            break
        page += 1

    n_total = len(teams)
    if min_score is not None or max_score is not None:
        kept = []
        for rank, tid, name, score in teams:
            try:
                s = float(score)
            except (TypeError, ValueError):
                continue
            if min_score is not None and s < min_score:
                continue
            if max_score is not None and s > max_score:
                continue
            kept.append((rank, tid, name, score))
        teams = kept

    if 0 < top_n < len(teams):
        teams = teams[:top_n]
    log.info("排行榜共 %d 支队伍 → 选取 %d 支（%s）",
             n_total, len(teams),
             f"分数区间 {min_score}~{max_score}" if min_score is not None or max_score is not None
             else f"取前 {top_n}")
    return teams


def get_best_submission(team_id, delay):
    """取该队伍 publicScore 最高的提交，返回 submission_id。"""
    rc, out = run_kaggle(["competitions", "team-submissions", str(team_id), "-v"], delay)
    if rc != 0:
        return None
    rows = parse_csv(out)
    best, best_score = None, float("-inf")
    for row in rows:
        sid = find_col(row, "submissionId", "submission_id", "id")
        raw = find_col(row, "publicScore", "public_score", "score")
        try:
            score = float(raw)
        except (TypeError, ValueError):
            continue  # 无效/待评分的提交
        if sid and score > best_score:
            best, best_score = sid.strip(), score
    return best


def get_episodes(submission_id, max_eps, delay):
    """返回该提交的 episodeId 列表（按时间倒序取前 max_eps）。"""
    rc, out = run_kaggle(["competitions", "episodes", str(submission_id), "-v"], delay)
    if rc != 0:
        return []
    rows = parse_csv(out)
    eps = []
    for row in rows:
        eid = find_col(row, "episodeId", "episode_id", "episode", "id")
        # [2026-08-11 修复] 空列表时 CLI 会在 CSV 后追加提示行
        # 'Use "kaggle competitions replay <episode_id>" to download a replay',
        # DictReader 把它当成数据行、整串落进第一列 → 之前原样透传给
        # `kaggle competitions replay` 致 rc=2 (invalid int)。episode id 必为纯数字。
        if eid and eid.strip().isdigit():
            eps.append(eid.strip())
    return eps[:max_eps]


def download_replay(episode_id, raw_dir, delay):
    """下载单局 replay 到 raw_dir，已存在则跳过（断点续传）。返回文件路径或 None。"""
    existing = list(raw_dir.glob(f"*{episode_id}*replay*.json"))
    if existing:
        log.debug("已存在，跳过 episode %s", episode_id)
        return existing[0]
    rc, _ = run_kaggle(["competitions", "replay", str(episode_id), "-p", str(raw_dir)], delay)
    if rc != 0:
        return None
    files = sorted(raw_dir.glob(f"*{episode_id}*.json"), key=os.path.getmtime)
    return files[-1] if files else None


def episode_cap(score, max_episodes):
    """按分数分级限制每队下载量：低分段价值低、体量大，少下。"""
    try:
        s = float(score)
    except (TypeError, ValueError):
        return max(3, max_episodes // 3)
    if s < 700:
        return min(3, max_episodes)
    if s < 800:
        return min(5, max_episodes)
    if s < 900:
        return min(10, max_episodes)
    if s < 1000:
        return min(15, max_episodes)
    return max_episodes


def harvest_one(args, raw_dir, rank, team_id, name, score, mf, lock, catalog=None, raw_present=None):
    """处理单支队伍（提交+对局+下载），返回 (manifest记录 or None, 新下载数)。"""
    cap = episode_cap(score, args.max_episodes)
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    sub_id = get_best_submission(team_id, args.delay)
    if not sub_id:
        log.warning("  [#%d] %s 无有效提交，跳过", rank, name)
        return None, 0
    episodes = get_episodes(sub_id, cap, args.delay)
    downloaded = []
    known_eps = catalog.known_ids() if catalog else set()
    for eid in episodes:
        eid = str(eid)
        if raw_present is not None and eid in known_eps and eid not in raw_present:
            log.debug("  episode %s 已归档（catalog 有记录），跳过下载", eid)
            continue
        path = download_replay(eid, raw_dir, args.delay)
        if path:
            downloaded.append({"episode_id": eid, "file": path.name})
        else:
            log.warning("  [#%d] %s replay 下载失败: episode %s", rank, name, eid)
    rec = {
        "date": ts, "rank": rank, "team_id": team_id, "team_name": name,
        "leaderboard_score": score, "best_submission_id": sub_id,
        "captured_at": ts, "rank_at_capture": rank,
        "score_at_capture": score,
        "episodes": downloaded,
    }
    with lock:
        if catalog:
            for episode in downloaded:
                catalog.register(
                    episode["episode_id"],
                    raw_dir / episode["file"],
                    captured_at=ts,
                    team_id=team_id,
                    team_name=name,
                    submission_id=sub_id,
                    rank_at_capture=rank,
                    score_at_capture=score,
                )
        mf.write(json.dumps(rec, ensure_ascii=False) + "\n")
        mf.flush()
    return rec, len(downloaded)


def cmd_harvest(args):
    out_dir = Path(args.out)
    raw_dir = out_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "manifest.jsonl"
    catalog = EpisodeCatalog(out_dir)
    catalog.bootstrap_from_manifest(manifest_path)

    check_prereqs()
    teams = get_leaderboard(args.comp, args.top, args.delay,
                            getattr(args, "min_score", None),
                            getattr(args, "max_score", None))
    if not teams:
        sys.exit("❌ 排行榜为空。")

    # 已处理过的 team 跳过（续传）
    done_teams = set()
    if manifest_path.exists():
        for line in manifest_path.read_text(encoding="utf-8").splitlines():
            try:
                done_teams.add(str(json.loads(line)["team_id"]))
            except Exception:
                pass
    todo = [(r, tid, n, s) for r, tid, n, s in teams if tid not in done_teams]
    log.info("待处理队伍 %d / %d", len(todo), len(teams))
    raw_present = {p.name.split("-")[1] for p in raw_dir.glob("episode-*-replay.json")}
    log.info("raw 现存 %d 局", len(raw_present))

    workers = max(1, getattr(args, "workers", 1))
    lock = threading.Lock()
    total_eps = 0
    snapshot_rows = []

    with manifest_path.open("a", encoding="utf-8") as mf:
        if workers == 1:
            for rank, team_id, name, score in todo:
                if _gate.exhausted():
                    log.error("预算用尽，harvest 提前停止")
                    break
                log.info("[#%d] %s (score=%s, team=%s)", rank, name, score, team_id)
                rec, n = harvest_one(args, raw_dir, rank, team_id, name, score, mf, lock, catalog, raw_present)
                if rec:
                    total_eps += n
                    snapshot_rows.append({
                        "rank": rank, "team_id": team_id, "team_name": name,
                        "leaderboard_score": score,
                        "best_submission_id": rec["best_submission_id"],
                        "new_downloads": n,
                        "episode_ids": [e["episode_id"] for e in rec["episodes"]],
                    })
                    log.info("  ✔ 本队完成(%d 局)，累计 replay: %d", n, total_eps)
        else:
            done_count = 0
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futs = {
                    pool.submit(harvest_one, args, raw_dir, rank, team_id, name, score, mf, lock, catalog, raw_present):
                        (rank, name) for rank, team_id, name, score in todo
                }
                for fut in as_completed(futs):
                    rank, name = futs[fut]
                    rec, n = fut.result()
                    if _gate.exhausted():
                        log.error("预算用尽，harvest 提前停止")
                        break
                    if rec:
                        total_eps += n
                        snapshot_rows.append({
                            "rank": rank, "team_id": rec["team_id"],
                            "team_name": rec["team_name"],
                            "leaderboard_score": rec["leaderboard_score"],
                            "best_submission_id": rec["best_submission_id"],
                            "new_downloads": n,
                            "episode_ids": [e["episode_id"] for e in rec["episodes"]],
                        })
                    done_count += 1
                    if n:
                        log.info("  ✔ [#%d] %s 完成，本队 %d 局，累计 %d", rank, name, n, total_eps)
                    if done_count % 25 == 0 or done_count == len(futs):
                        log.info("  — 进度: %d/%d 队, %d 局", done_count, len(todo), total_eps)

    log.info("✅ harvest 完成，共 %d 个 replay → %s", total_eps, raw_dir)
    if snapshot_rows:
        append_registry_snapshot(out_dir, snapshot_rows, phase="early")
    finalize_replay_artifacts(out_dir, args)


# ---------------------------------------------------------------------------
# INCREMENTAL: 每日增量 sync（推荐）——提交未变只记快照，变化才补下新对局
# ---------------------------------------------------------------------------
def load_latest_manifest(out_dir):
    """manifest.jsonl → {team_id: 最后一条记录}（增量比对的基线）。"""
    meta = {}
    mp = Path(out_dir) / "manifest.jsonl"
    if not mp.exists():
        return meta
    for line in mp.read_text(encoding="utf-8").splitlines():
        try:
            rec = json.loads(line)
        except Exception:
            continue
        if rec.get("team_id"):
            meta[str(rec["team_id"])] = rec
    return meta


def append_leaderboard_snapshot(out_dir, rows):
    """累积排行榜 CSV（date/rank/team_name/score…），一队一行，供排名趋势分析。"""
    csv_path = Path(out_dir) / "leaderboard_snapshot.csv"
    fieldnames = ["date", "ts", "rank", "team_id", "team_name",
                  "leaderboard_score", "best_submission_id", "new_downloads"]
    new_file = not csv_path.exists()
    with csv_path.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        if new_file:
            w.writeheader()
        w.writerows(rows)


def save_daily_manifest(out_dir, rows):
    """Write a timestamped leaderboard snapshot without overwriting history."""
    stamp = time.strftime("%Y-%m-%dT%H%M%SZ")
    p = Path(out_dir) / f"manifest-{stamp}.jsonl"
    with p.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return p


def cmd_incremental(args):
    """
    增量 sync：
      - 拉取排行榜 + 各队最佳提交
      - 无论提交是否变化，都拉取 episode ID 列表并做 episode_id diff
      - 只下载 raw/ 中不存在的新对局，raw/ 永久保留
      - 无论变没变都写：leaderboard_snapshot.csv（累积）+ manifest-<date>.jsonl
      - --force 时无视“未变”判断，强制重查所有队伍（如竞赛最后 48 小时）
    """
    out_dir = Path(args.out)
    raw_dir = out_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "manifest.jsonl"
    catalog = EpisodeCatalog(out_dir)
    catalog.bootstrap_from_manifest(manifest_path)

    check_prereqs()
    teams = get_leaderboard(args.comp, args.top, args.delay,
                            getattr(args, "min_score", None),
                            getattr(args, "max_score", None))
    if not teams:
        sys.exit("❌ 排行榜为空。")

    prev = load_latest_manifest(out_dir)
    known_eps = catalog.known_ids()
    raw_present = {p.name.split("-")[1] for p in raw_dir.glob("episode-*-replay.json")}
    log.info("catalog %d 局 / raw 现存 %d 局", len(known_eps), len(raw_present))

    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    phase = getattr(args, "phase", "auto")
    if phase == "auto":
        phase = competition_phase(
            competition_start=getattr(args, "competition_start", None),
            competition_end=getattr(args, "competition_end", None),
            final_days=getattr(args, "final_days", 2),
        )
    log.info("竞赛阶段=%s，更新策略=%s", phase, phase_policy(phase, {
        "schedule": {
            "early_poll_hours": 24, "mid_poll_hours": 6, "final_poll_hours": 1,
            "early_retrain_cooldown_hours": 168,
            "mid_retrain_cooldown_hours": 24,
            "final_retrain_cooldown_hours": 6,
        }
    }))
    snap_rows, n_changed, n_unchanged, n_new = [], 0, 0, 0

    with manifest_path.open("a", encoding="utf-8") as mf:
        for rank, team_id, name, score in teams:
            if _gate.exhausted():
                log.error("预算用尽，incremental 提前停止")
                break
            log.info("[#%d] %s (score=%s, team=%s)", rank, name, score, team_id)
            sub_id = get_best_submission(team_id, args.delay)
            old = prev.get(str(team_id))
            same_sub = bool(sub_id) and old and old.get("best_submission_id") == sub_id

            downloaded, new_entries, n_team_new = [], [], 0
            # Always poll episode IDs. A submission can expose more episodes
            # later, and a score change can increase episode_cap.
            if same_sub and not args.force:
                n_unchanged += 1
                log.info("  提交未变 (%s)，仍检查 episode ID 增量", sub_id)
            else:
                n_changed += 1
            episodes = get_episodes(
                sub_id,
                episode_cap(score, args.max_episodes),
                args.delay,
            ) if sub_id else []
            log.info("  对局数: %d（补卡上限 %d）", len(episodes), episode_cap(score, args.max_episodes))
            for eid in episodes:
                eid = str(eid)
                if eid in known_eps and eid not in raw_present:
                    log.debug("  episode %s 已归档（catalog 有记录，raw 无文件），跳过下载", eid)
                    continue
                is_new = eid not in known_eps
                path = download_replay(eid, raw_dir, args.delay)
                if path:
                    item = {"episode_id": eid, "file": path.name}
                    downloaded.append(item)
                    registered = catalog.register(
                        eid,
                        path,
                        captured_at=ts,
                        team_id=team_id,
                        team_name=name,
                        submission_id=sub_id,
                        rank_at_capture=rank,
                        score_at_capture=score,
                    )
                    if is_new or registered:
                        new_entries.append(item)
                        n_team_new += 1
                        n_new += 1
                    known_eps.add(eid)
                else:
                    log.warning("  replay 下载失败: episode %s", eid)
            if new_entries:
                mf.write(json.dumps({
                    "date": ts, "rank": rank, "team_id": team_id,
                    "team_name": name, "leaderboard_score": score,
                    "captured_at": ts, "rank_at_capture": rank,
                    "score_at_capture": score,
                    "best_submission_id": sub_id, "episodes": new_entries,
                }, ensure_ascii=False) + "\n")
                mf.flush()
                log.info("  ✔ 本队完成，本队新增 %d 个对局", n_team_new)

            snap_rows.append({
                "date": ts[:10], "ts": ts, "rank": rank, "team_id": team_id,
                "team_name": name, "leaderboard_score": score,
                "best_submission_id": sub_id, "new_downloads": n_team_new,
                "episode_ids": [str(eid) for eid in episodes],
                "phase": phase,
            })

    snap_path = save_daily_manifest(out_dir, snap_rows)
    append_leaderboard_snapshot(out_dir, snap_rows)
    append_registry_snapshot(out_dir, snap_rows, phase=phase, captured_at=ts)

    log.info("✅ 增量完成: 变更/新增 %d 队，未变 %d 队，新增 %d 个对局 → %s",
             n_changed, n_unchanged, n_new, raw_dir)
    log.info("   → 快照 %s / leaderboard_snapshot.csv", snap_path.name)
    finalize_replay_artifacts(out_dir, args)


# ---------------------------------------------------------------------------
# INSPECT: 查看 replay 真实 schema（schema 随环境版本变化，先看清再解析）
# ---------------------------------------------------------------------------
def shallow_schema(obj, depth=0, max_depth=4):
    if depth > max_depth:
        return "..."
    if isinstance(obj, dict):
        return {k: shallow_schema(v, depth + 1, max_depth) for k, v in list(obj.items())[:15]}
    if isinstance(obj, list):
        if not obj:
            return []
        return [shallow_schema(obj[0], depth + 1, max_depth), f"... (len={len(obj)})"]
    return type(obj).__name__


def cmd_inspect(args):
    raw_dir = Path(args.out) / "raw"
    files = sorted(raw_dir.glob("*.json"))
    if not files:
        sys.exit("❌ raw/ 目录为空，先跑 harvest。")
    data = json.loads(files[0].read_text(encoding="utf-8"))
    print(f"样本: {files[0].name}\n")
    print(json.dumps(shallow_schema(data), indent=2, ensure_ascii=False))


# ---------------------------------------------------------------------------
# PARSE: replay JSON → JSONL + corpus
# ---------------------------------------------------------------------------
def normalize_episode(path):
    """
    Kaggle simulation replay 通用结构（PTCG 以 inspect 结果为准微调）：
      {
        "name"/"info"/"configuration": ...,
        "steps": [ [ {agent0: obs/action/reward/status}, {agent1: ...} ], ... ],
        "rewards": [r0, r1]
      }
    返回 (episode_record, step_records)。
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    info = data.get("info", {}) if isinstance(data.get("info"), dict) else {}
    ep_id = info.get("EpisodeId") or info.get("episodeId") \
        or Path(path).stem.replace("-replay", "").replace("episode-", "")

    steps = data.get("steps") or data.get("Steps") or []
    rewards = data.get("rewards") or data.get("Rewards") or []
    agents = [a.get("name") if isinstance(a, dict) else str(a)
              for a in (data.get("agents") or info.get("Agents") or [])]

    ep_rec = {
        "episode_id": ep_id,
        "file": Path(path).name,
        "agents": agents,
        "rewards": rewards,
        "n_steps": len(steps),
        "winner": (rewards.index(max(rewards)) if rewards else None),
        "configuration": data.get("configuration"),
    }

    step_recs = []
    for si, step in enumerate(steps):
        # 每一步通常是 per-agent 的列表
        agent_views = step if isinstance(step, list) else [step]
        for ai, view in enumerate(agent_views):
            if not isinstance(view, dict):
                continue
            step_recs.append({
                "episode_id": ep_id,
                "step_index": si,
                "agent_index": ai,
                "action": view.get("action"),
                "reward": view.get("reward"),
                "status": view.get("status"),
                "observation": view.get("observation"),
            })
    return ep_rec, step_recs


def load_manifest(out_dir):
    """manifest.jsonl -> episode metadata from the first capture event."""
    meta = {}
    mp = Path(out_dir) / "manifest.jsonl"
    if not mp.exists():
        return meta
    for line in mp.read_text(encoding="utf-8").splitlines():
        try:
            rec = json.loads(line)
        except Exception:
            continue
        for ep in rec.get("episodes", []):
            # [fix 08-09] 坏记录容错: JSON 合法但缺键(episode_id/team_id/
            # best_submission_id 等)时跳过该条, 不再整函数崩溃拖垮整批
            try:
                episode_id = str(ep["episode_id"])
                candidate = {
                    "team_id": rec["team_id"], "team_name": rec["team_name"],
                    "rank_at_capture": rec.get("rank_at_capture", rec.get("rank")),
                    "score_at_capture": rec.get(
                        "score_at_capture", rec.get("leaderboard_score")
                    ),
                    "captured_at": rec.get("captured_at", rec.get("date")),
                    "submission_id": rec["best_submission_id"],
                }
            except KeyError:
                continue
            previous = meta.get(episode_id)
            # [fix 08-09] captured_at 混用 epoch 数值与 ISO 字符串时, 字典序
            # ("1..." 恒 < "2026...") 会误判早晚, 统一归一为 ISO 字符串再比
            if previous is None or _ts_key(candidate["captured_at"]) < _ts_key(previous["captured_at"]):
                meta[episode_id] = candidate
    return meta


def _ts_key(v):
    """captured_at 归一为可字典序比较的键: epoch 数值(含数字字符串)转 ISO
    字符串, ISO/日期字符串原样, None 排最后。ISO 格式字典序即时间序。"""
    from datetime import datetime
    if v is None:
        return "\uffff"
    if isinstance(v, (int, float)):
        try:
            return datetime.fromtimestamp(v).isoformat()
        except (OverflowError, OSError, ValueError):
            return str(v)
    s = str(v)
    try:  # 字符串里包着 epoch 的情况
        return datetime.fromtimestamp(float(s)).isoformat()
    except (ValueError, OverflowError, OSError):
        return s


def cmd_parse(args):
    out_dir = Path(args.out)
    raw_dir, parsed_dir = out_dir / "raw", out_dir / "parsed"
    parsed_dir.mkdir(parents=True, exist_ok=True)
    meta = load_manifest(out_dir)

    files = sorted(raw_dir.glob("*.json"))
    if not files:
        sys.exit("❌ raw/ 目录为空，先跑 harvest。")
    log.info("解析 %d 个 replay ...", len(files))

    n_ok = n_fail = 0
    ep_path = parsed_dir / "episodes.jsonl"
    st_path = parsed_dir / "steps.jsonl"
    corpus = {"competition": args.comp, "episodes": []}

    with ep_path.open("w", encoding="utf-8") as ef, st_path.open("w", encoding="utf-8") as sf:
        for f in files:
            try:
                ep_rec, step_recs = normalize_episode(f)
            except Exception as e:
                log.warning("解析失败 %s: %s", f.name, e)
                n_fail += 1
                continue
            ep_meta = meta.get(str(ep_rec["episode_id"]), {})
            ep_rec.update(ep_meta)
            ef.write(json.dumps(ep_rec, ensure_ascii=False) + "\n")
            for sr in step_recs:
                sf.write(json.dumps(sr, ensure_ascii=False) + "\n")
            corpus["episodes"].append({**ep_rec, "steps": step_recs})
            n_ok += 1

    (parsed_dir / "corpus.json").write_text(
        json.dumps(corpus, ensure_ascii=False, indent=1), encoding="utf-8")

    log.info("✅ 解析完成: %d 成功 / %d 失败", n_ok, n_fail)
    log.info("   → %s / %s / corpus.json", ep_path.name, st_path.name)


# ---------------------------------------------------------------------------
# STATS: 快速统计（schema 感知弱，偏通用）
# ---------------------------------------------------------------------------
def cmd_stats(args):
    out_dir = Path(args.out)
    ep_path = out_dir / "parsed" / "episodes.jsonl"
    st_path = out_dir / "parsed" / "steps.jsonl"
    if not ep_path.exists():
        sys.exit("❌ 先跑 parse。")

    episodes = [json.loads(l) for l in ep_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    print(f"== 对局概览（{len(episodes)} 局）==")
    lens = [e.get("n_steps", 0) for e in episodes]
    if lens:
        print(f"  步数: avg={sum(lens)/len(lens):.1f} min={min(lens)} max={max(lens)}")

    team_wins = Counter()
    team_games = Counter()
    for e in episodes:
        team = e.get("team_name", "?")
        team_games[team] += 1
        if e.get("winner") is not None:
            team_wins[team] += 1  # 注：无法区分是哪方agent，仅粗粒度参考
    print("  各队对局数:", dict(team_games.most_common(10)))

    if st_path.exists():
        action_types = Counter()
        status_c = Counter()
        n = 0
        with st_path.open(encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                n += 1
                sr = json.loads(line)
                act = sr.get("action")
                if isinstance(act, dict):
                    action_types[act.get("type") or next(iter(act), "?")] += 1
                elif act is not None:
                    action_types[str(act)[:40]] += 1
                if sr.get("status"):
                    status_c[sr["status"]] += 1
        print(f"\n== 步骤记录（{n} 条）==")
        print("  status 分布:", dict(status_c))
        print("  action 类型 Top 20:")
        for k, v in action_types.most_common(20):
            print(f"    {k}: {v}")


# ---------------------------------------------------------------------------
# VERIFY: 统一校验（manifest ↔ raw 一致性、JSON 完整性、按分数段覆盖）
# ---------------------------------------------------------------------------
def cmd_verify(args):
    out_dir = Path(args.out)
    raw_dir = out_dir / "raw"
    manifest_path = out_dir / "manifest.jsonl"
    if not manifest_path.exists():
        sys.exit("❌ 未找到 manifest.jsonl，先跑 harvest。")

    recs = [json.loads(l) for l in manifest_path.read_text(encoding="utf-8").splitlines() if l.strip()]

    catalog_ids = set()
    catalog_path = out_dir / "episode_catalog.jsonl"
    if catalog_path.exists():
        for line in catalog_path.read_text(encoding="utf-8").splitlines():
            try:
                catalog_ids.add(str(json.loads(line).get("episode_id")))
            except Exception:
                pass

    by_file, by_team = {}, {}
    for rec in recs:
        by_team.setdefault(str(rec["team_id"]), rec)
        for ep in rec.get("episodes", []):
            by_file[ep["file"]] = rec

    raw_files = {f.name: f for f in raw_dir.glob("*.json")}
    file_to_ep = {}
    for rec in recs:
        for ep in rec.get("episodes", []):
            file_to_ep[ep["file"]] = str(ep.get("episode_id", ""))
    archived = [f for f in by_file if f not in raw_files
                and file_to_ep.get(f) in catalog_ids]
    missing = [f for f in by_file if f not in raw_files and f not in archived]
    unreferenced = [f for f in raw_files if f not in by_file]

    bad_json = []
    for name, f in raw_files.items():
        try:
            json.loads(f.read_text(encoding="utf-8"))
        except Exception as e:
            bad_json.append((name, str(e)[:80]))

    n_eps = sum(len(r.get("episodes", [])) for r in recs)
    total_mb = sum(f.stat().st_size for f in raw_files.values()) / 1e6

    bands = Counter()
    for rec in by_team.values():
        try:
            s = float(rec.get("leaderboard_score", 0))
        except (TypeError, ValueError):
            s = 0
        bands[int(s) // 100 * 100] += 1

    print("== 一致性校验 ==")
    print(f"  manifest 记录(队):      {len(recs)}")
    print(f"  manifest 引用对局:      {n_eps}")
    print(f"  raw/ 实际文件:           {len(raw_files)}")
    print(f"  📦 已归档(catalog有、raw无): {len(archived)}（正常，可从 archive 恢复）")
    print(f"  ❌ manifest 有但磁盘缺:  {len(missing)}")
    for f in missing[:20]:
        print(f"      - {f}")
    print(f"  ⚠ 磁盘有但 manifest 无:  {len(unreferenced)}")
    for f in unreferenced[:20]:
        print(f"      - {f}")
    print(f"  ❌ JSON 解析失败:        {len(bad_json)}")
    for name, err in bad_json[:20]:
        print(f"      - {name}: {err}")
    print(f"  总大小:                 {total_mb:.1f} MB")
    print("  分数段分布(队):", dict(sorted(bands.items())))

    n_ok = len(recs)
    if missing or bad_json:
        print(f"\n❌ 校验未通过：缺失 {len(missing)}，坏 JSON {len(bad_json)}")
        return 1
    print(f"\n✅ 校验通过（{n_ok} 队 / {n_eps} 局 / {total_mb:.1f} MB）")
    return 0


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main():
    p = argparse.ArgumentParser(description="Kaggle PTCG replay 批量下载 + 解析")
    p.add_argument("--comp", default=DEFAULT_COMP, help="竞赛 slug")
    p.add_argument("--out", default=str(DEFAULT_DIR), help="输出目录")
    p.add_argument("--delay", type=float, default=DEFAULT_DELAY, help="请求基础间隔秒数（≥5 建议）")
    p.add_argument("--budget", type=int, default=BUDGET_DEFAULT,
                   help="每日(UTC)请求预算，0=不限（实测 ~4000 次触发硬限流，默认 %d）" % BUDGET_DEFAULT)
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)

    h = sub.add_parser("harvest", help="批量下载 replay（支持分数区间 + 并行分块）")
    h.add_argument("--top", type=int, default=20, help="扒前 N 名队伍（≤0 表示全量）")
    h.add_argument("--max-episodes", type=int, default=30, help="高分段每队最多下载几局")
    h.add_argument("--min-score", type=float, default=None, help="只处理分数 ≥ 该值的队伍")
    h.add_argument("--max-score", type=float, default=None, help="只处理分数 ≤ 该值的队伍")
    h.add_argument("--workers", type=int, default=1,
                   help="并行下载的 worker 数（配合 --delay 控制限流，建议 4-8）")
    h.add_argument("--archive-level", type=int, default=5,
                   help="完成后 zstd 重新打包等级")
    h.add_argument("--no-finalize", action="store_true",
                   help="仅用于故障恢复：跳过打包/全量校验")
    h.set_defaults(fn=cmd_harvest)

    inc = sub.add_parser("incremental", help="每日增量 sync：提交变化才补下新对局 + 排行榜快照")
    inc.add_argument("--top", type=int, default=20, help="前 N 名队伍（≤0 表示全量，需分数过滤时用）")
    inc.add_argument("--max-episodes", type=int, default=30, help="每队最多补下几局")
    inc.add_argument("--min-score", type=float, default=None)
    inc.add_argument("--max-score", type=float, default=None)
    inc.add_argument("--force", action="store_true",
                     help="无视提交比对，强制重查所有队伍并补下新对局（竞赛最后 48 小时用）")
    inc.add_argument("--phase", choices=("auto", "early", "mid", "final"), default="auto",
                     help="竞赛阶段；auto 根据 start/end 判断")
    inc.add_argument("--competition-start", default=None,
                     help="ISO 时间，例如 2026-08-01T00:00:00Z")
    inc.add_argument("--competition-end", default=None,
                     help="ISO 时间，例如 2026-08-15T00:00:00Z")
    inc.add_argument("--final-days", type=int, default=2,
                     help="结束前多少天进入 final 阶段")
    inc.add_argument("--archive-level", type=int, default=5,
                     help="完成后 zstd 重新打包等级")
    inc.add_argument("--no-finalize", action="store_true",
                     help="仅用于故障恢复：跳过打包/全量校验")
    inc.set_defaults(fn=cmd_incremental)

    i = sub.add_parser("inspect", help="查看 replay 真实 schema")
    i.set_defaults(fn=cmd_inspect)

    pa = sub.add_parser("parse", help="解析成 JSONL + corpus.json")
    pa.set_defaults(fn=cmd_parse)

    st = sub.add_parser("stats", help="快速统计")
    st.set_defaults(fn=cmd_stats)

    vf = sub.add_parser("verify", help="统一校验 manifest ↔ raw 一致性")
    vf.set_defaults(fn=cmd_verify)

    args = p.parse_args()
    Path(args.out).mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.StreamHandler(),
                  logging.FileHandler(Path(args.out) / "harvest.log", encoding="utf-8")],
    )
    _gate.configure(args.delay, args.budget, Path(args.out) / "request_budget.json")
    try:
        rc = args.fn(args)
    finally:
        _gate.save()
    sys.exit(rc if isinstance(rc, int) else 0)


if __name__ == "__main__":
    main()
