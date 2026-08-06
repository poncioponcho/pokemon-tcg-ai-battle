# 项目依赖关系图 (DEPENDENCIES)

> 2026-08-06 梳理。双项目结构：主仓库 3 条链 + 兄弟项目 ptcg-bcrl 反向依赖主仓库。

```
┌─ A. Pokemon_TCG_AI_Battle_Challenge（主仓库）
│
│  链1 卡牌数据链（静态）
│  strategy/JP_Card_Data_Cleaned.csv ─→ gen_card_db.py ─→ CardPool.csv
│  strategy/EN_Card_Data.csv ─→ build_deck.py ─→ optimized_deck.csv（分析用）
│  CardPool.csv ─→ gen_deck.py ─→ deck.csv（提交核心）
│
│  链2 提交链（竞赛产物）
│  main.py（纯Python agent，只 import collections，运行时读 deck.csv）
│  deck.csv + main.py (+可选 model_student.npz) ─→ pack.sh ─→ submission.tar.gz
│  ─→ submit.sh/submit.py ─→ Kaggle 提交；kaggle_status.sh 轮询
│  注意：submission/main.py 与 inference/main_entry.py 是旧变体（≠根 main.py）
│
│  链3 Replay→张量→训练链（inference/）
│  ptcg_replay_harvester.py ─→ leaderboard_replay/{raw,episode_catalog,manifest}
│  raw/ + archive/official_bulk ─→ merge_replays.py ─→ all_replays.jsonl.zst（唯一live归档）
│  all_replays ─→ extract.py ─→ dataset/data/*.npy（14G, 13,842局）
│  data/ + splits/ ─→ train_bc.py（依赖 card_vocab.py、model_v2.py）
│  ─→ export_student.py ─→ model_student.npz（回填 pack.sh）
│  kaggle_gpu_train.py：上传训练集脚本→Kaggle GPU 训练→下载 model_student.npz
│
└─ B. ptcg-bcrl（Phase 2 BC-RL，依赖主仓库）
   config/paths.json ──→ 主仓库 inference/dataset/data（14G，mmap）
                     ├─→ 主仓库 inference/dataset/splits/（评测集划分）
                     ├─→ 主仓库 sdk/（引擎）
                     └─→ 主仓库 deck.csv
   prepare.py（冻结评测 recall/top1）← gen_option_types.py（写 option_types.npy）
   train.py ─→ weights.npz ─→ export.py ─→ exports/{pure_submission/, submission.tar.gz}
   validate_winrate.py（docker 胜率门控）── run_exp.sh（.best_commit / WIN_GATE 5%）
```

## 关键依赖红线

| 红线 | 说明 |
|---|---|
| `inference/dataset/data/` | 被 ptcg-bcrl `paths.json` 的 data_dir 引用（mmap 读取），删除会断 Phase 2 训练/评测。重建：`ptcg_tensors.tar.gz` 秒级解压，或 `extract.py` 从 `all_replays.jsonl.zst` 重提取（9–22 分钟） |
| `all_replays.jsonl.zst` | live 数据唯一存档（`raw/` 已删，9,458 局全量归档），全部下游张量由此而来；备份于百度网盘 + 本地 `archive/` |
| `episode_catalog.jsonl` + `manifest.jsonl` | 增量爬取去重键，丢失会重复下载；已备份网盘 |
| `model_student.npz` | 可选提交物：不存在时 pack.sh 正常；由 Kaggle GPU 训练（kaggle_gpu_train.py）或本地 export_student.py 产出后回填根目录 |
| `submission/main.py` | 与根 `main.py` 不同步（旧快照）；pack.sh 打包的是根的 `main.py` |
| `inference/dataset/splits/` | ptcg-bcrl 评测集划分（episode_splits.jsonl + rolling_canary.json），不可删；被主仓库训练与兄弟项目共享 |

## 数据流方向（只读依赖 → 产出）

```
strategy/*.csv ──────────→ gen_card_db.py ─→ CardPool.csv ─→ gen_deck.py ─→ deck.csv
deck.csv + main.py ──────→ pack.sh ─→ submission.tar.gz ─→ submit.py ─→ Kaggle
raw/ + official_bulk.zst ─→ merge_replays.py ─→ all_replays.jsonl.zst ─→ extract.py
  ─→ data/*.npy + splits/ ─→ train_bc.py ─→ export_student.py ─→ model_student.npz
ptcg-bcrl: paths.json ─→ (data/ + splits/ + sdk/ + deck.csv 只读引用)
  ─→ prepare.py / gen_option_types.py ─→ train.py ─→ weights.npz ─→ export.py ─→ exports/
```

## 备份/恢复速查

- 网盘：`inference/backup_to_baidu/`（all_replays.zst、张量 tar、卡牌库、git bundle、catalog/manifest）— 见 `BACKUP_MANIFEST.md`
- 代码：GitHub 私有库 `poncioponcho/pokemon-tcg-ai-battle`（SSH 免密）
- 张量恢复：`tar xzf ptcg_tensors.tar.gz -C inference/dataset/data/`（秒级）
- 归档重提取：`python3 inference/dataset/extract.py --archive inference/leaderboard_replay/archive/all_replays.jsonl.zst --out inference/dataset/data --workers 8`
