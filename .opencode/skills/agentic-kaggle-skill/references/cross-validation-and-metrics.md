# Cross-Validation And Metrics

## Fold Design Checklist

Choose validation before modeling:

- Identify what one test row represents and how Kaggle likely sampled the hidden set.
- Check duplicate IDs, near-duplicate text/images, repeated users, patients, stores, products, locations, sessions, and timestamps.
- Decide whether labels need stratification, groups need isolation, or time needs ordering.
- Add a persistent `fold` column to the train table and use it in every script.
- Report mean, standard deviation, and per-fold scores.
- Keep OOF predictions for diagnostics, thresholding, blending, and stacking.

## Split Selection

Use `StratifiedKFold` for ordinary classification. For imbalanced targets, keep class ratios stable and inspect minority-class counts per fold.

Use `KFold` for ordinary regression. If the target is skewed or multimodal, bin the target and stratify on bins. A good default bin count is Sturges' rule: `1 + log2(n_rows)`.

Use `GroupKFold` when the same entity can appear multiple times. Common groups are user, patient, product, session, document, author, household, image source, prompt, location, and time block.

Use a stratified group split when both label balance and group isolation matter. If the installed scikit-learn has `StratifiedGroupKFold`, use it; otherwise decide whether group isolation or label balance is the higher risk and document the tradeoff.

Use time-aware validation when chronological leakage is possible. Sort by time and create holdouts that mimic the public/private periods.

## Leakage Checks

- Feature values computed using all rows before splitting can leak validation information. Fit transforms inside each fold.
- Target encoding must be out-of-fold.
- Scaling, imputation, SVD/PCA, vectorizers, oversampling, feature selection, and threshold search must be trained only on training-fold data when they learn from data.
- Augment images only after splitting; never let augmented variants cross folds.
- Near-duplicate rows should stay in the same fold or be removed.
- If CV and public LB disagree, audit split choice, metric implementation, submission format, and train/test drift before chasing the leaderboard.

## Metric Selection

Use the competition metric exactly. Common mappings:

- Binary classification: log loss, ROC AUC, PR AUC, F1, MCC, accuracy, or balanced accuracy.
- Multiclass: multiclass log loss, macro/micro F1, accuracy, Cohen's kappa.
- Multilabel: per-class log loss, mean F1, label-ranking average precision, mAP.
- Regression: RMSE, RMSLE, MAE, MAPE, R2, correlation, quantile loss.
- Ranking/recommendation: MAP@K, NDCG@K, hit rate, recall@K.
- Segmentation: Dice, IoU/Jaccard, pixel accuracy, boundary-aware metrics.

When the metric has thresholds, tune thresholds on OOF predictions only. For F1/MCC/kappa, thresholding can matter as much as model choice.

For log-loss style metrics, calibrate probabilities, avoid overconfident clipping mistakes, and validate the exact label order in the submission.

For RMSLE, train or evaluate in log space only if it matches the metric and the target is nonnegative. Clip negative predictions before scoring when required.
