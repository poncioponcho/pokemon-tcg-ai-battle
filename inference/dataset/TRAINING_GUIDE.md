# PTCG BC+RL Training Framework

## Scope

This is an offline training framework for the PTCG replay data. The local
machine does not have the Linux `libcg.so` battle engine, so the RL phase is
implemented as Advantage-Weighted Regression (AWR) over replay outcomes. It is
the offline RL continuation of behavior cloning, not a claim of local
self-play PPO execution.

## Module Layout

| Module | Responsibility |
|---|---|
| `replay_archive.py` | Streamable zstd archive, raw scan, archive scan, repack and equality validation |
| `card_vocab.py` | Immutable `card_vocab_v1.json` and explicit unknown bucket |
| `mlops_registry.py` | Episode catalog, fixed split, rolling canary, PSI, threshold calibration and phase policy |
| `extract.py` | Replay state/action tensor extraction; raw-first and archive fallback |
| `train_bc.py` | Full BC followed by full AWR retraining; no newest-batch-only fine-tuning |
| `evaluate_canary.py` | Fixed-test/canary action accuracy and PSI metric producer |
| `update_controller.py` | Warmup-gated full retraining trigger controller |
| `run_training_tests.py` | Three-round unit/integration/end-to-end validation runner |
| `ptcg_replay_harvester.py` | Leaderboard snapshots, episode ID diff, permanent raw storage and post-crawl finalize |

## Data Flow

```text
leaderboard snapshot
        |
        v
episode_id diff ---> raw/ append-only ---> episode_catalog.jsonl
        |                                      |
        +------------------------------+-------+
                                       v
                         full raw scan + zstd repack
                                       |
                                       v
                          frozen card vocabulary extraction
                                       |
                                       v
                 fixed_test / rolling_canary / train splits
                                       |
                                       v
                              BC -> AWR full retrain
                                       |
                                       v
                         canary accuracy + feature PSI
```

## Initial Training

The initial run must not enable drift-triggered retraining.

```bash
python3 inference/dataset/mlops_registry.py bootstrap \
  --root inference/leaderboard_replay \
  --manifest inference/leaderboard_replay/manifest.jsonl

python3 inference/dataset/build_manifest.py
python3 inference/dataset/replay_archive.py finalize \
  --raw-dir inference/leaderboard_replay/raw \
  --output inference/leaderboard_replay/archive/raw_replays.jsonl.zst \
  --report inference/leaderboard_replay/archive/raw_replays.validation.json

python3 inference/dataset/extract.py \
  --raw-dir inference/leaderboard_replay/raw \
  --out inference/dataset/data

python3 inference/dataset/train_bc.py \
  --phase all --epochs-bc 6 --epochs-awr 4 --bs 4096
```

For AWR continuation after BC has already converged, resume from the BC model
and monitor the rolling canary. The current best model is retained separately
until fixed-test comparison is complete:

```bash
python3 inference/dataset/train_bc.py \
  --phase awr \
  --resume-from inference/dataset/data/model_bc.pt \
  --epochs-awr 20 --early-stop-patience 5 \
  --model-output inference/dataset/data/model_awr_extended.pt \
  --best-model-output inference/dataset/data/model_awr_extended.best.pt
```

Early stopping monitors canary top1, while fixed-test metrics are used only for
the final comparison. A saved best epoch is loaded before the output model is
written.

## Quality-Filtered AWR Experiment

After a new data collection round, rebuild tensors first. The extractor records
the replay's `rank_at_capture`, captured-team index, and whether each decision
belongs to that team. This prevents retaining the opponent's view when applying
rank filtering.

Prepare a top-50% captured-team subset with winner and late-turn weights:

```bash
python3 inference/dataset/quality_subset.py \
  --data-dir inference/dataset/data \
  --output-dir inference/dataset/quality_top50 \
  --top-ratio 0.5 \
  --win-bonus 1.5 \
  --late-turn-start 10 \
  --late-turn-bonus 1.25
```

Run the AWR sweep from the same BC checkpoint:

```bash
python3 inference/dataset/awr_sweep.py \
  --data-dir inference/dataset/data \
  --bc-model inference/dataset/data/model_bc.pt \
  --output-dir inference/dataset/awr_sweep_top50 \
  --sample-index inference/dataset/quality_top50/sample_indices.npy \
  --sample-weights inference/dataset/quality_top50/sample_weights.npy \
  --epochs 20 --patience 5
```

The sweep compares canary and fixed-test Top1/Recall for each temperature,
weight cap, learning rate, and batch-size configuration. It does not redownload
data or rerun BC.

After the fixed-test metric has plateaued and at least 100 canary episodes are
available, enable monitoring explicitly:

```bash
python3 inference/dataset/mlops_registry.py mark-baseline \
  --state inference/dataset/mlops_state.json \
  --sample-size 100 --metric-plateau
```

## Recurring Update

The crawler now calls `get_episodes()` even when the submission ID is
unchanged. It downloads only unseen episode IDs. At the end of every successful
`harvest` or `incremental` command it executes:

1. Full raw JSON/schema/duplicate-ID scan.
2. Full zstd repack into `archive/raw_replays.jsonl.zst`.
3. Full archive stream scan.
4. Raw/archive record-count and step-count equality validation.
5. `raw_replays.validation.json` report creation.

`--no-finalize` exists only for emergency recovery and is not the normal path.

## Archive Fallback

`extract.py` uses raw files first. If the raw directory is missing or cannot be
opened, it searches these paths in order:

1. `inference/leaderboard_replay/archive-firstarchive/raw_replays.jsonl.zst`
2. `inference/leaderboard_replay/archive/raw_replays.jsonl.zst`

The current formal run used the raw directory. The second path exists and was
validated; the first requested path does not exist locally.

## Trigger Policy

Only these two drift signals are actionable:

- action-matching accuracy decline on the rolling canary;
- scalar-feature PSI drift.

Win rate is not used because the local environment cannot provide valid
self-play win-rate measurements. Initial thresholds are configurable heuristics
in `mlops_config.json` and are recalibrated after normal monitoring windows.
The trigger remains blocked until BC completion, metric plateau and minimum
canary sample gates are all true.
