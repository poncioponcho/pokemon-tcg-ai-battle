# 百度网盘备份清单 (BACKUP_MANIFEST)

- 备份时间: 2026-08-06
- 目的: `inference/leaderboard_replay/raw/` 已删除（37G，全部已归档进 all_replays.jsonl.zst），
  以下为**不可再生 / 费事再生**数据的网盘备份记录。
- 上传方式: 将 `inference/backup_to_baidu/` 整个目录拖入百度网盘客户端（目录内为硬链接，上传完成后可删除该目录，不影响原文件）。

## 文件清单

| 文件 | 大小 | SHA256 | 来源 | 可再生性 |
|---|---|---|---|---|
| all_replays.jsonl.zst | 1,025,955,020 (978M) | 2d89a81a05fa812b896d9cc30425de18b2738f1e6461303e9cf781a0a24b4d64 | 由 `merge_replays.py` 合并 raw/(9,458局,已删) + official_bulk(4,384局) | **不可再生**（raw/ 已删，重爬受 Kaggle 429 日配额限制）。13,842 局，位级验证通过 |
| TopRatedEpisodes/2026-07-01.zip | 749,325,652 | ce29508045d31635ec9f1d86fbd92fc8f08e2212db20aaa9f49943d30b6c13e2 | Kaggle TopRatedEpisodes 周快照 | 可重新下载（费事） |
| TopRatedEpisodes/2026-07-08.zip | 744,760,015 | 55d5f63c1625b7838fc388e26a0cf33ffeef82e735c68e58e13bf94d94c7a5e1 | 同上 | 同上 |
| TopRatedEpisodes/2026-07-12.zip | 736,685,052 | fba2cc8fd028109ab038dda9b2aca09bd1323cf40200cd2797d66c351fc67646 | 同上 | 同上 |
| TopRatedEpisodes/2026-07-19.zip | 732,439,318 | c663091e736ce872574493e8fcc9e59551d8fe5cd4241787769e957ed92f5083 | 同上 | 同上 |
| TopRatedEpisodes/2026-07-31.zip | 744,817,663 | c19ad47fa061c8838da1375d7cb0a49efd8ed9674d53be39b6246623a578ed31 | 同上 | 同上 |

总计约 4.5G。下载回来用 `shasum -a 256 <file>` 对照上表校验。

## 本地已删/可删（可再生，不备份）

| 路径 | 大小 | 再生命令 |
|---|---|---|
| `inference/dataset/data/*.npy`（训练张量, 13,842局） | 14G | `python3 inference/dataset/extract.py --archive inference/leaderboard_replay/archive/all_replays.jsonl.zst --out inference/dataset/data --workers 8`（单线程约 9–22 分钟） |
| `inference/leaderboard_replay/archive/raw_replays.jsonl.zst` | 650M | 是 all_replays 的纯子集，无需再生；`extract.py`/`run_training_tests.py` 默认引用它，若删需传参 `--archive` |
| `inference/leaderboard_replay/archive/official_bulk_2026-07-30.jsonl.zst` | 331M | 已并入 all_replays；删后 `merge_replays.py` 需改 BULK 路径 |

## 重建/增量关键命令

```bash
# 增量爬取（episode_catalog.jsonl 权威，已归档的局自动跳过）
python3 inference/ptcg_replay_harvester.py --out inference/leaderboard_replay --delay 7 incremental --top 0 --min-score 600 --max-score 1000

# 合并所有源 → 规范归档（merge_replays.py 需 raw/ + official_bulk 两个源都存在）
python3 inference/dataset/merge_replays.py

# 归档完整性验证
python3 inference/ptcg_replay_harvester.py --out inference/leaderboard_replay verify
```

## 第二波备份 (2026-08-06)

| 文件 | 大小 | SHA256 | 说明 |
|---|---|---|---|
| ptcg_tensors.tar.gz | 131,830,806 (126M) | 9ef2c40d0a95a1c0cbd17d3fd0d3d2d502de15a04eb2920efbaba2c0c74eac92 | 14G 训练张量（13,842局）的无损压缩包；与本地已删的 inference/dataset/data/ 逐字节一致（meta.json 已验证）；重建备选路径。**注意：此目录被 ptcg-bcrl/config/paths.json 的 data_dir 引用（共享依赖，勿删）**。恢复: `tar xzf ptcg_tensors.tar.gz -C inference/dataset/data/` |
| episode_catalog.jsonl | 3,903,808 | da3ccfc537cbc09a9119c7ed191646249490ea81ce57fd52acc3ea1b72d8602e | 增量爬取去重键（权威 catalog），丢失会重复下载 |
| manifest.jsonl | 914,080 | 5f141228252ad3a74f8f1b6c29d1809393cb0aa9e6b865f8db5e8dce9fcd487e | 同上（manifest） |
| repo_history.bundle | 56,626 | ad72e6983df68a85a3277671ac28b6e9516039e06eea134b7cdcd71f2bbcf613 | 完整 git 历史（`git bundle verify` 通过）。恢复: `git clone repo_history.bundle <dir>`。建议另推 GitHub 私有库 |
| card_strategy_data.tar.gz | 1,825,921,024 (1.7G) | 74a1ce7f276a5a38992d32a05e03dd3bddd092317a784fdddf1ab169726edc7c | 卡牌库：card_pages 1.4G 官网页图 + OCR 结果/清洗 CSV + ID 列表 PDF；1,331 文件可读。可再生但费事（重抓+OCR 数小时） |

本地已删 `inference/dataset/data/*.npy`（14G）由上面 tar 包或 `extract.py` 重建均可。

## 完整性验证记录

- 2026-08-06: all_replays.jsonl.zst 解压 13,842 行（zstd），manifest 记录 from_raw=9,458 / from_bulk=4,384
- 2026-08-06: 删除 raw/ 前核对 episode_catalog.jsonl=9,458 条 == raw/ 文件数=9,458（完全一致，无未归档文件）
