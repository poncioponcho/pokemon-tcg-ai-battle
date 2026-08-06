# Kaggle Pipeline Datasets

Use this reference when a solution needs several remote stages, intermediate artifacts, advanced producers/consumers, or Python-level access through `kagglehub`.

## Multi-Notebook Pattern

Use a small directed pipeline instead of a single overloaded notebook:

1. Run fewer than five independent producer notebooks/scripts in parallel or as one wave, chosen for model/feature diversity.
2. Each producer owns one expensive artifact family: features, embeddings, fold checkpoints, pseudo labels, image crops, text chunks, OOF/test predictions, or distilled model outputs.
3. Each producer writes `experiment_log.json`, `metrics.jsonl`, `artifacts_manifest.json`, and a compact data contract describing its artifacts.
4. Promote durable producer notebook outputs to private Kaggle datasets, or attach notebook outputs directly with `kernel_sources` only for short-lived chains.
5. Run one final consumer notebook/script that attaches the producer-created datasets as input datasets, validates schemas and row order, writes final OOF/test/submission artifacts, submits the final artifact/kernel to Kaggle for scoring, and records the resulting submission status/score.

Do not exceed the user's intended pipeline size without asking. If more than five producers seem necessary, batch them into waves and document why.

For performance-oriented architecture selection, read `advanced-notebook-architecture.md` before deciding the producer set.

## Artifact Dataset Rules

Use Kaggle datasets for intermediate artifacts when outputs are large, expensive to recompute, needed by multiple notebooks, useful across experiments, or should be versioned.

Read `information-sharing-policy.md` before making any artifact dataset public. Intermediate artifacts often derive from competition data and should stay private unless the target rules and licenses clearly allow redistribution.

Producer notebook outputs can become Kaggle datasets. Use this as the preferred bridge between independent notebooks:

1. Producer notebook writes artifacts to `/kaggle/working`: feature tables, embeddings, checkpoints, OOF/test predictions, manifests, or logs.
2. After the producer completes, save/version those outputs as a private Kaggle dataset.
3. Downstream notebooks list that dataset handle in `dataset_sources`.
4. Downstream code reads the mounted dataset from `/kaggle/input/...`, validates the artifact manifest, and logs the consumed dataset handle/version.

If direct Kaggle UI output-to-dataset creation is available, it can be used. From a local agent workflow, the portable CLI-compatible path is: `kaggle kernels output` into a `kaggle_datasets/STAGE` folder, prepare dataset metadata, then `kaggle datasets create` or `kaggle datasets version`.

Keep each artifact dataset narrow:

- Use one dataset per logical stage or reusable artifact family.
- Prefer Parquet/NumPy/NPZ/safetensors/model checkpoint formats that preserve types and avoid accidental CSV conversion.
- Include schema files for feature tables and prediction files.
- Include `artifact_dataset_manifest.json` with run ID, source kernel, source commit, source config, fold coverage, row counts, checksums if available, and file descriptions.
- Include the source producer kernel ref/version and whether the dataset was created from notebook output, downloaded output, or locally generated artifacts.
- Keep datasets private unless the user explicitly wants public artifacts and the target rules, data license, and third-party IP checks allow public redistribution.

Use `kaggle datasets create` for the first version and `kaggle datasets version` for later versions. Use `--keep-tabular` for Parquet or other files that should not be converted, and choose directory mode deliberately when nested checkpoint folders are present.

## Model Artifact Datasets

In code competitions and heavyweight architectures, the most common durable handoff is: train a model in a producer notebook, save the trained model as a private Kaggle dataset, then attach that dataset to the final inference notebook.

Producer model datasets should include:

- Model/checkpoint files: `.pt`, `.pth`, `.ckpt`, `.safetensors`, `.bin`, `.pkl`, `.joblib`, or framework-specific directories.
- Inference dependencies: tokenizer/config files, preprocessing assets, label maps, feature schema, fold metadata, and any small custom modules allowed by the competition rules.
- Evaluation artifacts: OOF predictions, fold metrics, test predictions if produced, and error-analysis slices.
- `model_manifest.json`: model family, architecture, training config, source kernel/version, source dataset versions, fold coverage, expected input columns/files, prediction columns/classes, device assumptions, batch-size guidance, and checksums if available.

Downstream notebooks must treat the model dataset as immutable input. Load from `/kaggle/input/DATASET_SLUG/...`, verify `model_manifest.json`, and fail early if a file, class order, schema, or fold is missing. Do not rely on the producer notebook being rerun during final scoring.

## Consumer Notebook Rules

The final consumer must:

- Attach all producer-created dataset handles in `kernel-metadata.json` `dataset_sources` when those artifacts are durable or reused; reserve `kernel_sources` for short-lived direct notebook-output chains.
- Validate artifact manifests before loading data.
- Check expected files, row counts, IDs, fold columns, prediction columns, target label order, model versions, and schema hashes if present.
- Log which artifact version was consumed.
- Fail fast if a producer artifact is missing or incompatible.
- Save final OOF predictions, final test predictions, blend/stack weights, metric report, and submission.
- Be the only scoring boundary for the architecture unless the user explicitly asks for producer-stage scoring.
- Submit the produced `submission.csv` or code-competition kernel version to Kaggle for scoring after all producers are consumed.
- Retrieve the Kaggle submission status/score and write it to `submission_receipt.json` and `pipeline_manifest.json`.
- If the final consumer scores with an error, run the code-competition debugging loop on the final consumer; do not rerun producers unless their artifacts are implicated.

## Pipeline Manifest

Maintain `pipeline_manifest.json` locally and in final outputs:

```json
{
  "pipeline_id": "exp_042",
  "competition": "competition-slug",
  "producers": [
    {
      "stage": "train_model",
      "kernel": "user/exp-042-train-model",
      "kernel_version": "7",
      "dataset": "user/exp-042-model-artifacts",
      "version": "3",
      "created_from": "producer_notebook_output",
      "outputs": ["fold0/model.safetensors", "model_manifest.json", "oof.parquet"],
      "status": "complete"
    }
  ],
  "consumer": {
    "kernel": "user/exp-042-final",
    "consumes_datasets": ["user/exp-042-model-artifacts/versions/3"],
    "outputs": ["submission.csv", "oof_final.parquet"],
    "submission": {
      "status": "complete",
      "public_score": "0.12345",
      "submitted_at": "2026-06-11T00:00:00Z"
    }
  }
}
```

The manifest is the agent's memory between remote runs. Update it after each push, status poll, dataset version, output retrieval, submission, and score retrieval.

## Command Sketch

Producer kernel:

```bash
kaggle kernels push -p kaggle_kernels/exp_features --accelerator NvidiaTeslaT4
kaggle kernels status user/exp-features
kaggle kernels output user/exp-features -p remote_outputs/exp_features -o
```

Promote downloaded producer artifacts to a private dataset:

```bash
kaggle kernels output user/exp-features -p kaggle_datasets/exp_features -o
python3 <skill-dir>/scripts/prepare_kaggle_dataset.py \
  --output kaggle_datasets/exp_features \
  --username user \
  --slug exp-features \
  --title "exp features" \
  --description "Feature artifacts from exp_features"
kaggle datasets create -p kaggle_datasets/exp_features -t -r zip
```

Consumer kernel metadata should include the produced dataset handle:

```json
{
  "dataset_sources": ["user/exp-features"],
  "kernel_sources": [],
  "competition_sources": ["competition-slug"]
}
```

After the consumer finishes, submit and fetch score:

```bash
kaggle competitions submit competition-slug -f remote_outputs/exp_final/submission.csv -m "exp_042 final consumer"
kaggle competitions submissions competition-slug -v -q
```

For code competitions, submit the final consumer kernel/version:

```bash
kaggle competitions submit competition-slug -f submission.csv -k user/exp-042-final -v KERNEL_VERSION -m "exp_042 final consumer"
kaggle competitions submissions competition-slug -v -q
```

## KaggleHub Usage

Inside Python:

```python
import kagglehub

competition_dir = kagglehub.competition_download("competition-slug")
features_dir = kagglehub.dataset_download("user/exp-features")
prior_output_dir = kagglehub.notebook_output_download("user/exp-features-kernel")
kagglehub.dataset_upload("user/exp-features", "kaggle_datasets/exp_features", version_notes="new features")
```

Use CLI commands when orchestrating from the local workspace. Use `kagglehub` when the code is already running in Python or inside Kaggle.
