---
name: ptcg-leaderboard-harvest
description: Use when downloading or updating the LIVE Kaggle pokemon-tcg-ai-battle leaderboard replay data (最新榜单对战数据爬取). Covers the pitfalls of ptcg_replay_harvester.py: leaderboard pagination, score-range filtering, Kaggle API rate limiting (429), daily request budget, resume/verify, and why official bulk datasets are historical not live. Trigger on 爬取/限流/429/leaderboard replay/harvest/incremental/request_budget.
---

# PTCG Live Leaderboard Replay Harvest

Download the CURRENT leaderboard's replay data (per-team submissions → episodes → replay JSON), not dated snapshots.

## Where the code lives

- Harvester + RateGate + budget: `inference/ptcg_replay_harvester.py`
- Streamable archive: `inference/dataset/replay_archive.py` (pack/scan/extract)
- Bulk historical source helper: `inference/dataset/bulk_replay_source.py`
- Data root: `inference/leaderboard_replay/` (`raw/`, `manifest.jsonl`, `episode_catalog.jsonl`, `request_budget.json`, `archive/`)

## Why the first naive crawl failed (evidence)

| Config | Effective rate | Clean time | Requests before first 429 |
|---|---|---|---|
| 6 workers × 2s delay | ~0.87 req/s | 61 min | ~4,000 |
| 2 workers × 7s delay (after recovery) | ~0.10 req/s | 38 min | ~230 |

Conclusions (empirical, this competition):
1. Kaggle throttling here is a **dynamic cumulative quota**, not pure rate limiting. The first run consumed the day's quota; a much slower second run hit the wall quickly after recovery.
2. **SSL connection drops** (`SSLEOFError`) appeared ~50 min BEFORE the first 429 — they are the early-warning signal. Treat them as pressure, not just retry noise.
3. Sustained aggregate > ~1 req/s eventually triggers 429; the safe envelope is single worker with 5-10s spacing.
4. After a 429 storm, a quick restart burns quota with zero output (measured: restart 10 min later → 0 progress, 48 wasted requests). Wait for the window to clear or for UTC midnight reset.

## Non-negotiable rules

- Default request spacing ≥ 5s (`--delay 5`), never below 3s.
- `--workers 1` unless you accept 429 risk; multi-worker only during off-peak with monitoring.
- Keep `--budget` (default 3000/UTC day) — it is persisted to `out/request_budget.json` and resets at UTC midnight (= Beijing 08:00). 0 disables it.
- Never hammer after a 429 storm. Let RateGate's long cooldown (900s) do its job.
- `kaggle competitions replay` calls the GetEpisodeReplay **API** and IS rate-limited. The "CLI is not API-limited" claim only applies to dataset downloads, not replay.

## Core commands

```bash
PY="python3 inference/ptcg_replay_harvester.py"
OUT="inference/leaderboard_replay"

# Live leaderboard crawl for the score band most relevant below-base-600 play
$PY --out $OUT --delay 7 harvest --top 0 --min-score 600 --max-score 1000 --workers 1

# Daily incremental: re-polls episode IDs, downloads only missing raw files
$PY --out $OUT --delay 7 incremental --top 0 --min-score 600 --max-score 1000

# Unified integrity check (manifest ↔ raw, JSON validity, band coverage)
$PY --out $OUT verify
```

## Problems → solutions

| Symptom | Root cause | Fix |
|---|---|---|
| Leaderboard shows only 20 teams | CLI paginates; output has `Next Page Token = ...` | Loop `--page-size 200 --page-token <token>` until no token (script does this; needs `-s -v` flags) |
| Want score range (e.g. 600-1000) | Score filtering | Fetch ALL pages first, then filter (script keeps original rank) |
| 429 bursts on GetEpisodeReplay | Cumulative quota exhausted / rate too hot | Wait for UTC midnight or window; check `request_budget.json`; never restart within ~30-60 min |
| SSL EOF / connection errors | Server-side pressure, precedes 429 by ~50 min | Count as pressure: RateGate auto-ramps delay (5s→60s cap) |
| "0 warnings then suddenly throttled" | Old binary counter reset on success | RateGate sliding window (50 req / 10 min): >5% warn, >20% ramp, ≥60% → 900s cooldown |
| Budget exhausted mid-run | Daily cap hit | Clean stop (rc -2); resume next UTC day; or `--budget 0` |
| `--out`/`--delay` error | argparse order | Global flags go BEFORE the subcommand |
| `~/.kaggle/kaggle.json` missing | Env-token setup | `KAGGLE_API_TOKEN` env var is sufficient (check_prereqs patched) |
| Re-downloads everything | No resume | manifest.jsonl + raw-file existence dedup; `verify` confirms |

## Score-based episode caps (harvest/incremental apply automatically)

600-700: 3/team · 700-800: 5/team · 800-900: 10/team · 900-1000: 15/team · 1000+: 30/team

## Live vs historical sources — do not mix them up

- Official Kaggle Dataset `kaggle/pokemon-tcg-ai-battle-episodes-2026-07-30` (4,384 replays) and `inference/TopRatedEpisodes/*.zip` (weekly: 07-01/08/12/19/31) are **dated snapshots** with NO live leaderboard rank/score.
- Use them only as extra archive volume (`replay_archive.py pack` them); the live leaderboard requires the incremental/harvest path above.

## Compression & storage (measured, 4,432 replays)

- raw JSON 17.43 GB → `raw_replays.jsonl.zst` ~305 MB (zstd level 5, ratio ~57×)
- Streaming scan (parse all, bounded memory ~0.4 GB): ~3 min wall
- Extract-from-archive training tensors: ~525 s wall, 414 MB peak (single-threaded)
- Raw multiprocessing extraction (8 workers): ~224 s wall, 1.44 GB peak
- `train_bc.py` consumes uncompressed `.npy` tensors, so archive choice never affects training speed once tensors exist.
- Full live ≥600 dataset: 3,559 teams ≈ 22,800 episodes ≈ 90 GB raw / ~1.6 GB archived / ~12 GB tensors.

## Storage scheme (archive-first)

Disk cannot hold the full raw set (90 GB + project). The crawler treats
`episode_catalog.jsonl` as authoritative: after `raw/` is wiped, incremental and
harvest skip episodes already in the catalog, so archived data is never
re-downloaded. Canonical copy is `archive/raw_replays.jsonl.zst` (repacked
after each crawl); `raw/` is a working cache that may be deleted; tensors in
`dataset/data/*.npy` stay for mmap training; `parsed/` is regenerable. See
`inference/dataset/MLOPS.md` "Storage scheme" section.

## RateGate behavior (in-script)

- Sliding window over last 50 requests / 10 min; pressure = (429 + conn errors) / window.
- Adaptive delay: base `--delay`, ×1.15 (early), ×1.3, ×1.6 up to 60s; decays only when pressure ≤ 2%.
- Cooldown 900s when pressure ≥ 60%.
- Budget: spend per attempt (incl. retries), persist every 25 + on exit.
