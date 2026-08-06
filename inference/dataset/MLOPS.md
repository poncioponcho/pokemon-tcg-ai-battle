# Replay MLOps Workflow

This pipeline uses incremental collection and full retraining. It does not
fine-tune a model on only the newest replay batch.

## Immutable data

- `inference/leaderboard_replay/raw/` is append-only and keyed by `episode_id`.
- `episode_catalog.jsonl` records the first successful capture, SHA-256, and
  `rank_at_capture`.
- `leaderboard_snapshots.jsonl` and `snapshots/*.json` preserve leaderboard
  history independently of replay files.

## Compressed replay archive

`inference/dataset/replay_archive.py` creates a streamable JSONL+Zstandard
archive.  It keeps one replay per compressed line, so a scanner does not need
to extract the full dataset:

```bash
python3 inference/dataset/replay_archive.py pack \
  --raw-dir inference/leaderboard_replay/raw \
  --output inference/leaderboard_replay/archive/raw_replays.jsonl.zst \
  --level 5

python3 inference/dataset/replay_archive.py scan \
  --archive inference/leaderboard_replay/archive/raw_replays.jsonl.zst
```

After the archive manifest and scan count have been verified, `raw/` may be
removed to reclaim space.  Restore it later with:

```bash
python3 inference/dataset/replay_archive.py extract \
  --archive inference/leaderboard_replay/archive/raw_replays.jsonl.zst \
  --raw-dir inference/leaderboard_replay/raw
```

Training tensors remain uncompressed `.npy` files for memory mapping and fast
random access.  If raw files have been removed, extraction can rebuild the
tensors directly from the archive, one replay at a time:

```bash
python3 inference/dataset/extract.py \
  --archive inference/leaderboard_replay/archive/raw_replays.jsonl.zst
```

Archive extraction is slower than the default multiprocessing raw-file path,
but it uses bounded memory.  It does not affect `train_bc.py` once tensors
already exist.

## Storage scheme (archive-first, disk ~90 GB free)

The complete live ≥600-point dataset is ~22,800 episodes ≈ 90 GB raw, which
does not fit alongside the rest of the project.  Adopted layout:

- `archive/raw_replays.jsonl.zst` is the canonical copy (~1.6 GB for the full
  set; repacked after every crawl by the off-peak scheduler).
- `raw/` is a working cache only.  When disk pressure grows, delete `raw/*.json`
  wholesale: the crawler treats `episode_catalog.jsonl` as authoritative and
  will NOT re-download archived episodes (incremental/harvest both check it).
- `dataset/data/*.npy` tensors stay on disk (~12 GB at full volume) because
  `train_bc.py` memory-maps them; regenerate from the archive when needed:
  `python3 inference/dataset/extract.py --archive ...`.
- `parsed/` is regenerable and normally not stored; `replay_archive.py extract`
  + `ptcg_replay_harvester.py parse` rebuild it on demand.

```bash
# Rebuild raw files from the archive when training needs them
python3 inference/dataset/replay_archive.py extract \
  --archive inference/leaderboard_replay/archive/raw_replays.jsonl.zst \
  --raw-dir /tmp/raw_work

# Verify an archive is complete before relying on it
python3 inference/dataset/replay_archive.py scan --archive <archive>
```

## Official bulk source

For dated historical snapshots, prefer the official Kaggle Dataset artifact
route over thousands of per-episode replay calls:

```bash
python3 inference/dataset/bulk_replay_source.py download \
  --dataset kaggle/pokemon-tcg-ai-battle-episodes-2026-07-30 \
  --output /path/to/official_bulk_2026-07-30

python3 inference/dataset/bulk_replay_source.py inspect \
  --root /path/to/official_bulk_2026-07-30
```

This is a bulk-download path, not a limit bypass: it still uses Kaggle's
official authenticated delivery and the snapshot is dated.  It has no live
leaderboard rank/score mapping, so keep it as a separate historical source
unless a matching snapshot manifest is available.  The local cache already
contains this source with 4,384 JSON replays.

Run the crawler with competition dates when available:

```bash
python3 inference/ptcg_replay_harvester.py \
  --out inference/leaderboard_replay incremental \
  --top 20 --max-episodes 30 \
  --competition-start 2026-08-01T00:00:00Z \
  --competition-end 2026-08-15T00:00:00Z
```

The crawler polls episode IDs even when `best_submission_id` is unchanged and
downloads only IDs absent from the catalog/raw directory.

If the current download round predates this registry, bootstrap it once after
the downloader finishes:

```bash
python3 inference/dataset/mlops_registry.py bootstrap \
  --root inference/leaderboard_replay \
  --manifest inference/leaderboard_replay/manifest.jsonl
```

## Frozen vocabulary and splits

`card_vocab_v1.json` is created once and never reordered. New card IDs use the
explicit unknown bucket until a deliberate `card_vocab_v2` full rebuild.

`episode_splits.jsonl` assigns each episode permanently to `train` or
`fixed_test`. `rolling_canary.json` contains the newest non-test episodes and
is excluded from training for the current run.

The first baseline can be trained with:

```bash
python3 inference/dataset/build_manifest.py
python3 inference/dataset/extract.py
python3 inference/dataset/train_bc.py --phase all
```

Only after BC has completed, the fixed-test metric has plateaued, and the
canary has enough episodes should monitoring be enabled:

```bash
python3 inference/dataset/mlops_registry.py mark-baseline \
  --state inference/dataset/mlops_state.json \
  --sample-size 100 --metric-plateau
```

`--mark-converged` is intentionally explicit so unstable initial training
cannot trigger retraining; it can also be passed to the final baseline
training invocation instead of the command above.

## Drift and full retraining

The controller accepts a metrics JSON containing:

```json
{
  "base_episode_count": 4090,
  "new_episode_count": 250,
  "canary_episode_count": 100,
  "baseline_accuracy": 0.52,
  "canary_accuracy": 0.46,
  "psi": 0.24
}
```

The metrics can be produced from the current model and tensors with:

```bash
python3 inference/dataset/evaluate_canary.py \
  --new-episode-count 250 \
  --output canary_metrics.json
```

Evaluate without starting training:

```bash
python3 inference/dataset/update_controller.py \
  --metrics metrics.json --phase final
```

Add `--run-train` to run a complete BC+AWR retraining only when the warmup
gate, data-volume trigger, action-accuracy trigger, or PSI trigger permits it.
Win rate is intentionally not used because the local replay pipeline has no
valid self-play win-rate measurement.

The values in `mlops_config.json` are initial heuristics. After five or more
normal monitoring windows, prior accuracy drops and PSI values calibrate the
thresholds using the configured quantile and safety multiplier.

## Competition phases

- Early: snapshot polling every 24 hours; retraining cooldown is one week.
- Mid: polling every 6 hours; retraining cooldown is one day.
- Final: polling every hour; retraining cooldown is six hours.

These are scheduling defaults, not immutable thresholds. The raw and snapshot
history remains available for later full reconciliation.
