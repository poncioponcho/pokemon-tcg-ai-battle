# Method Map

This skill packages a neutral Kaggle competition workflow. It should provide reusable procedure, scripts, and checklists without depending on or displaying named source material.

## Core Areas

| Area | Use |
| --- | --- |
| Environment setup | Create a repeatable local and Kaggle project layout. |
| Task framing | Identify target type, metric, data constraints, submission mode, and scoring boundary. |
| Validation | Build folds that match hidden-test risk and prevent leakage. |
| Metrics | Reproduce the official metric locally before trusting experiments. |
| Project structure | Keep raw inputs, configs, training code, model artifacts, OOF predictions, logs, and submissions separated. |
| Categorical and tabular features | Use encodings, missing-value policy, feature selection, and tuning with fold boundaries. |
| Image and text workflows | Validate labels, transforms, pretrained assets, inference shape, and modality-specific leakage. |
| Ensembling and stacking | Use only OOF-safe base predictions and record blend/stack evidence. |
| Reproducibility | Track seeds, code version, data version, run config, metrics, artifacts, and scoring receipts. |
| Kaggle execution | Offload heavy runs, manage producer/consumer notebooks, create private artifact datasets, and retrieve outputs. |

## Distillation Principles

- Convert general competitive ML practice into action rules for Kaggle work, not copied prose from any source.
- Prefer compact workflows, checklists, and reusable scripts over long explanations.
- Keep validation, metric choice, and OOF predictions as first-class artifacts.
- Prefer code-first, scriptable, fold-driven, and metric-aware execution.
- Modernize implementation choices when current Kaggle practice, competition rules, or platform mechanics require it.

## Platform Materials

- Kaggle competition rules, data pages, notebooks, datasets, and API documentation.
- Kaggle dataset publishing/versioning and dataset community usage.
- Kaggle CLI commands for dataset create/version/status, dataset metadata, kernel push/status/output, kernel metadata, competition submit, and submission-history retrieval.
- Kaggle notebook output practice: producer notebook outputs can be promoted to datasets and consumed by downstream notebooks as attached inputs.
- Kaggle code-competition practice: producer notebooks train models or generate heavy artifacts, export them as private Kaggle datasets, and the final consumer notebook loads those artifacts for hidden-test-safe scoring.
- Kaggle code-competition debugging guidance for limited hidden-run error detail and robust retry loops.
- Python package support for Kaggle datasets, models, competition files, notebook outputs, and dataset/model uploads.
- Optional public notebook and discussion intelligence tools for live competition reconnaissance.
- Advanced architecture guidance for staged Kaggle notebook pipelines, producer/consumer artifact datasets, and OOF-gated ensemble escalation.
