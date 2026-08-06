#!/usr/bin/env python3
"""Add a reproducible fold column to a training CSV."""

from __future__ import annotations

import argparse
import math
from pathlib import Path
from typing import Iterable

np = None
pd = None
GroupKFold = KFold = StratifiedKFold = TimeSeriesSplit = None
StratifiedGroupKFold = None
HAVE_SKLEARN = False


def _load_dependencies() -> None:
    global np, pd, GroupKFold, KFold, StratifiedKFold, TimeSeriesSplit
    global StratifiedGroupKFold, HAVE_SKLEARN

    try:
        import numpy as np_module
        import pandas as pd_module
    except ImportError as exc:  # pragma: no cover - exercised in minimal environments
        raise SystemExit(
            "make_folds.py requires pandas and numpy. Install them with: "
            "python3 -m pip install pandas numpy scikit-learn"
        ) from exc

    np = np_module
    pd = pd_module

    try:
        from sklearn.model_selection import GroupKFold as GroupKFoldCls
        from sklearn.model_selection import KFold as KFoldCls
        from sklearn.model_selection import StratifiedKFold as StratifiedKFoldCls
        from sklearn.model_selection import TimeSeriesSplit as TimeSeriesSplitCls

        try:
            from sklearn.model_selection import StratifiedGroupKFold as StratifiedGroupKFoldCls
        except ImportError:  # pragma: no cover - depends on sklearn version
            StratifiedGroupKFoldCls = None

        GroupKFold = GroupKFoldCls
        KFold = KFoldCls
        StratifiedKFold = StratifiedKFoldCls
        TimeSeriesSplit = TimeSeriesSplitCls
        StratifiedGroupKFold = StratifiedGroupKFoldCls
        HAVE_SKLEARN = True
    except ImportError:  # pragma: no cover - exercised in minimal environments
        HAVE_SKLEARN = False


def _target_is_classification(y: pd.Series) -> bool:
    if y.dtype == object or str(y.dtype).startswith(("category", "bool")):
        return True
    unique = y.nunique(dropna=False)
    return unique <= min(50, max(10, int(0.05 * len(y))))


def _sturges_bins(y: pd.Series) -> pd.Series:
    n_bins = max(2, int(1 + math.log2(max(len(y), 2))))
    ranked = y.rank(method="first")
    return pd.qcut(ranked, q=min(n_bins, len(y)), labels=False, duplicates="drop")


def _splitter(strategy: str, n_splits: int, seed: int):
    if not HAVE_SKLEARN:
        return None
    if strategy in {"kfold", "auto-regression"}:
        return KFold(n_splits=n_splits, shuffle=True, random_state=seed)
    if strategy in {"stratified", "auto-classification"}:
        return StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=seed)
    if strategy == "group":
        return GroupKFold(n_splits=n_splits)
    if strategy == "stratified-group":
        if StratifiedGroupKFold is None:
            raise RuntimeError(
                "StratifiedGroupKFold is unavailable in this scikit-learn version. "
                "Use --strategy group or install a newer scikit-learn."
            )
        return StratifiedGroupKFold(n_splits=n_splits, shuffle=True, random_state=seed)
    if strategy == "time":
        return TimeSeriesSplit(n_splits=n_splits)
    raise ValueError(f"Unknown strategy: {strategy}")


def _fallback_kfold(n_rows: int, n_splits: int, seed: int):
    rng = np.random.default_rng(seed)
    indices = np.arange(n_rows)
    rng.shuffle(indices)
    for valid_idx in np.array_split(indices, n_splits):
        train_idx = np.setdiff1d(np.arange(n_rows), valid_idx, assume_unique=False)
        yield train_idx, valid_idx


def _fallback_stratified(y: pd.Series, n_splits: int, seed: int):
    rng = np.random.default_rng(seed)
    fold_bins: list[list[int]] = [[] for _ in range(n_splits)]
    labels = pd.Series(y).fillna("__missing__").astype(str).to_numpy()
    for label in np.unique(labels):
        label_idx = np.where(labels == label)[0]
        rng.shuffle(label_idx)
        for fold, chunk in enumerate(np.array_split(label_idx, n_splits)):
            fold_bins[fold].extend(chunk.tolist())
    all_idx = np.arange(len(labels))
    for valid in fold_bins:
        valid_idx = np.array(sorted(valid), dtype=int)
        train_idx = np.setdiff1d(all_idx, valid_idx, assume_unique=False)
        yield train_idx, valid_idx


def _fallback_group(groups: pd.Series, n_splits: int, seed: int):
    rng = np.random.default_rng(seed)
    group_values = pd.Series(groups).fillna("__missing_group__").astype(str).to_numpy()
    unique_groups, inverse = np.unique(group_values, return_inverse=True)
    group_counts = np.bincount(inverse)
    order = np.arange(len(unique_groups))
    rng.shuffle(order)
    order = sorted(order, key=lambda g: group_counts[g], reverse=True)

    fold_groups: list[list[int]] = [[] for _ in range(n_splits)]
    fold_sizes = np.zeros(n_splits, dtype=int)
    for group_id in order:
        fold = int(np.argmin(fold_sizes))
        fold_groups[fold].append(group_id)
        fold_sizes[fold] += group_counts[group_id]

    all_idx = np.arange(len(group_values))
    for groups_in_fold in fold_groups:
        valid_mask = np.isin(inverse, groups_in_fold)
        valid_idx = np.where(valid_mask)[0]
        train_idx = np.setdiff1d(all_idx, valid_idx, assume_unique=False)
        yield train_idx, valid_idx


def _fallback_stratified_group(y: pd.Series, groups: pd.Series, n_splits: int, seed: int):
    rng = np.random.default_rng(seed)
    labels = pd.Series(y).fillna("__missing__").astype(str).to_numpy()
    group_values = pd.Series(groups).fillna("__missing_group__").astype(str).to_numpy()
    unique_groups, group_inverse = np.unique(group_values, return_inverse=True)
    unique_labels, label_inverse = np.unique(labels, return_inverse=True)

    group_label_counts = np.zeros((len(unique_groups), len(unique_labels)), dtype=float)
    for group_id, label_id in zip(group_inverse, label_inverse):
        group_label_counts[group_id, label_id] += 1.0

    order = np.arange(len(unique_groups))
    rng.shuffle(order)
    order = sorted(
        order,
        key=lambda g: (group_label_counts[g].max(), group_label_counts[g].sum()),
        reverse=True,
    )

    fold_groups: list[list[int]] = [[] for _ in range(n_splits)]
    fold_counts = np.zeros((n_splits, len(unique_labels)), dtype=float)
    fold_sizes = np.zeros(n_splits, dtype=float)
    for group_id in order:
        best_fold = 0
        best_score = None
        for fold in range(n_splits):
            candidate_counts = fold_counts.copy()
            candidate_sizes = fold_sizes.copy()
            candidate_counts[fold] += group_label_counts[group_id]
            candidate_sizes[fold] += group_label_counts[group_id].sum()
            label_balance = np.std(candidate_counts, axis=0).mean()
            size_balance = np.std(candidate_sizes / max(candidate_sizes.sum(), 1.0))
            score = label_balance + 0.1 * size_balance
            if best_score is None or score < best_score:
                best_score = score
                best_fold = fold
        fold_groups[best_fold].append(group_id)
        fold_counts[best_fold] += group_label_counts[group_id]
        fold_sizes[best_fold] += group_label_counts[group_id].sum()

    all_idx = np.arange(len(group_values))
    for groups_in_fold in fold_groups:
        valid_mask = np.isin(group_inverse, groups_in_fold)
        valid_idx = np.where(valid_mask)[0]
        train_idx = np.setdiff1d(all_idx, valid_idx, assume_unique=False)
        yield train_idx, valid_idx


def _fallback_time(n_rows: int, n_splits: int):
    test_size = max(1, n_rows // (n_splits + 1))
    remainder = n_rows - test_size * (n_splits + 1)
    for fold in range(n_splits):
        train_end = remainder + test_size * (fold + 1)
        valid_start = train_end
        valid_end = valid_start + test_size
        if fold == n_splits - 1:
            valid_end = n_rows
        valid_idx = np.arange(valid_start, min(valid_end, n_rows))
        train_idx = np.arange(0, valid_start)
        yield train_idx, valid_idx


def _fallback_splits(
    work: pd.DataFrame,
    y_for_split: pd.Series,
    strategy: str,
    n_splits: int,
    seed: int,
    group_col: str | None,
):
    if strategy in {"kfold", "auto-regression"}:
        yield from _fallback_kfold(len(work), n_splits, seed)
    elif strategy in {"stratified", "auto-classification"}:
        yield from _fallback_stratified(y_for_split.loc[work.index], n_splits, seed)
    elif strategy == "group":
        if not group_col:
            raise ValueError("--group-col is required for --strategy group")
        yield from _fallback_group(work[group_col], n_splits, seed)
    elif strategy == "stratified-group":
        if not group_col:
            raise ValueError("--group-col is required for --strategy stratified-group")
        yield from _fallback_stratified_group(
            y_for_split.loc[work.index],
            work[group_col],
            n_splits,
            seed,
        )
    elif strategy == "time":
        yield from _fallback_time(len(work), n_splits)
    else:
        raise ValueError(f"Unknown strategy: {strategy}")


def _iter_splits(
    df: pd.DataFrame,
    y_for_split: pd.Series,
    strategy: str,
    n_splits: int,
    seed: int,
    group_col: str | None,
    time_col: str | None,
) -> Iterable[tuple[np.ndarray, np.ndarray]]:
    work = df
    if strategy == "time":
        if not time_col:
            raise ValueError("--time-col is required for --strategy time")
        work = df.sort_values(time_col).reset_index()

    splitter = _splitter(strategy, n_splits, seed)

    if HAVE_SKLEARN:
        if strategy == "group":
            if not group_col:
                raise ValueError("--group-col is required for --strategy group")
            splits = splitter.split(work, groups=work[group_col])
        elif strategy == "stratified-group":
            if not group_col:
                raise ValueError("--group-col is required for --strategy stratified-group")
            splits = splitter.split(work, y_for_split.loc[work.index], groups=work[group_col])
        elif strategy in {"stratified", "auto-classification"}:
            splits = splitter.split(work, y_for_split.loc[work.index])
        else:
            splits = splitter.split(work)
    else:
        splits = _fallback_splits(
            work=work,
            y_for_split=y_for_split,
            strategy=strategy,
            n_splits=n_splits,
            seed=seed,
            group_col=group_col,
        )

    for train_idx, valid_idx in splits:
        if strategy == "time":
            original_valid_idx = work.loc[valid_idx, "index"].to_numpy()
            yield train_idx, original_valid_idx
        else:
            yield train_idx, valid_idx


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Input training CSV")
    parser.add_argument("--output", required=True, help="Output CSV with fold column")
    parser.add_argument("--target", required=True, help="Target column")
    parser.add_argument("--fold-col", default="fold", help="Name of output fold column")
    parser.add_argument("--strategy", default="auto", choices=[
        "auto",
        "kfold",
        "stratified",
        "group",
        "stratified-group",
        "time",
    ])
    parser.add_argument("--group-col", default=None, help="Group column for grouped splits")
    parser.add_argument("--time-col", default=None, help="Time column for ordered splits")
    parser.add_argument("--n-splits", type=int, default=5)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--regression-bins",
        action="store_true",
        help="Use binned target stratification for regression targets",
    )
    args = parser.parse_args()

    _load_dependencies()

    input_path = Path(args.input).expanduser()
    output_path = Path(args.output).expanduser()
    df = pd.read_csv(input_path)

    if args.target not in df.columns:
        raise ValueError(f"Target column not found: {args.target}")
    if args.group_col and args.group_col not in df.columns:
        raise ValueError(f"Group column not found: {args.group_col}")
    if args.time_col and args.time_col not in df.columns:
        raise ValueError(f"Time column not found: {args.time_col}")

    strategy = args.strategy
    target = df[args.target]
    if strategy == "auto":
        if args.group_col:
            strategy = "stratified-group" if _target_is_classification(target) else "group"
        elif args.time_col:
            strategy = "time"
        elif _target_is_classification(target):
            strategy = "auto-classification"
        else:
            strategy = "stratified" if args.regression_bins else "auto-regression"

    if strategy in {"stratified", "stratified-group"} and not _target_is_classification(target):
        y_for_split = _sturges_bins(target)
    elif strategy == "auto-classification":
        y_for_split = target
    elif args.regression_bins and strategy in {"auto-regression", "kfold"}:
        strategy = "stratified"
        y_for_split = _sturges_bins(target)
    else:
        y_for_split = target

    df[args.fold_col] = -1
    for fold, (_, valid_idx) in enumerate(
        _iter_splits(
            df=df,
            y_for_split=y_for_split,
            strategy=strategy,
            n_splits=args.n_splits,
            seed=args.seed,
            group_col=args.group_col,
            time_col=args.time_col,
        )
    ):
        df.loc[valid_idx, args.fold_col] = fold

    if (df[args.fold_col] < 0).any() and strategy != "time":
        missing = int((df[args.fold_col] < 0).sum())
        raise RuntimeError(f"{missing} rows were not assigned to a fold")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
    counts = df[args.fold_col].value_counts().sort_index().to_dict()
    print(f"Wrote {output_path} using strategy={strategy}, fold_counts={counts}")


if __name__ == "__main__":
    main()
