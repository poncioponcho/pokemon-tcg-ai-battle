# Kaggle Code Competition Pipeline

Use this reference when a Kaggle competition scores a notebook/kernel, reruns code on hidden data, or needs a staged model architecture.

Read `information-sharing-policy.md` before publishing any final scoring kernel, producer kernel, artifact dataset, model dataset, or downloaded output.

## Kaggle-First Defaults

Assume the work should finish on Kaggle, not locally:

- Build and run the final scoring artifact as a Kaggle notebook/script.
- Keep competition data mounted through `competition_sources`.
- Keep trained models, feature stores, embeddings, and other reusable producer outputs mounted through `dataset_sources`.
- Keep internet-independent scoring paths unless the rules explicitly allow otherwise.
- Record kernel refs, kernel versions, dataset handles, dataset versions, run IDs, and submission receipts.

The end condition is not a local prediction file. It is a processed Kaggle submission status/score, or a concrete external blocker that prevents scoring.

## Producer Model Dataset Pattern

For most complicated code-competition architectures, producer notebooks should train models and publish their outputs as private Kaggle datasets:

1. Producer training notebook runs on Kaggle GPU/TPU when useful.
2. It writes model artifacts to `/kaggle/working`, such as `.pt`, `.pth`, `.ckpt`, `.safetensors`, `.pkl`, `.joblib`, tokenizer files, configs, label maps, fold metadata, OOF predictions, test predictions, and logs.
3. It writes `model_manifest.json` and `artifact_dataset_manifest.json` with source kernel, kernel version, run ID, fold coverage, model family, metric, expected input schema, output columns, checksums if available, and inference entrypoint.
4. After the producer completes, retrieve the notebook output and create or version a private Kaggle dataset from those files.
5. Downstream producer or final consumer notebooks attach that dataset in `kernel-metadata.json` `dataset_sources`.
6. Consumer code loads from `/kaggle/input/DATASET_SLUG/...`, validates the manifest, then performs inference, blending, stacking, calibration, or postprocessing.

Use `kernel_sources` only for short-lived notebook-output chains. Prefer datasets for trained models because datasets are versioned, durable, reusable, and explicit in the final consumer's input list.

## Dependency Graph

Keep the graph shallow and auditable:

- Producer nodes create one artifact family each: fold checkpoints, embeddings, feature tables, pseudo labels, calibration data, distilled models, OOF/test predictions, or preprocessing assets.
- Consumer nodes combine or use those artifacts: model inference, blend, stack, calibrate, threshold, postprocess, and write the final submission.
- Use fewer than five independent producers in a wave. Start a second wave only after reviewing OOF metrics, artifact manifests, and resource cost.
- The final consumer is the scoring boundary. It must consume all required producer datasets before scoring.

Maintain `pipeline_manifest.json` with:

```json
{
  "pipeline_id": "exp_042",
  "competition": "competition-slug",
  "kind": "code_competition",
  "producers": [
    {
      "stage": "train_transformer_fold_models",
      "kernel": "user/exp-042-train-transformer",
      "kernel_version": "8",
      "produced_dataset": "user/exp-042-transformer-models",
      "dataset_version": "2",
      "outputs": ["fold0/model.safetensors", "model_manifest.json"],
      "status": "complete"
    }
  ],
  "final_consumer": {
    "kernel": "user/exp-042-final-inference",
    "consumes_datasets": ["user/exp-042-transformer-models/versions/2"],
    "submission": {
      "status": "pending",
      "public_score": null
    }
  }
}
```

Update this manifest after each producer completion, dataset create/version, consumer run, submission, retry, and score retrieval.

## Final Consumer Requirements

Before submitting a code-competition kernel/version, the final consumer must:

- Attach every required producer model/artifact dataset.
- Load model files only from attached datasets, competition inputs, or approved model sources.
- Validate manifests, file existence, fold coverage, expected columns, label order, and prediction shape before inference.
- Avoid hidden-data assumptions, hard-coded visible-test row counts, and network downloads in scoring code.
- Use conservative memory settings: small batches, limited workers, cleanup between models, compressed artifacts, and limited TTA.
- Write `submission.csv`, `experiment_log.json`, `metrics.jsonl`, `pipeline_manifest.json`, and `submission_receipt.json`.

Submit the final consumer kernel/version for scoring, then retrieve the submission status/score. If scoring fails, debug the final consumer first; rerun producer notebooks only when the failure implicates a missing, corrupt, incompatible, or rules-invalid producer artifact.

## Commands

Producer run:

```bash
kaggle kernels push -p kaggle_kernels/exp_042_train_transformer
kaggle kernels status user/exp-042-train-transformer
kaggle kernels output user/exp-042-train-transformer -p kaggle_datasets/exp_042_transformer_models -o
```

Promote producer output to a model artifact dataset:

```bash
python3 <skill-dir>/scripts/prepare_kaggle_dataset.py \
  --output kaggle_datasets/exp_042_transformer_models \
  --username user \
  --slug exp-042-transformer-models \
  --title "exp 042 transformer models" \
  --description "Trained fold model artifacts from exp_042_train_transformer" \
  --artifact-kind model \
  --source-kernel user/exp-042-train-transformer \
  --source-run-id exp_042_train_transformer
kaggle datasets create -p kaggle_datasets/exp_042_transformer_models -t -r zip
```

Final consumer metadata should attach the produced model dataset:

```json
{
  "dataset_sources": ["user/exp-042-transformer-models"],
  "competition_sources": ["competition-slug"],
  "kernel_sources": []
}
```

Submit final code-competition kernel/version:

```bash
kaggle kernels push -p kaggle_kernels/exp_042_final_inference
kaggle kernels status user/exp-042-final-inference
kaggle competitions submit competition-slug -f submission.csv -k user/exp-042-final-inference -v KERNEL_VERSION -m "exp_042 final consumer"
kaggle competitions submissions competition-slug -v -q
```
