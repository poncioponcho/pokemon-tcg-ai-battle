#!/usr/bin/env python3
"""Post-hoc, read-only decomposition of the positive Route-A Router fold."""

from __future__ import annotations

import argparse
import json
import math
import pathlib
import sys
import time
from collections import defaultdict
from typing import Any, Callable

import numpy as np


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiments import routeA_train as train  # noqa: E402
from experiments.routeA_policy import FEATURE_NAMES  # noqa: E402
from scripts.candidate_h2h import sha256  # noqa: E402
from scripts.safe_json_output import reserve_json_output  # noqa: E402


EXPECTED_DATA_SHA = "ea7be6e7a948c211f132f4b6b79fee61c3b49743acc50861a60b026f380ce241"
EXPECTED_TRAIN_SHA = "ae140f957cc5484d3fa417e1627e1e60d95b27053f2e9c029c54a71724feae65"
ACTION_NAMES = {7: "play", 8: "attach", 9: "evolve", 10: "ability"}


def _mean_ci(values: np.ndarray) -> dict[str, Any]:
    values = np.asarray(values, dtype=np.float64)
    if not len(values):
        return {"n": 0, "mean": None, "se": None, "ci95": None}
    mean = float(np.mean(values))
    se = float(np.std(values, ddof=1) / math.sqrt(len(values))) if len(values) > 1 else 0.0
    return {
        "n": int(len(values)),
        "mean": round(mean, 6),
        "se": round(se, 6),
        "ci95": [round(mean - 1.96 * se, 6), round(mean + 1.96 * se, 6)],
    }


def _assessment(rows: list[dict[str, Any]], total: int) -> dict[str, Any]:
    assigned = np.asarray([row["treatment"] for row in rows], dtype=np.int8)
    outcome = np.asarray([row["outcome"] for row in rows], dtype=np.float64)
    policy = np.asarray([row["policy"] for row in rows], dtype=np.int8)
    z0 = outcome[assigned == 0]
    z1 = outcome[assigned == 1]
    raw_estimable = len(z0) >= 2 and len(z1) >= 2
    raw_delta = float(np.mean(z1) - np.mean(z0)) if raw_estimable else None
    raw_se = (
        math.sqrt(float(np.var(z1, ddof=1) / len(z1) + np.var(z0, ddof=1) / len(z0)))
        if raw_estimable else None
    )
    influence = 2.0 * outcome * (
        (assigned == policy).astype(np.float64) - (assigned == 0).astype(np.float64)
    )
    ips = _mean_ci(influence)
    return {
        "episodes": len(rows),
        "share_of_router": round(len(rows) / total, 6),
        "z0": len(z0),
        "z1": len(z1),
        "z1_rate": round(float(np.mean(assigned)), 6),
        "outcome_z0": round(float(np.mean(z0)), 6) if len(z0) else None,
        "outcome_z1": round(float(np.mean(z1)), 6) if len(z1) else None,
        "raw_randomized_delta": round(raw_delta, 6) if raw_delta is not None else None,
        "raw_randomized_delta_ci95": (
            [round(raw_delta - 1.96 * raw_se, 6), round(raw_delta + 1.96 * raw_se, 6)]
            if raw_delta is not None and raw_se is not None else None
        ),
        "policy_intervention_rate": round(float(np.mean(policy)), 6),
        "policy_ips_uplift": ips["mean"],
        "policy_ips_uplift_ci95": ips["ci95"],
        "contribution_to_overall_uplift": round(float(ips["mean"]) * len(rows) / total, 6),
    }


def _partition(
    rows: list[dict[str, Any]],
    key: Callable[[dict[str, Any]], str],
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[key(row)].append(row)
    output = []
    for label, group in grouped.items():
        output.append({"label": label, **_assessment(group, len(rows))})
    output.sort(key=lambda item: (-abs(float(item["contribution_to_overall_uplift"])), item["label"]))
    return output


def _score_gap_bucket(row: dict[str, Any]) -> str:
    gap = float(row["score_gap"])
    if abs(gap) <= 1e-12:
        return "gap=0"
    if gap <= 5.0:
        return "0<gap<=5"
    if gap <= 15.0:
        return "5<gap<=15"
    return "15<gap<=25"


def _raw_all_eligible(source: dict[str, Any], leg: str) -> dict[str, Any]:
    rows = [row for row in source["rows"] if row["leg"] == leg and row["eligible"]]
    assigned = np.asarray([row["record"]["treatment"] for row in rows], dtype=np.int8)
    outcome = np.asarray([row["outcome"] for row in rows], dtype=np.float64)
    z0 = outcome[assigned == 0]
    z1 = outcome[assigned == 1]
    delta = float(np.mean(z1) - np.mean(z0))
    se = math.sqrt(float(np.var(z1, ddof=1) / len(z1) + np.var(z0, ddof=1) / len(z0)))
    return {
        "episodes": len(rows),
        "z0": len(z0),
        "z1": len(z1),
        "outcome_z0": round(float(np.mean(z0)), 6),
        "outcome_z1": round(float(np.mean(z1)), 6),
        "delta": round(delta, 6),
        "delta_ci95": [round(delta - 1.96 * se, 6), round(delta + 1.96 * se, 6)],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True)
    parser.add_argument("--training-report", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    data_path = pathlib.Path(args.data).resolve()
    training_path = pathlib.Path(args.training_report).resolve()
    if sha256(data_path) != EXPECTED_DATA_SHA:
        raise SystemExit("Router slice input data SHA mismatch")
    if sha256(training_path) != EXPECTED_TRAIN_SHA:
        raise SystemExit("Router slice training report SHA mismatch")
    reservation = reserve_json_output(args.out)
    source = json.loads(data_path.read_text(encoding="utf-8"))
    training_report = json.loads(training_path.read_text(encoding="utf-8"))
    learning, _calibration = train._normalize_rows(source)
    train_rows = [row for row in learning if row["leg"] != "router"]
    router_rows = [dict(row) for row in learning if row["leg"] == "router"]
    model = train._fit(train_rows)
    threshold, threshold_assessments = train._choose_threshold(model, train_rows)
    advantages = train._advantages(model, router_rows)
    policy = (advantages >= threshold).astype(np.int8)
    reproduced = train._ips(router_rows, policy)
    expected_fold = next(
        fold for fold in training_report["folds"] if fold["heldout_leg"] == "router"
    )
    if threshold != float(expected_fold["selected_threshold"]):
        raise SystemExit("Router fold selected threshold reproduction failed")
    for key in ("policy_value", "exact_value", "uplift", "intervention_rate"):
        if abs(float(reproduced[key]) - float(expected_fold["heldout_ips"][key])) > 1e-6:
            raise SystemExit(f"Router fold reproduction failed for {key}")

    metadata = {
        (str(row["leg"]), int(row["game_index"])): row
        for row in source["rows"] if row.get("eligible") and row.get("record") is not None
    }
    enriched = []
    for row, advantage, decision in zip(router_rows, advantages, policy):
        meta = metadata[(row["leg"], row["game_index"])]
        record = meta["record"]
        exact_type = int(record["exact_semantic"][0])
        alternative_type = int(record["alternative_semantic"][0])
        enriched.append({
            **row,
            "advantage": float(advantage),
            "policy": int(decision),
            "exact_type": exact_type,
            "alternative_type": alternative_type,
            "exact_action_name": ACTION_NAMES.get(exact_type, f"type-{exact_type}"),
            "alternative_action_name": ACTION_NAMES.get(alternative_type, f"type-{alternative_type}"),
            "score_gap": float(record["score_gap"]),
        })

    feature_matrix = np.asarray([row["features"] for row in train_rows], dtype=np.float64)
    interaction_coefficients = np.asarray(model.coef_[0][33:], dtype=np.float64)
    feature_std = np.std(feature_matrix, axis=0, ddof=1)
    interactions = [
        {
            "feature": name,
            "z_interaction_coefficient": round(float(coefficient), 8),
            "training_feature_std": round(float(std), 8),
            "standardized_magnitude": round(float(coefficient * std), 8),
        }
        for name, coefficient, std in zip(FEATURE_NAMES, interaction_coefficients, feature_std)
    ]
    interactions.sort(key=lambda item: -abs(float(item["standardized_magnitude"])))

    report = {
        "created_unix": time.time(),
        "method": "routeA-router-heldout-posthoc-decomposition-v1",
        "scope": "hypothesis-generation-only; no pilot reopening or candidate promotion",
        "analysis_plan": str(ROOT / "reports" / "20260815_postfinal_exploration_plan.md"),
        "source_data": str(data_path),
        "source_data_sha256": sha256(data_path),
        "source_training_report": str(training_path),
        "source_training_report_sha256": sha256(training_path),
        "fold_reproduction": {
            "passed": True,
            "selected_threshold": threshold,
            "heldout_ips": reproduced,
            "training_threshold_assessments": threshold_assessments,
        },
        "formal_raw_all_eligible_router": _raw_all_eligible(source, "router"),
        "heldout_learning_overall": _assessment(enriched, len(enriched)),
        "partitions": {
            "turn_bucket": _partition(enriched, lambda row: row["bucket"]),
            "alternative_action_type": _partition(
                enriched, lambda row: row["alternative_action_name"]
            ),
            "exact_to_alternative": _partition(
                enriched,
                lambda row: f"{row['exact_action_name']}->{row['alternative_action_name']}",
            ),
            "score_gap": _partition(enriched, _score_gap_bucket),
        },
        "exact_to_alternative_summary_min_n_200": [
            row for row in _partition(
                enriched,
                lambda item: f"{item['exact_action_name']}->{item['alternative_action_name']}",
            ) if int(row["episodes"]) >= 200
        ],
        "top_standardized_z_interactions": interactions[:12],
        "all_z_interactions": interactions,
        "multiplicity_warning": (
            "All partitions and coefficient rankings are post-hoc and unadjusted; "
            "confidence intervals are descriptive, not promotion evidence."
        ),
        "winner": None,
        "submitted": False,
    }
    reservation.write(report)
    print(
        "Router slice audit complete "
        f"raw={report['formal_raw_all_eligible_router']['delta']:+.4f} "
        f"heldout_ips={reproduced['uplift']:+.4f} threshold={threshold:.3f}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
