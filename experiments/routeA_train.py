#!/usr/bin/env python3
"""Fit and cross-fit the preregistered 32-feature Route-A response model."""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time
from collections import Counter
from typing import Any

import numpy as np
from sklearn.linear_model import LogisticRegression


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiments.routeA_policy import (  # noqa: E402
    DECISION_THRESHOLDS,
    FEATURE_NAMES,
    LinearResponseModel,
)
from scripts.candidate_h2h import BASELINE as V22, assert_locked_baseline, sha256, tree_sha256  # noqa: E402
from scripts.safe_json_output import reserve_json_output  # noqa: E402


LEG_ORDER = ("v22", "router", "alakazam", "lucario")
# sklearn constrains random_state to uint32; keep the full protocol timestamp
# elsewhere and use its stable uint32 reduction for model/control generation.
RANDOM_SEED = 202608151328 % (2**32)


def _design(features: np.ndarray, treatment: np.ndarray) -> np.ndarray:
    treatment_column = treatment.reshape(-1, 1).astype(float)
    return np.concatenate(
        [features, treatment_column, features * treatment_column], axis=1
    )


def _fit(rows: list[dict[str, Any]]) -> LogisticRegression:
    decisive = [row for row in rows if float(row["outcome"]) in (0.0, 1.0)]
    if len(decisive) < 100 or len({float(row["outcome"]) for row in decisive}) < 2:
        raise SystemExit("Route-A training fold lacks decisive outcomes/classes")
    features = np.asarray([row["features"] for row in decisive], dtype=np.float64)
    treatment = np.asarray([row["treatment"] for row in decisive], dtype=np.int8)
    outcome = np.asarray([row["outcome"] for row in decisive], dtype=np.int8)
    model = LogisticRegression(
        l1_ratio=0.0,
        C=1.0,
        solver="lbfgs",
        max_iter=1000,
        tol=1e-7,
        random_state=RANDOM_SEED,
    )
    model.fit(_design(features, treatment), outcome)
    if model.coef_.shape != (1, 65):
        raise SystemExit(f"Route-A model shape mismatch: {model.coef_.shape}")
    return model


def _runtime_model(model: LogisticRegression, threshold: float) -> LinearResponseModel:
    return LinearResponseModel(
        intercept=float(model.intercept_[0]),
        coefficients=tuple(float(value) for value in model.coef_[0]),
        decision_threshold=float(threshold),
    )


def _advantages(model: LogisticRegression, rows: list[dict[str, Any]]) -> np.ndarray:
    features = np.asarray([row["features"] for row in rows], dtype=np.float64)
    zeros = np.zeros(len(rows), dtype=np.int8)
    ones = np.ones(len(rows), dtype=np.int8)
    p0 = model.predict_proba(_design(features, zeros))[:, 1]
    p1 = model.predict_proba(_design(features, ones))[:, 1]
    return p1 - p0


def _ips(rows: list[dict[str, Any]], policy_treatment: np.ndarray) -> dict[str, Any]:
    assigned = np.asarray([row["treatment"] for row in rows], dtype=np.int8)
    outcome = np.asarray([row["outcome"] for row in rows], dtype=np.float64)
    policy_treatment = np.asarray(policy_treatment, dtype=np.int8)
    if len(policy_treatment) != len(rows):
        raise ValueError("Route-A IPS policy length mismatch")
    policy_value = float(np.mean(2.0 * outcome * (assigned == policy_treatment)))
    exact_value = float(np.mean(2.0 * outcome * (assigned == 0)))
    return {
        "episodes": len(rows),
        "policy_value": round(policy_value, 6),
        "exact_value": round(exact_value, 6),
        "uplift": round(policy_value - exact_value, 6),
        "intervention_rate": round(float(np.mean(policy_treatment)), 6),
        "assigned_treatment_rate": round(float(np.mean(assigned)), 6),
    }


def _choose_threshold(
    model: LogisticRegression,
    rows: list[dict[str, Any]],
) -> tuple[float, list[dict[str, Any]]]:
    advantages = _advantages(model, rows)
    assessments = []
    for threshold in DECISION_THRESHOLDS:
        assessment = _ips(rows, (advantages >= threshold).astype(np.int8))
        assessment["threshold"] = threshold
        assessments.append(assessment)
    # Higher threshold wins exact ties, making the deployed head more conservative.
    winner = max(assessments, key=lambda row: (row["uplift"], row["threshold"]))
    return float(winner["threshold"]), assessments


def _normalize_rows(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if payload.get("candidate_tree_sha256") != tree_sha256(V22):
        raise SystemExit("Route-A collection baseline tree mismatch")
    if payload.get("feature_names") != list(FEATURE_NAMES):
        raise SystemExit("Route-A collection feature contract mismatch")
    normalized = []
    for row in payload.get("rows") or []:
        if not row.get("eligible") or row.get("record") is None:
            continue
        if row.get("candidate_fault") or row.get("internal_errors"):
            raise SystemExit("Route-A formal data contains candidate/internal fault")
        record = row["record"]
        features = [float(value) for value in record["features"]]
        if len(features) != len(FEATURE_NAMES):
            raise SystemExit("Route-A formal row feature width mismatch")
        normalized.append({
            "leg": str(row["leg"]),
            "game_index": int(row["game_index"]),
            "bucket": str(record["bucket"]),
            "treatment": int(record["treatment"]),
            "outcome": float(row["outcome"]),
            "features": features,
        })
    # Fixed outcome-blind 10% calibration split.  The offset by leg prevents
    # the identical per-leg game indices from selecting exactly the same rows.
    leg_offset = {leg: index for index, leg in enumerate(LEG_ORDER)}
    def is_calibration(row: dict[str, Any]) -> bool:
        return (row["game_index"] + leg_offset[row["leg"]]) % 10 == 0

    calibration = [row for row in normalized if is_calibration(row)]
    learning = [row for row in normalized if not is_calibration(row)]
    return learning, calibration


def _model_payload(model: LinearResponseModel) -> dict[str, Any]:
    return {
        "intercept": model.intercept,
        "coefficients": list(model.coefficients),
        "decision_threshold": model.decision_threshold,
        "feature_names": list(FEATURE_NAMES),
        "architecture": "base32+Z+Zx32 logistic response; L2 C=1.0",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--overwrite-output", action="store_true")
    args = parser.parse_args()

    assert_locked_baseline()
    reservation = reserve_json_output(args.out, overwrite=args.overwrite_output)
    source_path = pathlib.Path(args.data).resolve()
    source = json.loads(source_path.read_text(encoding="utf-8"))
    learning, calibration = _normalize_rows(source)
    if set(row["leg"] for row in learning) != set(LEG_ORDER):
        raise SystemExit("Route-A formal data missing an opponent leg")
    started = time.time()

    folds = []
    crossfit_rows: list[dict[str, Any]] = []
    crossfit_policy: list[int] = []
    for heldout in LEG_ORDER:
        train_rows = [row for row in learning if row["leg"] != heldout]
        test_rows = [row for row in learning if row["leg"] == heldout]
        model = _fit(train_rows)
        threshold, train_thresholds = _choose_threshold(model, train_rows)
        advantages = _advantages(model, test_rows)
        policy = (advantages >= threshold).astype(np.int8)
        heldout_ips = _ips(test_rows, policy)
        folds.append({
            "heldout_leg": heldout,
            "train_episodes": len(train_rows),
            "heldout_episodes": len(test_rows),
            "selected_threshold": threshold,
            "training_threshold_assessments": train_thresholds,
            "heldout_ips": heldout_ips,
        })
        crossfit_rows.extend(test_rows)
        crossfit_policy.extend(int(value) for value in policy)

    overall = _ips(crossfit_rows, np.asarray(crossfit_policy, dtype=np.int8))
    positive_folds = sum(fold["heldout_ips"]["uplift"] > 0 for fold in folds)
    worst_fold = min(fold["heldout_ips"]["uplift"] for fold in folds)
    crossfit_pass = bool(
        overall["uplift"] >= 0.03
        and positive_folds >= 3
        and worst_fold >= -0.05
    )

    final_sklearn = _fit(learning)
    final_threshold, final_thresholds = _choose_threshold(final_sklearn, learning)
    final_model = _runtime_model(final_sklearn, final_threshold)

    calibration_features = np.asarray(
        [row["features"] for row in calibration], dtype=np.float64
    )
    trained_advantages = np.asarray([
        final_model.advantage(tuple(float(value) for value in features))
        for features in calibration_features
    ])
    trained_rate = float(np.mean(trained_advantages >= final_threshold))

    rng = np.random.default_rng(RANDOM_SEED)
    trained_scale = max(0.01, float(np.std(final_sklearn.coef_[0])))
    random_coefficients = rng.normal(0.0, trained_scale, size=65)
    random_intercept = float(rng.normal(0.0, trained_scale))
    provisional_random = LinearResponseModel(
        intercept=random_intercept,
        coefficients=tuple(float(value) for value in random_coefficients),
        decision_threshold=0.0,
    )
    random_advantages = np.asarray([
        provisional_random.advantage(tuple(float(value) for value in features))
        for features in calibration_features
    ])
    if trained_rate <= 0.0:
        random_threshold = float(np.max(random_advantages) + 1e-12)
    elif trained_rate >= 1.0:
        random_threshold = float(np.min(random_advantages) - 1e-12)
    else:
        random_threshold = float(np.quantile(random_advantages, 1.0 - trained_rate))
    random_model = LinearResponseModel(
        intercept=random_intercept,
        coefficients=tuple(float(value) for value in random_coefficients),
        decision_threshold=random_threshold,
    )
    random_rate = float(np.mean(random_advantages >= random_threshold))
    rate_delta = abs(trained_rate - random_rate)

    report = {
        "created_unix": time.time(),
        "method": "routeA-crossfit-logistic-advantage-v1",
        "source_data": str(source_path),
        "source_data_sha256": sha256(source_path),
        "candidate_tree_sha256": tree_sha256(V22),
        "feature_names": list(FEATURE_NAMES),
        "eligible_episodes": len(learning) + len(calibration),
        "learning_episodes": len(learning),
        "calibration_episodes": len(calibration),
        "learning_legs": dict(Counter(row["leg"] for row in learning)),
        "learning_buckets": dict(Counter(row["bucket"] for row in learning)),
        "learning_treatment": dict(Counter(str(row["treatment"]) for row in learning)),
        "draws_retained_for_ips_but_excluded_from_logistic": sum(
            row["outcome"] == 0.5 for row in learning
        ),
        "folds": folds,
        "crossfit": {
            **overall,
            "positive_folds": positive_folds,
            "worst_fold_uplift": round(worst_fold, 6),
            "rules": {
                "overall_uplift_min": 0.03,
                "positive_folds_min": 3,
                "worst_fold_min": -0.05,
            },
            "passed": crossfit_pass,
        },
        "final_training_threshold_assessments": final_thresholds,
        "trained_model": _model_payload(final_model),
        "random_control_model": _model_payload(random_model),
        "random_control_rate_match": {
            "trained_calibration_rate": round(trained_rate, 6),
            "random_calibration_rate": round(random_rate, 6),
            "absolute_delta": round(rate_delta, 6),
            "max_delta": 0.02,
            "passed": rate_delta <= 0.02,
        },
        "verdict": (
            "PASS_TO_LIVE_CANARY"
            if crossfit_pass and rate_delta <= 0.02
            else "TRAINING_KILL"
        ),
        "elapsed_s": round(time.time() - started, 6),
    }
    reservation.write(report)
    print(
        f"Route-A train verdict={report['verdict']} "
        f"crossfit_uplift={overall['uplift']:+.4f} "
        f"positive_folds={positive_folds}/4 worst={worst_fold:+.4f} "
        f"trained_rate={trained_rate:.3f} random_rate={random_rate:.3f}",
        flush=True,
    )
    for fold in folds:
        print(
            f"  heldout={fold['heldout_leg']:<9} "
            f"uplift={fold['heldout_ips']['uplift']:+.4f} "
            f"rate={fold['heldout_ips']['intervention_rate']:.3f} "
            f"threshold={fold['selected_threshold']:.3f}",
            flush=True,
        )
    return 0 if report["verdict"] == "PASS_TO_LIVE_CANARY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
