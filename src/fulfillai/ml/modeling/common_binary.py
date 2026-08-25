"""Shared leakage-safe binary-classification workflow for FulfillAI.

This module intentionally keeps TRAIN/VALIDATION experimentation separate from
one-time TEST evaluation. It is used by Phase 9 (delivery) and Phase 10
(inventory) wrappers.
"""

from __future__ import annotations

import hashlib
import json
import math
import subprocess
import time
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import ExtraTreesClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression

from ..config import METRIC_ROOT, MODEL_ROOT, ensure_artifact_directories, get_task_config
from ..data import LoadedSplit, load_metadata, load_split, predictor_columns
from ..metrics import (
    binary_classification_metrics,
    find_best_threshold,
)
from ..preprocessing import build_preprocessor, infer_feature_schema

RANDOM_STATE = 42
K_FRACTION = 0.01

# Row-level identifiers do not generalize and can let flexible models memorize.
IDENTIFIER_COLUMNS = {
    "shipment_external_id",
    "order_external_id",
    "shipment_id",
    "order_id",
    "customer_id",
}

# Raw temporal values are intentionally excluded from this generic modeling
# layer. Engineered calendar/duration features remain eligible.
RAW_TIME_COLUMNS = {
    "order_ts",
    "promised_delivery_ts",
    "shipped_at",
    "expected_delivery_at",
    "delivered_at",
    "ship_date",
}

# PostgreSQL NUMERIC/DECIMAL often lands as object dtype in pandas.
SEMANTIC_NUMERIC_COLUMNS = {
    "order_value",
    "avg_item_price",
    "max_item_price",
    "total_weight_kg",
    "shipping_cost",
    "processing_hours",
    "promised_total_hours",
    "expected_transit_hours",
    "processing_share_of_promise",
    "remaining_window_share_of_promise",
    "shipping_cost_pct_of_order",
    "shipping_cost_per_unit",
    "shipping_cost_per_kg",
    "units_sold",
    "on_hand_units",
    "reorder_point_units",
    "safety_stock_units",
    "lead_time_days",
}


class BinaryWorkflowError(RuntimeError):
    """Raised when a remaining-phase scientific integrity gate fails."""


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        value = float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(_json_safe(payload), handle, indent=2, sort_keys=True)
        handle.write("\n")


def read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return "UNKNOWN"


def require_clean_git() -> str:
    try:
        status = subprocess.check_output(
            ["git", "status", "--porcelain"],
            text=True,
            stderr=subprocess.STDOUT,
        )
    except Exception as exc:
        raise BinaryWorkflowError("Unable to verify Git working tree.") from exc
    if status.strip():
        raise BinaryWorkflowError(
            "Working tree is not clean. Commit/freeze source before one-time TEST evaluation."
        )
    return git_commit()


def _raw_rows(metadata: dict, split_name: str) -> int | None:
    try:
        return int(metadata["splits"][split_name]["rows"])
    except Exception:
        return None


def load_train_validation(task_name: str) -> dict:
    """Load only TRAIN and VALIDATION. TEST is not touched."""
    task = get_task_config(task_name)
    metadata = load_metadata(task)
    predictors = predictor_columns(task, metadata)
    train = load_split(task, "train", metadata=metadata, predictors=predictors)
    validation = load_split(task, "validation", metadata=metadata, predictors=predictors)
    return {
        "task": task,
        "metadata": metadata,
        "predictors": predictors,
        "train": train,
        "validation": validation,
    }


def load_test_only(task_name: str) -> dict:
    """Load only TEST for a frozen task. Call only after freeze gates pass."""
    task = get_task_config(task_name)
    metadata = load_metadata(task)
    predictors = predictor_columns(task, metadata)
    test = load_split(task, "test", metadata=metadata, predictors=predictors)
    return {
        "task": task,
        "metadata": metadata,
        "predictors": predictors,
        "test": test,
    }


def prepare_model_frame(split: LoadedSplit) -> tuple[pd.DataFrame, list[str]]:
    """Create deterministic model-ready raw predictors without outcome leakage."""
    frame = split.X.copy()
    dropped: list[str] = []

    for column in list(frame.columns):
        if column in IDENTIFIER_COLUMNS or column in RAW_TIME_COLUMNS:
            dropped.append(column)
            frame = frame.drop(columns=[column])
            continue
        if pd.api.types.is_datetime64_any_dtype(frame[column]):
            dropped.append(column)
            frame = frame.drop(columns=[column])

    for column in frame.columns:
        if column in SEMANTIC_NUMERIC_COLUMNS and not pd.api.types.is_numeric_dtype(frame[column]):
            frame[column] = pd.to_numeric(frame[column], errors="coerce")

    # Safe generic coercion for Decimal-like object columns. A categorical is
    # converted only when essentially all observed non-null values are numeric.
    for column in frame.select_dtypes(include=["object"]).columns:
        original = frame[column]
        converted = pd.to_numeric(original, errors="coerce")
        observed = int(original.notna().sum())
        numeric = int(converted.notna().sum())
        if observed and numeric / observed >= 0.995:
            frame[column] = converted

    if frame.empty:
        raise BinaryWorkflowError(f"{split.name}: no predictors remain after safe filtering.")

    return frame, sorted(dropped)


def candidate_models() -> dict[str, object]:
    """Compact, CPU-friendly model set. No huge grid search."""
    return {
        "dummy_prior": DummyClassifier(strategy="prior"),
        "logistic_balanced": LogisticRegression(
            solver="liblinear",
            class_weight="balanced",
            max_iter=1200,
            random_state=RANDOM_STATE,
        ),
        "random_forest": RandomForestClassifier(
            n_estimators=180,
            max_depth=14,
            min_samples_leaf=6,
            max_features="sqrt",
            class_weight="balanced_subsample",
            n_jobs=-1,
            random_state=RANDOM_STATE,
        ),
        "extra_trees": ExtraTreesClassifier(
            n_estimators=180,
            max_depth=None,
            min_samples_leaf=5,
            max_features="sqrt",
            class_weight="balanced",
            n_jobs=-1,
            random_state=RANDOM_STATE,
        ),
    }


def model_from_name(name: str):
    models = candidate_models()
    if name not in models:
        raise BinaryWorkflowError(f"Unknown frozen model name: {name}")
    return models[name]


def choose_threshold(y_true, probabilities, configured_metric: str | None) -> tuple[float, str, float]:
    """Choose a validation-only operating threshold.

    F1/F2 use the project's native threshold search. For a task configured as
    raw 'recall', maximizing recall alone would degenerate toward predicting
    nearly everything positive, so F2 is used as a recall-weighted proxy while
    PR-AUC and top-k metrics remain the model-selection criteria.
    """
    metric = (configured_metric or "f1").lower()
    if metric == "f1":
        threshold, score = find_best_threshold(y_true, probabilities, metric="f1")
        return float(threshold), "f1", float(score)
    if metric == "f2":
        threshold, score = find_best_threshold(y_true, probabilities, metric="f2")
        return float(threshold), "f2", float(score)
    if metric == "recall":
        threshold, score = find_best_threshold(y_true, probabilities, metric="f2")
        return float(threshold), "f2_proxy_for_recall", float(score)
    return 0.5, "fixed_0.50", float("nan")


def _fit_preprocessor(train_frame: pd.DataFrame):
    schema = infer_feature_schema(train_frame)
    preprocessor = build_preprocessor(schema)
    encoded = preprocessor.fit_transform(train_frame)
    return schema, preprocessor, encoded


def validate_task(task_name: str, *, phase: str, group: str) -> dict:
    """Run compact candidate comparison on TRAIN -> VALIDATION only."""
    bundle = load_train_validation(task_name)
    task = bundle["task"]
    train: LoadedSplit = bundle["train"]
    validation: LoadedSplit = bundle["validation"]

    X_train, dropped_train = prepare_model_frame(train)
    X_validation, dropped_validation = prepare_model_frame(validation)
    if tuple(X_train.columns) != tuple(X_validation.columns):
        raise BinaryWorkflowError(f"{task_name}: TRAIN/VALIDATION model columns differ.")
    if dropped_train != dropped_validation:
        raise BinaryWorkflowError(f"{task_name}: TRAIN/VALIDATION dropped columns differ.")

    y_train = pd.to_numeric(train.y, errors="raise").astype(int)
    y_validation = pd.to_numeric(validation.y, errors="raise").astype(int)
    if not set(y_train.unique()).issubset({0, 1}) or not set(y_validation.unique()).issubset({0, 1}):
        raise BinaryWorkflowError(f"{task_name}: target must be binary 0/1.")

    t0 = time.perf_counter()
    schema, preprocessor, X_train_encoded = _fit_preprocessor(X_train)
    X_validation_encoded = preprocessor.transform(X_validation)
    preprocessing_seconds = time.perf_counter() - t0

    results: dict[str, dict] = {}
    fitted_models: dict[str, object] = {}
    val_probabilities: dict[str, np.ndarray] = {}

    for model_name, model in candidate_models().items():
        start = time.perf_counter()
        model.fit(X_train_encoded, y_train)
        probabilities = np.asarray(model.predict_proba(X_validation_encoded)[:, 1], dtype=float)
        seconds = time.perf_counter() - start
        metrics = binary_classification_metrics(
            y_validation,
            probabilities,
            threshold=0.5,
            k_fraction=K_FRACTION,
        )
        results[model_name] = {"metrics_at_0_50": metrics, "seconds": seconds}
        fitted_models[model_name] = model
        val_probabilities[model_name] = probabilities

    ranking = sorted(
        results,
        key=lambda name: results[name]["metrics_at_0_50"]["pr_auc"],
        reverse=True,
    )
    winner = ranking[0]
    winner_prob = val_probabilities[winner]
    threshold, threshold_policy, threshold_score = choose_threshold(
        y_validation,
        winner_prob,
        task.threshold_metric,
    )
    winner_threshold_metrics = binary_classification_metrics(
        y_validation,
        winner_prob,
        threshold=threshold,
        k_fraction=K_FRACTION,
    )

    ensure_artifact_directories()
    metric_dir = METRIC_ROOT / group
    model_dir = MODEL_ROOT / group
    metric_dir.mkdir(parents=True, exist_ok=True)
    model_dir.mkdir(parents=True, exist_ok=True)

    selection_path = metric_dir / f"{task_name}_{phase.replace('.', '_')}_validation.json"
    candidate_path = model_dir / f"{task_name}_{phase.replace('.', '_')}_train_candidate.joblib"

    candidate_bundle = {
        "artifact_version": 1,
        "phase": phase,
        "task_name": task_name,
        "model_name": winner,
        "threshold": threshold,
        "threshold_policy": threshold_policy,
        "feature_columns": list(X_train.columns),
        "dropped_columns": dropped_train,
        "preprocessor": preprocessor,
        "model": fitted_models[winner],
        "fit_scope": "train_only",
        "test_used": False,
    }
    joblib.dump(candidate_bundle, candidate_path)

    payload = {
        "artifact_version": 1,
        "phase": phase,
        "group": group,
        "task_name": task_name,
        "task": {
            "target_column": task.target_column,
            "primary_metric": task.primary_metric,
            "threshold_metric": task.threshold_metric,
            "eligibility_column": getattr(task, "eligibility_column", None),
        },
        "population": {
            "train_raw_rows": _raw_rows(bundle["metadata"], "train"),
            "train_eligible_rows": train.rows,
            "train_positive_rows": int(y_train.sum()),
            "train_positive_rate": float(y_train.mean()),
            "validation_raw_rows": _raw_rows(bundle["metadata"], "validation"),
            "validation_eligible_rows": validation.rows,
            "validation_positive_rows": int(y_validation.sum()),
            "validation_positive_rate": float(y_validation.mean()),
        },
        "features": {
            "source_predictor_count": len(bundle["predictors"]),
            "model_predictor_count": int(X_train.shape[1]),
            "encoded_feature_count": int(X_train_encoded.shape[1]),
            "dropped_columns": dropped_train,
            "numeric_columns": list(schema.numeric_columns),
            "categorical_columns": list(schema.categorical_columns),
            "preprocessing_seconds": preprocessing_seconds,
        },
        "candidates": results,
        "ranking_by_pr_auc": ranking,
        "winner": winner,
        "validation_threshold": threshold,
        "threshold_policy": threshold_policy,
        "threshold_objective_score": threshold_score,
        "winner_metrics_at_frozen_threshold": winner_threshold_metrics,
        "candidate_model_artifact": str(candidate_path),
        "test_set_used": False,
    }
    write_json(selection_path, payload)
    payload["selection_artifact"] = str(selection_path)
    return payload


def print_validation_result(result: dict) -> None:
    print()
    print("=" * 104)
    print(f"{result['phase']} — {result['task_name'].upper()} VALIDATION")
    print("=" * 104)
    pop = result["population"]
    print(
        f"TRAIN raw={pop['train_raw_rows']} eligible={pop['train_eligible_rows']:,} "
        f"positive={pop['train_positive_rows']:,} ({pop['train_positive_rate']:.2%})"
    )
    print(
        f"VALID raw={pop['validation_raw_rows']} eligible={pop['validation_eligible_rows']:,} "
        f"positive={pop['validation_positive_rows']:,} ({pop['validation_positive_rate']:.2%})"
    )
    print()
    print(f"{'MODEL':<22} {'PR-AUC':>9} {'ROC-AUC':>9} {'F1@.50':>9} {'RECALL':>9} {'SECONDS':>9}")
    print("-" * 104)
    for name in result["ranking_by_pr_auc"]:
        row = result["candidates"][name]
        m = row["metrics_at_0_50"]
        print(
            f"{name:<22} {m['pr_auc']:>9.4f} {m['roc_auc']:>9.4f} "
            f"{m['f1']:>9.4f} {m['recall']:>9.4f} {row['seconds']:>9.2f}"
        )
    fm = result["winner_metrics_at_frozen_threshold"]
    print()
    print(f"winner                 : {result['winner']}")
    print(f"frozen threshold       : {result['validation_threshold']:.4f} ({result['threshold_policy']})")
    print(f"winner validation PR-AUC: {fm['pr_auc']:.6f}")
    print(f"winner validation F1    : {fm['f1']:.6f}")
    print("TEST LOADED             : NO 🔒")


def selection_path(group: str, task_name: str, phase: str) -> Path:
    return METRIC_ROOT / group / f"{task_name}_{phase.replace('.', '_')}_validation.json"


def final_model_path(group: str, task_name: str, phase: str) -> Path:
    return MODEL_ROOT / group / f"{task_name}_{phase.replace('.', '_')}_final.joblib"


def final_refit_task(task_name: str, *, validation_phase: str, final_phase: str, group: str) -> dict:
    """Freeze a validation-selected architecture and refit on TRAIN+VALIDATION.

    The source tree must already be clean so the persisted model can be tied to
    the exact committed implementation used for the final refit.
    """
    source_commit = require_clean_git()
    sel_path = selection_path(group, task_name, validation_phase)
    if not sel_path.exists():
        raise BinaryWorkflowError(f"Missing validation selection artifact: {sel_path}")
    selection = read_json(sel_path)
    model_name = selection["winner"]
    threshold = float(selection["validation_threshold"])

    bundle = load_train_validation(task_name)
    train: LoadedSplit = bundle["train"]
    validation: LoadedSplit = bundle["validation"]
    X_train, _ = prepare_model_frame(train)
    X_validation, _ = prepare_model_frame(validation)
    if list(X_train.columns) != list(X_validation.columns):
        raise BinaryWorkflowError(f"{task_name}: feature columns changed before final refit.")
    expected_columns = selection["features"]["model_predictor_count"]
    if X_train.shape[1] != expected_columns:
        raise BinaryWorkflowError(f"{task_name}: model predictor count changed since selection.")

    y_train = pd.to_numeric(train.y, errors="raise").astype(int)
    y_validation = pd.to_numeric(validation.y, errors="raise").astype(int)
    X_final = pd.concat([X_train, X_validation], axis=0, ignore_index=True)
    y_final = pd.concat([y_train, y_validation], axis=0, ignore_index=True)

    schema = infer_feature_schema(X_final)
    preprocessor = build_preprocessor(schema)
    X_final_encoded = preprocessor.fit_transform(X_final)
    model = model_from_name(model_name)
    start = time.perf_counter()
    model.fit(X_final_encoded, y_final)
    fit_seconds = time.perf_counter() - start

    ensure_artifact_directories()
    path = final_model_path(group, task_name, final_phase)
    path.parent.mkdir(parents=True, exist_ok=True)
    artifact = {
        "artifact_version": 1,
        "phase": final_phase,
        "task_name": task_name,
        "group": group,
        "model_name": model_name,
        "threshold": threshold,
        "threshold_policy": selection["threshold_policy"],
        "feature_columns": list(X_final.columns),
        "preprocessor": preprocessor,
        "model": model,
        "fit_scope": "train_plus_validation",
        "rows": int(len(X_final)),
        "positive_rows": int(y_final.sum()),
        "selection_artifact": str(sel_path),
        "selection_artifact_sha256": sha256_file(sel_path),
        "source_git_commit": source_commit,
        "test_used": False,
    }
    joblib.dump(artifact, path)

    metric_path = METRIC_ROOT / group / f"{task_name}_{final_phase.replace('.', '_')}_refit.json"
    payload = {
        "phase": final_phase,
        "task_name": task_name,
        "group": group,
        "winner": model_name,
        "threshold": threshold,
        "fit_rows": int(len(X_final)),
        "positive_rows": int(y_final.sum()),
        "fit_seconds": fit_seconds,
        "model_artifact": str(path),
        "model_sha256": sha256_file(path),
        "selection_artifact": str(sel_path),
        "source_git_commit": source_commit,
        "test_set_used": False,
    }
    write_json(metric_path, payload)
    return payload


def evaluate_frozen_test_task(
    task_name: str,
    *,
    final_phase: str,
    test_phase: str,
    group: str,
    confirm_one_time_test: bool,
    source_commit: str | None = None,
) -> dict:
    """One-time unbiased TEST evaluation of a frozen final model."""
    if not confirm_one_time_test:
        raise BinaryWorkflowError(
            "TEST remains locked. Re-run with the explicit one-time-test confirmation flag."
        )
    commit = source_commit or require_clean_git()
    model_path = final_model_path(group, task_name, final_phase)
    if not model_path.exists():
        raise BinaryWorkflowError(f"Missing frozen final model: {model_path}")

    metric_path = METRIC_ROOT / group / f"{task_name}_{test_phase.replace('.', '_')}_test.json"
    if metric_path.exists():
        raise BinaryWorkflowError(
            f"One-time TEST artifact already exists: {metric_path}. Refusing to re-evaluate."
        )

    frozen = joblib.load(model_path)
    test_bundle = load_test_only(task_name)  # first test read happens here
    test: LoadedSplit = test_bundle["test"]
    X_test, _ = prepare_model_frame(test)
    if list(X_test.columns) != list(frozen["feature_columns"]):
        raise BinaryWorkflowError(f"{task_name}: TEST feature contract differs from frozen model.")
    y_test = pd.to_numeric(test.y, errors="raise").astype(int)
    X_encoded = frozen["preprocessor"].transform(X_test)
    probabilities = np.asarray(frozen["model"].predict_proba(X_encoded)[:, 1], dtype=float)
    metrics = binary_classification_metrics(
        y_test,
        probabilities,
        threshold=float(frozen["threshold"]),
        k_fraction=K_FRACTION,
    )

    payload = {
        "artifact_version": 1,
        "phase": test_phase,
        "task_name": task_name,
        "group": group,
        "one_time_evaluation": True,
        "source_git_commit": commit,
        "frozen_model": str(model_path),
        "frozen_model_sha256": sha256_file(model_path),
        "model_name": frozen["model_name"],
        "threshold": float(frozen["threshold"]),
        "threshold_policy": frozen["threshold_policy"],
        "test_rows": int(test.rows),
        "test_positive_rows": int(y_test.sum()),
        "metrics": metrics,
        "post_test_model_changes_allowed": False,
    }
    write_json(metric_path, payload)
    payload["metrics_artifact"] = str(metric_path)
    return payload


def print_test_result(result: dict) -> None:
    m = result["metrics"]
    print()
    print("=" * 100)
    print(f"{result['phase']} — {result['task_name'].upper()} ONE-TIME TEST")
    print("=" * 100)
    print(f"model      : {result['model_name']}")
    print(f"threshold  : {result['threshold']:.4f}")
    print(f"rows       : {result['test_rows']:,}")
    print(f"positives  : {result['test_positive_rows']:,}")
    print(f"PR-AUC     : {m['pr_auc']:.6f}")
    print(f"ROC-AUC    : {m['roc_auc']:.6f}")
    print(f"precision  : {m['precision']:.6f}")
    print(f"recall     : {m['recall']:.6f}")
    print(f"F1         : {m['f1']:.6f}")
    print(f"F2         : {m['f2']:.6f}")
    print(f"lift@1%    : {m['lift_at_k']:.6f}")
    print("MODEL CHANGES AFTER TEST: NOT ALLOWED 🔒")
