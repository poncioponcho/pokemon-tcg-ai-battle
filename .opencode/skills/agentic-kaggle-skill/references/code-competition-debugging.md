# Code Competition Debugging

Use this reference when a Kaggle code competition submission fails, returns a vague scoring status, OOMs, times out, produces no output, or passes the visible notebook run but fails during hidden rerun/scoring.

Kaggle intentionally limits detailed error messages in code competitions to avoid hidden-test probing. Treat limited feedback as expected. Do not use repeated submissions to infer hidden data, labels, or private test properties; use submissions only to test genuine robustness fixes.

## Debugging Loop

1. Capture the observed failure: submission status, CLI output, kernel status, run/version ID, visible logs, elapsed time, and whether `submission.csv` was produced.
2. Download available outputs and logs:

```bash
kaggle kernels status USER/KERNEL_SLUG
kaggle kernels output USER/KERNEL_SLUG -p remote_outputs/RUN_ID -o
kaggle competitions submissions COMPETITION_SLUG -v -q
```

3. Classify the most likely failure mode using the taxonomy below.
4. Patch the final consumer notebook/script defensively.
5. Run a local smoke test and a Kaggle visible run.
6. Resubmit the final file or kernel/version for scoring.
7. Record the patch and result in `debug_attempts.jsonl` and `submission_receipt.json`.
8. Repeat until scored or an external blocker prevents more retries.

## Failure Taxonomy

- Missing output: `submission.csv` not written, wrong path, wrong working directory, file written after an exception, or output only exists in a subfolder Kaggle does not collect.
- Schema mismatch: wrong columns, wrong order, duplicate IDs, missing IDs, extra index column, bad label names, wrong class order, invalid probability range, NaN/inf values, or row count mismatch.
- Hidden data shape: assumptions from public data fail on hidden data, such as fixed image size, fixed text length, fixed number of files, fixed batch size, unseen classes/categories, or empty groups.
- Path/input mismatch: hard-coded `/kaggle/input/...` paths, dataset slug changes, nested dataset folders, producer artifact version drift, missing model files, or case-sensitive filenames.
- Internet/package issue: internet disabled, pip install attempted during scoring, package version differs, private dataset/model not attached, or imported module unavailable.
- Resource failure: OOM, disk full, timeout, CPU/GPU mismatch, too many workers, large batch size, uncompressed intermediates, model ensemble too large, or slow test-time augmentation.
- Statefulness: notebook relies on previous cell state, hidden global variables, mutable caches, random nondeterminism, or files generated in an earlier run but not in the scoring run.
- Competition API misuse: code competition environment expects a specific inference server, iterator, prediction format, or final write location.
- External-data/rules issue: producer artifacts, pretrained weights, internet downloads, or private datasets are not allowed or not attached according to competition rules.

## Defensive Patches

Add these safeguards to the final consumer before resubmission:

- Centralize paths and print discovered input/output paths.
- Validate all attached datasets, producer manifests, model files, and expected columns before inference.
- Add public-data and synthetic hidden-like smoke tests for empty files, unseen categories, missing optional columns, odd image sizes, long/empty text, tiny batches, and one-row batches.
- Wrap inference stages with concise logging that records stage start/end, shapes, counts, dtypes, memory estimates, and artifact paths.
- Fail early with actionable messages when required artifacts are missing.
- Always write `submission.csv` atomically to the expected directory.
- Sanitize predictions: no NaN/inf, valid label set, valid probability range, expected row count, expected ID set/order.
- Reduce resource pressure: smaller batch size, fewer workers, fp16/bfloat16 if safe, memory cleanup between models, model-by-model inference, compressed artifacts, and limited TTA.
- Avoid hidden-state notebook behavior by using a single script-style entry point for scoring logic.
- Disable network-dependent setup in scoring paths; vendor or attach required code/model/data as datasets.

## Retry Discipline

- Make one hypothesis-driven patch per retry when possible.
- Preserve each submitted kernel/version and `debug_attempts.jsonl` entry.
- Avoid leaderboard probing. A retry should fix robustness, schema, path, dependency, or resource handling.
- If daily submission quota is low, run extra visible Kaggle kernel tests before spending another scoring attempt.
- If the error remains vague after several genuine fixes, summarize attempted fixes and ask the user whether to spend another submission attempt.

## Debug Log Schema

Append one JSON object per attempt to `debug_attempts.jsonl`:

```json
{
  "run_id": "exp_042",
  "attempt": 2,
  "kernel": "user/exp-042-final",
  "kernel_version": "12",
  "submission_status": "Notebook Threw Exception",
  "observed_error": "limited Kaggle code competition error",
  "suspected_failure_class": "resource failure",
  "patch": "reduced batch size and disabled TTA",
  "result": "pending"
}
```

When an attempt scores, copy the final status and public score into `submission_receipt.json` and the pipeline manifest.
