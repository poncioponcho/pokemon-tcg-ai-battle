# Advanced Notebook Architecture

Use this reference when a Kaggle competition is likely to benefit from a stronger staged solution rather than a single baseline notebook.

## When To Escalate

Proactively escalate after a metric-correct baseline exists when any of these are true:

- Public notebook/discussion intel shows strong solutions using multiple models, external pretrained features, staged inference, stacking, pseudo-labeling, or custom postprocessing.
- The data is multimodal, high-dimensional, large, grouped, time-based, image/text-heavy, or expensive to featurize.
- A single baseline plateaus while fold variance and error analysis show recoverable errors.
- The metric rewards calibration, ranking, thresholding, segmentation postprocessing, sequence aggregation, or ensembling.
- GPU inference/training, embeddings, or fold models are too heavy for local execution.

Do not overcomplicate before the split, metric, submission format, and one reliable baseline are correct.

## Architecture Pattern

Use a shallow DAG:

1. Baseline notebook/script: metric-correct OOF/test predictions and valid submission.
2. Producer notebooks/scripts: independent heavy stages that can run in parallel, especially model-training producers for code competitions.
3. Artifact datasets: each useful producer output is saved/versioned as a private Kaggle dataset; trained producer models should be exported with checkpoints, configs, OOF predictions, and manifests.
4. Consumer notebook/script: attaches producer datasets, loads models from `/kaggle/input/...`, validates artifacts, blends/stacks/postprocesses, writes final submission, submits for scoring, and records score/status.

Keep one wave to fewer than five producer notebooks unless the user approves more. Prefer another wave after reviewing OOF artifacts over launching a sprawling graph.

## Producer Ideas

Choose producers that create diversity:

- Tabular: LightGBM/XGBoost/CatBoost variants, neural tabular embeddings, target/count/stat features, time/group aggregations, adversarial-drift features.
- Text: TF-IDF linear baseline, transformer embeddings, fine-tuned transformer logits, retrieval/reranking features, language/source metadata.
- Images: different backbones/resolutions, segmentation masks, crop generators, test-time augmentation predictions, embedding extractors.
- Time series: rolling/lag feature stores, sequence models, entity-level aggregate features, horizon-specific models.
- Multimodal: separate text/image/tabular producers plus a late-fusion consumer.
- Meta-modeling: calibrated probabilities, threshold search, rank averaging, stacking, pseudo-label generation, distillation, uncertainty estimates.

Every producer must write OOF predictions when it trains on labels. Without OOF predictions, its output is not safe for stacking.

When a producer trains a model for a downstream code-competition consumer, it must also write a model artifact dataset contract: checkpoint paths, tokenizer/config paths, label order, fold IDs, expected input schema, inference batch-size guidance, metric summary, and source kernel/version.

## Promotion Gates

Promote a producer output to the final consumer when at least one is true:

- It improves mean CV beyond noise.
- It reduces fold variance or fixes a known error cluster.
- It adds ensemble diversity despite not winning alone.
- It enables a downstream stage such as pseudo-labeling, postprocessing, or calibration.

Reject or quarantine producers with suspicious train/valid gaps, schema drift, unexplainable public LB-only gains, or artifacts that cannot be reproduced.

## Consumer Responsibilities

The final consumer is the only scoring boundary for the full architecture unless the user asks otherwise.

It must:

- Attach producer-created dataset handles through `dataset_sources`.
- Load trained producer models from attached Kaggle datasets, not from local paths or rerunning upstream notebooks.
- Validate every artifact manifest, schema, row count, ID order, fold coverage, model version, and prediction column.
- Compare model correlation/diversity before blending or stacking.
- Use OOF predictions for blend weights, stackers, thresholds, calibration, and postprocessing.
- Write final OOF/test predictions, blend/stack report, submission, `pipeline_manifest.json`, and `submission_receipt.json`.
- Submit the final artifact or kernel/version to Kaggle and retrieve score/status.

## Practical Escalation Order

1. Strong single-model baseline.
2. Add one high-signal feature/embedding producer.
3. Add one diverse model-family producer.
4. Add one domain-specific postprocessing or calibration stage.
5. Blend or stack producers using OOF predictions.
6. If score improves and resources remain, start a second producer wave.

If Kaggle submission quota is scarce, prefer OOF-validated improvements and visible kernel tests before spending another scoring attempt.
