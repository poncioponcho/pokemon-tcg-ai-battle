# Tabular Workflow

## Strong Baseline

1. Load train/test, mark target, ID, groups, time columns, categorical columns, numeric columns, and leaks to exclude.
2. Create folds and freeze them.
3. Implement the metric locally.
4. Train a tree boosting baseline with early stopping and OOF/test predictions.
5. Create one clean submission and verify row order and IDs.
6. Add features, encodings, and model variants only after the baseline is reproducible.

## Categorical Variables

Use the model family to choose encodings:

- Tree boosting: label encoding, ordinal/category dtype, count encoding, frequency encoding, rare-category grouping, CatBoost native categorical handling.
- Linear models: one-hot encoding, hashing trick, target/frequency features, sparse matrices.
- Neural nets: integer categories plus embeddings, especially for many high-cardinality fields.

Target encoding rules:

- Compute target statistics out-of-fold for train and from full train for test.
- Use smoothing to reduce noise in rare categories.
- Add noise or regularization when overfitting appears.
- Never let a row see its own target through an encoding.

Useful categorical features:

- Missingness flags and explicit unknown category.
- Category counts, frequencies, nunique by group, and cross-category combinations.
- Train/test category mismatch indicators.
- Aggregated target-free statistics by entity, time, location, or product.

## Numeric And Date Features

- Add missing indicators when missingness is informative.
- Try log, rank, clipping, binning, ratios, differences, interactions, and group-normalized features.
- Extract date parts: year, month, week, day, day of week, hour, holiday, season, elapsed time, recency, and period index.
- Build grouped aggregations: count, mean, median, min, max, std, sum, nunique, last, first, difference from group mean, and trend.
- For linear/SVM/neural models, scale numeric features. For tree models, scaling is usually unnecessary.

## Feature Selection

Do selection inside the validation loop when it learns from target or distribution.

Start by removing:

- Constant and near-constant features.
- Duplicate columns.
- Obvious ID leaks and post-outcome columns.
- Features with impossible train/test drift unless drift itself is the signal.

Then compare:

- Model importances across folds.
- Permutation importance on validation folds.
- Correlation pruning for linear models.
- Univariate selection only as a weak signal.
- Recursive elimination only when the feature count and runtime make it practical.

Keep a feature only when CV improves or it contributes useful diversity to an ensemble.

## Hyperparameter Tuning

Tune after validation and baseline code are stable.

Prioritize:

- Learning rate and number of estimators with early stopping.
- Tree depth, leaves, min child samples/weight.
- Row and column sampling.
- L1/L2 regularization.
- Class weights or scale-pos-weight for imbalanced classification.

Use random/Bayesian search over wide but sensible ranges before fine grids. Tune on fold averages, not a single lucky fold. Save every trial's params, seed, fold scores, and artifacts.

Avoid tuning noisy features and model params at the same time. If the CV signal is smaller than fold variance, simplify or gather more validation evidence.
