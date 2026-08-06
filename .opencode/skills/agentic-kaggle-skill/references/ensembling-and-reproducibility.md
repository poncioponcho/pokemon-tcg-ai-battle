# Ensembling And Reproducibility

## Project Layout

A practical competition layout:

```text
input/
notebooks/
src/
models/
oof/
submissions/
logs/
configs/
kaggle_kernels/
kaggle_datasets/
remote_outputs/
```

Keep raw downloaded data in `input/` and treat it as read-only. Put repeatable training code in `src/`; use notebooks for EDA, visual checks, and quick diagnostics.

## Script Pattern

Prefer command-driven training:

```bash
python src/train.py --fold 0 --model lgbm --config configs/lgbm.yaml
python src/predict.py --model-dir models/lgbm_fold0 --output submissions/lgbm_fold0.csv
```

Keep model dispatch separate from training loops when many models share the same dataset and metric. Save enough metadata that another run can reproduce the exact artifact.

## Required Artifacts

For each run, save:

- Config/params.
- Fold assignments or fold source file path.
- Per-fold metric and mean/std.
- OOF predictions.
- Test predictions per fold and averaged test predictions.
- Feature list and categorical column list.
- Model files or checkpoints.
- Submission file.
- Notes on public LB result if submitted.
- Kaggle submission receipt/status and public score after scoring.
- Remote run logs and downloaded Kaggle outputs when compute was offloaded.
- Pipeline manifests and intermediate Kaggle dataset handles/versions for multi-notebook runs.

## Blending

Start with simple averaging for similar probability outputs. Try weighted averages when OOF scores and error correlations justify it.

For rank-like metrics or differently calibrated models, rank averaging can be safer than raw averaging.

Use OOF predictions to search blend weights. Keep the search small enough to avoid fitting noise.

For sophisticated notebook architectures, keep a model-correlation or disagreement report in the final consumer. A producer that is not best alone can still be valuable if it improves the OOF blend without increasing leakage risk.

## Stacking

Stack only with OOF base predictions:

1. Train base models on K-1 folds and predict the held-out fold.
2. Concatenate OOF base predictions into a level-1 train matrix.
3. Average each base model's test predictions across folds for the level-1 test matrix.
4. Train the stacker on the level-1 train matrix using the same or a nested validation plan.

Good stackers are often simple: logistic regression, ridge, linear models, shallow boosting, or constrained weighted averages. Complex stackers can overfit quickly.

Blending is stacking with a holdout set instead of full OOF folds. Use it when runtime is limited, but prefer OOF stacking when data is scarce.

## Reproducibility Guardrails

- Set seeds for Python, NumPy, model libraries, and deep-learning frameworks.
- Log package versions and hardware assumptions when results are sensitive.
- Use deterministic data paths and run IDs.
- Avoid hidden notebook state for anything that affects submissions.
- Keep train/test row order explicit through ID columns.
- Version feature generation and preprocessing.
- Make every submitted file traceable to code, config, data, and OOF score.
- Make every Kaggle score traceable to the exact submission file or kernel/version that produced it.
- For Kaggle-offloaded runs, keep the pushed kernel folder, `kernel-metadata.json`, downloaded `experiment_log.json`, `metrics.jsonl`, and output artifacts together under `remote_outputs/RUN_ID/`.
- For multi-notebook runs, keep producer dataset folders under `kaggle_datasets/` and final downloaded outputs under `remote_outputs/CONSUMER_RUN_ID/`.
