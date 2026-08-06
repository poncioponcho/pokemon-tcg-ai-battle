# Training Execution Report

Date: 2026-08-04/05 local execution window

## Data Source and Validation

| Item | Result |
|---|---:|
| Raw source | `inference/leaderboard_replay/raw` |
| Raw replay files | 4432 |
| Unique episode IDs | 4432 |
| Raw steps | 636297 |
| Valid action decisions | 525371 |
| Archive source | `inference/leaderboard_replay/archive/raw_replays.jsonl.zst` |
| Archive records | 4432 |
| Archive unique IDs | 4432 |
| Archive steps | 636297 |
| Duplicate IDs | 0 |
| Invalid raw/archive records | 0 |
| Finalize status | `ok` |

The requested `archive-firstarchive/raw_replays.jsonl.zst` path was not present.
The existing `archive/raw_replays.jsonl.zst` path was used for validation and is
registered as the automatic fallback. The formal training run used raw files
because they were readable.

Archive fallback smoke test: an unavailable raw directory automatically selected
the existing archive and extracted 3 episodes / 352 decisions successfully.

## Test Gate

Three complete rounds were executed by `run_training_tests.py`.

| Test layer | Per-round result | Rounds |
|---|---|---:|
| Unit: registry/vocabulary/warmup/crawler diff | 8 tests passed | 3 |
| Integration: sample raw -> zstd -> archive validation | 3 records, 0 invalid | 3 |
| End-to-end: extraction -> BC -> AWR CPU smoke run | passed | 3 |

All three rounds passed before formal training. Additional project regression
checks passed: agent `21/21`, replay regression `100%` legal actions, and Python
compile checks passed.

After adding resume/early-stopping controls, the complete three-round suite was
run again and passed; the focused training-control suite passed 11/11.

## Formal Training Parameters

| Parameter | Value |
|---|---:|
| Device | Apple MPS |
| Python | 3.14.5 |
| PyTorch | 2.12.0 |
| Seed | 42 |
| Decisions | 525371 |
| Train episodes | 3862 |
| Fixed-test episodes | 470 |
| Rolling-canary episodes | 100 |
| Batch size | 4096 |
| BC epochs | 6 |
| AWR epochs | 4 |
| Learning rate | 0.001 |
| AWR temperature | 0.5 |
| AWR weight cap | 20 |
| Card vocabulary | `card_vocab_v1`, 399 cards + unknown bucket |

## Metrics

| Stage | Fixed-test recall | Fixed-test top1 | Canary recall | Canary top1 |
|---|---:|---:|---:|---:|
| Initial/random | 0.2640 | 0.2136 | - | - |
| After BC | 0.3758 | 0.5207 | - | - |
| After AWR | 0.3908 | 0.5318 | 0.3860 | 0.5377 |

## AWR Extension

The original `model_awr.pt` was preserved as
`model_awr_before_awr20.pt`. A separate continuation resumed from
`model_bc.pt`, requested 20 AWR epochs, and used canary top1 with patience 5.
It stopped at epoch 15; the best canary score was at epoch 10.

| Model | Fixed-test recall | Fixed-test top1 | Canary recall | Canary top1 |
|---|---:|---:|---:|---:|
| Original AWR-4 | 0.3908 | 0.5318 | 0.3860 | 0.5377 |
| Extended AWR best | **0.4026** | **0.5332** | **0.3995** | **0.5432** |

The extended best model was promoted to `model_awr.pt`. The independent files
`model_awr_extended.pt` and `model_awr_extended.best.pt` remain available for
comparison.

## Next Data Round

The quality-filter and AWR sweep framework is prepared but was not run against
the current data. It will be executed only after the next crawler/archive round
finishes, because the experiment is intended to measure whether rank-quality
filtering improves the new distribution rather than overfit the current one.

Model artifacts:

- `inference/dataset/data/model_bc.pt`
- `inference/dataset/data/model_awr.pt`
- `inference/dataset/data/model_meta.json`
- `inference/dataset/data/eval_report.json`

## Monitoring State

Monitoring remains disabled after the initial run:

```json
{
  "monitoring_enabled": false,
  "bc_completed": false,
  "metric_plateau": false
}
```

This is intentional. It prevents the first training run from treating normal
loss/accuracy movement as environmental drift. Enable it only after an explicit
plateau review using `mlops_registry.py mark-baseline`.

## Final Submission Cycle (2026-08-05)

Formal retraining on the same frozen 4432-episode tensors completed: BC 6 epochs
then AWR with canary-based early stopping (stopped at epoch 12, best canary at
epoch 7). The promoted best model (`model_awr.pt`, fixed top1 0.5332, canary
top1 0.5432) was preserved and re-verified after the run.

Evaluation:

- Scalar PSI 0.018 (no drift)
- NN vs rule agent on 5479 real observations: NN exact-match 37.7% vs rule
  21.8%; NN legal rate 100%
- Per-context breakdown and project adjustment decisions are in
  `PROJECT_EVALUATION_REPORT.md`

Full test gate passed after training:

- Three complete rounds (unit + integration + end-to-end)
- Agent regression 24/24
- Replay regression 100% legal, zero missed attacks

Submission package rebuilt from the latest synced `main.py` (v23.1) +
`deck.csv` (60 cards), verified in tar before upload.
