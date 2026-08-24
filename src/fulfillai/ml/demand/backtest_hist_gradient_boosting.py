"""
FulfillAI Phase 8.10 temporal backtest for the Phase 8.8/8.9 demand model.

Purpose
-------
Check whether the Phase 8.9 validation champion is stable across earlier,
non-overlapping calendar months before the one-time test-set evaluation.

Experimental discipline
-----------------------
- Read ONLY demand_forecasting/train.parquet and validation.parquet.
- Never read test.parquet.
- For every fold, fit preprocessing and the estimator only on rows strictly
  earlier than that fold's evaluation month.
- Evaluate on one complete month at a time.
- Compare the Phase 8.8 reference configuration with the Phase 8.9 validation
  champion selected by tune_hist_gradient_boosting.py.
- Recompute the rolling-28 baseline from rolling_28d_avg_units for context.

Important
---------
The Phase 8.9 champion was selected on May 2026 validation data. Therefore:
- January-April are retrospective robustness folds that were not used as the
  Phase 8.9 validation period.
- May is a selection-period replay and is reported separately.
- The June-July test partition remains completely locked.

This script writes only a metrics/audit JSON artifact. It does not overwrite
any trained model artifact.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from sklearn.ensemble import HistGradientBoostingRegressor

from ..config import METRIC_ROOT, ensure_artifact_directories
from ..metrics import forecasting_metrics
from .train_hist_gradient_boosting import (
    EXPECTED_PHASE_8_8_PREDICTORS,
    ROLLING_28_VALIDATION_WAPE,
    SAFE_COLUMNS,
    build_preprocessor,
    select_safe_features,
    validate_target,
)
from .tune_hist_gradient_boosting import (
    CANDIDATES,
    TUNING_RESULTS_PATH,
)


# ============================================================================
# Experiment identity
# ============================================================================

TASK_NAME = "demand_forecasting"
PHASE = "8.10"
PRIMARY_METRIC = "wape"

PROJECT_ROOT = Path(__file__).resolve().parents[4]
FEATURE_DATASET_DIR = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "features"
    / TASK_NAME
)

TRAIN_PARQUET = FEATURE_DATASET_DIR / "train.parquet"
VALIDATION_PARQUET = FEATURE_DATASET_DIR / "validation.parquet"

BACKTEST_RESULTS_PATH = (
    METRIC_ROOT
    / "demand_hist_gradient_boosting_phase_8_10_backtest.json"
)

TARGET_COLUMN = "units_sold"
DATE_COLUMN = "demand_date"
ROLLING_28_COLUMN = "rolling_28d_avg_units"

EXPECTED_SOURCE_PREDICTOR_COUNT = 60
EXPECTED_SAFE_PREDICTOR_COUNT = 52

REFERENCE_CANDIDATE_NAME = "hgb_01_phase_8_8_reference"

# This is only an audit tolerance. The May rolling-28 backtest should reproduce
# the already-established validation baseline when the same feature column is
# used. A small tolerance protects against harmless floating-point differences.
MAY_BASELINE_TOLERANCE_POINTS = 0.01


# ============================================================================
# Backtest folds
# ============================================================================


@dataclass(frozen=True)
class BacktestFold:
    name: str
    train_end: str
    evaluation_start: str
    evaluation_end: str
    role: str


BACKTEST_FOLDS: tuple[BacktestFold, ...] = (
    BacktestFold(
        name="2026-01",
        train_end="2025-12-31",
        evaluation_start="2026-01-01",
        evaluation_end="2026-01-31",
        role="historical_robustness",
    ),
    BacktestFold(
        name="2026-02",
        train_end="2026-01-31",
        evaluation_start="2026-02-01",
        evaluation_end="2026-02-28",
        role="historical_robustness",
    ),
    BacktestFold(
        name="2026-03",
        train_end="2026-02-28",
        evaluation_start="2026-03-01",
        evaluation_end="2026-03-31",
        role="historical_robustness",
    ),
    BacktestFold(
        name="2026-04",
        train_end="2026-03-31",
        evaluation_start="2026-04-01",
        evaluation_end="2026-04-30",
        role="historical_robustness",
    ),
    BacktestFold(
        name="2026-05",
        train_end="2026-04-30",
        evaluation_start="2026-05-01",
        evaluation_end="2026-05-31",
        role="selection_period_replay",
    ),
)


# ============================================================================
# Errors
# ============================================================================


class DemandBacktestError(RuntimeError):
    """Raised when Phase 8.10 cannot continue safely."""


# ============================================================================
# Utilities
# ============================================================================


def _as_float32(matrix: Any) -> np.ndarray:
    return np.asarray(matrix, dtype=np.float32)


def _timestamp(value: str) -> pd.Timestamp:
    return pd.Timestamp(value).normalize()


def _round_metrics(metrics: dict[str, float]) -> dict[str, float]:
    return {key: float(value) for key, value in metrics.items()}


def _candidate_by_name(name: str) -> dict[str, Any]:
    matches = [candidate for candidate in CANDIDATES if candidate["name"] == name]

    if len(matches) != 1:
        raise DemandBacktestError(
            f"Expected exactly one tuning candidate named {name!r}; "
            f"found {len(matches)}."
        )

    return dict(matches[0])


def _make_model(candidate: dict[str, Any]) -> HistGradientBoostingRegressor:
    return HistGradientBoostingRegressor(
        loss="poisson",
        learning_rate=float(candidate["learning_rate"]),
        max_iter=int(candidate["max_iter"]),
        max_leaf_nodes=int(candidate["max_leaf_nodes"]),
        min_samples_leaf=int(candidate["min_samples_leaf"]),
        l2_regularization=float(candidate["l2_regularization"]),
        max_bins=255,
        early_stopping=False,
        random_state=42,
        verbose=0,
    )


def _candidate_parameters(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "loss": "poisson",
        "learning_rate": float(candidate["learning_rate"]),
        "max_iter": int(candidate["max_iter"]),
        "max_leaf_nodes": int(candidate["max_leaf_nodes"]),
        "min_samples_leaf": int(candidate["min_samples_leaf"]),
        "l2_regularization": float(candidate["l2_regularization"]),
        "max_bins": 255,
        "early_stopping": False,
        "random_state": 42,
    }


def _prediction_checks(prediction: np.ndarray, *, label: str) -> None:
    values = np.asarray(prediction, dtype=float)

    if values.ndim != 1:
        raise DemandBacktestError(
            f"{label}: predictions must be one-dimensional; got {values.shape}."
        )

    if not np.isfinite(values).all():
        raise DemandBacktestError(
            f"{label}: predictions contain NaN or infinite values."
        )

    negative = int(np.sum(values < 0))
    if negative:
        raise DemandBacktestError(
            f"{label}: Poisson model produced {negative:,} negative predictions."
        )


# ============================================================================
# Tuning-audit loading
# ============================================================================


def load_phase_8_9_champion() -> tuple[str, dict[str, Any], dict[str, Any]]:
    if not TUNING_RESULTS_PATH.exists():
        raise DemandBacktestError(
            "Phase 8.9 tuning artifact does not exist: "
            f"{TUNING_RESULTS_PATH}. Run the Phase 8.9 tuner first."
        )

    with TUNING_RESULTS_PATH.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    if payload.get("test_set_used") is not False:
        raise DemandBacktestError(
            "Phase 8.9 tuning audit does not explicitly state test_set_used=false."
        )

    best = payload.get("best_validation_candidate")
    if not isinstance(best, dict):
        raise DemandBacktestError(
            "Phase 8.9 tuning audit is missing best_validation_candidate."
        )

    champion_name = str(best.get("name", ""))
    if not champion_name:
        raise DemandBacktestError(
            "Phase 8.9 tuning audit has no champion candidate name."
        )

    champion_candidate = _candidate_by_name(champion_name)

    audit_parameters = best.get("parameters")
    if not isinstance(audit_parameters, dict):
        raise DemandBacktestError(
            "Phase 8.9 champion is missing its parameter audit."
        )

    expected = _candidate_parameters(champion_candidate)

    for key, expected_value in expected.items():
        if key not in audit_parameters:
            raise DemandBacktestError(
                f"Phase 8.9 champion audit is missing parameter {key!r}."
            )

        actual_value = audit_parameters[key]

        if isinstance(expected_value, float):
            if not np.isclose(
                float(actual_value),
                expected_value,
                rtol=0.0,
                atol=1e-12,
            ):
                raise DemandBacktestError(
                    "Phase 8.9 tuning artifact and source candidate definition "
                    f"disagree for {key}: {actual_value!r} vs {expected_value!r}."
                )
        else:
            if actual_value != expected_value:
                raise DemandBacktestError(
                    "Phase 8.9 tuning artifact and source candidate definition "
                    f"disagree for {key}: {actual_value!r} vs {expected_value!r}."
                )

    return champion_name, champion_candidate, payload


# ============================================================================
# Data loading — intentionally excludes test.parquet
# ============================================================================


def _read_pretest_parquet(path: Path, *, expected_name: str) -> pd.DataFrame:
    if not path.exists():
        raise DemandBacktestError(
            f"Required pre-test feature artifact does not exist: {path}"
        )

    if path.name == "test.parquet":
        raise DemandBacktestError("Refusing to read test.parquet during Phase 8.10.")

    frame = pd.read_parquet(path)

    if frame.empty:
        raise DemandBacktestError(f"{expected_name} parquet is empty: {path}")

    return frame


def load_backtest_frame() -> pd.DataFrame:
    print("Reading PRE-TEST feature artifacts only...")
    print(f"  train      : {TRAIN_PARQUET}")
    print(f"  validation : {VALIDATION_PARQUET}")
    print("  test       : NOT OPENED / LOCKED")

    train = _read_pretest_parquet(
        TRAIN_PARQUET,
        expected_name="train",
    )
    validation = _read_pretest_parquet(
        VALIDATION_PARQUET,
        expected_name="validation",
    )

    required = {
        DATE_COLUMN,
        TARGET_COLUMN,
        ROLLING_28_COLUMN,
        *EXPECTED_PHASE_8_8_PREDICTORS,
    }

    for split_name, frame in (
        ("train", train),
        ("validation", validation),
    ):
        missing = sorted(required - set(frame.columns))
        if missing:
            raise DemandBacktestError(
                f"{split_name}: required backtest columns are missing: {missing}"
            )

        duplicates = frame.columns[frame.columns.duplicated()].tolist()
        if duplicates:
            raise DemandBacktestError(
                f"{split_name}: duplicate columns detected: {duplicates}"
            )

    train = train.copy()
    validation = validation.copy()

    train[DATE_COLUMN] = pd.to_datetime(
        train[DATE_COLUMN],
        errors="raise",
    ).dt.normalize()

    validation[DATE_COLUMN] = pd.to_datetime(
        validation[DATE_COLUMN],
        errors="raise",
    ).dt.normalize()

    expected_train_max = _timestamp("2026-04-30")
    expected_validation_min = _timestamp("2026-05-01")
    expected_validation_max = _timestamp("2026-05-31")

    if train[DATE_COLUMN].max() > expected_train_max:
        raise DemandBacktestError(
            "train.parquet extends beyond 2026-04-30; refusing to backtest "
            "because the expected chronological contract has changed."
        )

    if validation[DATE_COLUMN].min() < expected_validation_min:
        raise DemandBacktestError(
            "validation.parquet begins before 2026-05-01; chronological "
            "contract differs from the Phase 8.9 experiment."
        )

    if validation[DATE_COLUMN].max() > expected_validation_max:
        raise DemandBacktestError(
            "validation.parquet extends beyond 2026-05-31. Phase 8.10 must "
            "not consume June/July test-period rows."
        )

    frame = pd.concat(
        [train, validation],
        axis=0,
        ignore_index=True,
        sort=False,
    )

    sort_columns = [DATE_COLUMN]
    for column in ("warehouse_id", "product_id"):
        if column in frame.columns:
            sort_columns.append(column)

    frame = (
        frame
        .sort_values(sort_columns, kind="mergesort")
        .reset_index(drop=True)
    )

    if frame[DATE_COLUMN].max() > expected_validation_max:
        raise DemandBacktestError(
            "Combined backtest frame reaches beyond 2026-05-31."
        )

    if len(EXPECTED_PHASE_8_8_PREDICTORS) != EXPECTED_SOURCE_PREDICTOR_COUNT:
        raise DemandBacktestError(
            "Phase 8.8 source predictor contract must contain exactly "
            f"{EXPECTED_SOURCE_PREDICTOR_COUNT} predictors; found "
            f"{len(EXPECTED_PHASE_8_8_PREDICTORS)}."
        )

    if len(SAFE_COLUMNS) != EXPECTED_SAFE_PREDICTOR_COUNT:
        raise DemandBacktestError(
            "Phase 8.8 safe predictor contract must contain exactly "
            f"{EXPECTED_SAFE_PREDICTOR_COUNT} predictors; found "
            f"{len(SAFE_COLUMNS)}."
        )

    return frame


# ============================================================================
# Fold construction
# ============================================================================


def build_fold_frames(
    frame: pd.DataFrame,
    fold: BacktestFold,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    train_end = _timestamp(fold.train_end)
    evaluation_start = _timestamp(fold.evaluation_start)
    evaluation_end = _timestamp(fold.evaluation_end)

    if train_end >= evaluation_start:
        raise DemandBacktestError(
            f"{fold.name}: train_end must be before evaluation_start."
        )

    train_mask = frame[DATE_COLUMN] <= train_end
    evaluation_mask = (
        (frame[DATE_COLUMN] >= evaluation_start)
        & (frame[DATE_COLUMN] <= evaluation_end)
    )

    train_frame = frame.loc[train_mask].copy()
    evaluation_frame = frame.loc[evaluation_mask].copy()

    if train_frame.empty:
        raise DemandBacktestError(f"{fold.name}: training fold is empty.")

    if evaluation_frame.empty:
        raise DemandBacktestError(f"{fold.name}: evaluation fold is empty.")

    if train_frame[DATE_COLUMN].max() >= evaluation_frame[DATE_COLUMN].min():
        raise DemandBacktestError(
            f"{fold.name}: chronological separation failed."
        )

    expected_days = pd.date_range(
        evaluation_start,
        evaluation_end,
        freq="D",
    )
    actual_days = pd.DatetimeIndex(
        evaluation_frame[DATE_COLUMN].drop_duplicates().sort_values()
    )

    if not actual_days.equals(expected_days):
        missing_days = expected_days.difference(actual_days)
        extra_days = actual_days.difference(expected_days)
        raise DemandBacktestError(
            f"{fold.name}: evaluation month is not a complete calendar window. "
            f"missing={list(missing_days.astype(str))[:5]}, "
            f"extra={list(extra_days.astype(str))[:5]}"
        )

    return train_frame, evaluation_frame


# ============================================================================
# Fold evaluation
# ============================================================================


def _rolling_28_prediction(evaluation_frame: pd.DataFrame) -> np.ndarray:
    values = pd.to_numeric(
        evaluation_frame[ROLLING_28_COLUMN],
        errors="coerce",
    ).to_numpy(dtype=float)

    if not np.isfinite(values).all():
        invalid = int(np.sum(~np.isfinite(values)))
        raise DemandBacktestError(
            f"rolling_28 baseline contains {invalid:,} missing/non-finite values."
        )

    negative = int(np.sum(values < 0))
    if negative:
        raise DemandBacktestError(
            f"rolling_28 baseline contains {negative:,} negative predictions."
        )

    return values


def evaluate_fold(
    *,
    fold: BacktestFold,
    train_frame: pd.DataFrame,
    evaluation_frame: pd.DataFrame,
    reference_candidate: dict[str, Any],
    champion_candidate: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    source_columns = list(EXPECTED_PHASE_8_8_PREDICTORS)

    X_train_source = train_frame.loc[:, source_columns].copy()
    X_eval_source = evaluation_frame.loc[:, source_columns].copy()

    X_train = select_safe_features(
        X_train_source,
        split_name=f"{fold.name}/train",
    )
    X_eval = select_safe_features(
        X_eval_source,
        split_name=f"{fold.name}/evaluation",
    )

    y_train = validate_target(
        train_frame[TARGET_COLUMN],
        split_name=f"{fold.name}/train",
    )
    y_eval = validate_target(
        evaluation_frame[TARGET_COLUMN],
        split_name=f"{fold.name}/evaluation",
    )

    preprocessor = build_preprocessor()

    preprocessing_started = time.perf_counter()
    X_train_encoded = _as_float32(
        preprocessor.fit_transform(X_train)
    )
    X_eval_encoded = _as_float32(
        preprocessor.transform(X_eval)
    )
    preprocessing_seconds = time.perf_counter() - preprocessing_started

    if X_train_encoded.ndim != 2 or X_eval_encoded.ndim != 2:
        raise DemandBacktestError(
            f"{fold.name}: encoded feature matrices must be two-dimensional."
        )

    if X_train_encoded.shape[1] != X_eval_encoded.shape[1]:
        raise DemandBacktestError(
            f"{fold.name}: train/evaluation encoded feature counts differ: "
            f"{X_train_encoded.shape[1]} vs {X_eval_encoded.shape[1]}."
        )

    if not np.isfinite(X_train_encoded).all():
        raise DemandBacktestError(
            f"{fold.name}: encoded training matrix contains NaN/Inf."
        )

    if not np.isfinite(X_eval_encoded).all():
        raise DemandBacktestError(
            f"{fold.name}: encoded evaluation matrix contains NaN/Inf."
        )

    model_results: dict[str, Any] = {}
    prediction_arrays: dict[str, np.ndarray] = {}

    model_specs = (
        ("phase_8_8_reference", reference_candidate),
        ("phase_8_9_champion", champion_candidate),
    )

    for label, candidate in model_specs:
        model = _make_model(candidate)

        started = time.perf_counter()
        model.fit(X_train_encoded, y_train)
        training_seconds = time.perf_counter() - started

        prediction = np.asarray(
            model.predict(X_eval_encoded),
            dtype=float,
        )

        _prediction_checks(
            prediction,
            label=f"{fold.name}/{label}",
        )

        metrics = forecasting_metrics(y_eval, prediction)

        model_results[label] = {
            "candidate_name": str(candidate["name"]),
            "parameters": _candidate_parameters(candidate),
            "metrics": _round_metrics(metrics),
            "training_seconds": float(training_seconds),
        }

        prediction_arrays[label] = prediction

    baseline_prediction = _rolling_28_prediction(evaluation_frame)
    baseline_metrics = forecasting_metrics(y_eval, baseline_prediction)

    prediction_arrays["rolling_28"] = baseline_prediction
    prediction_arrays["target"] = np.asarray(y_eval, dtype=float)

    reference_wape = float(
        model_results["phase_8_8_reference"]["metrics"]["wape"]
    )
    champion_wape = float(
        model_results["phase_8_9_champion"]["metrics"]["wape"]
    )
    rolling_wape = float(baseline_metrics["wape"])

    fold_result = {
        "fold": fold.name,
        "role": fold.role,
        "train_end": fold.train_end,
        "evaluation_start": fold.evaluation_start,
        "evaluation_end": fold.evaluation_end,
        "training_rows": int(len(train_frame)),
        "evaluation_rows": int(len(evaluation_frame)),
        "training_min_date": str(train_frame[DATE_COLUMN].min().date()),
        "training_max_date": str(train_frame[DATE_COLUMN].max().date()),
        "evaluation_min_date": str(evaluation_frame[DATE_COLUMN].min().date()),
        "evaluation_max_date": str(evaluation_frame[DATE_COLUMN].max().date()),
        "encoded_feature_count": int(X_train_encoded.shape[1]),
        "preprocessing_seconds": float(preprocessing_seconds),
        "rolling_28": {
            "source_column": ROLLING_28_COLUMN,
            "metrics": _round_metrics(baseline_metrics),
        },
        "phase_8_8_reference": model_results["phase_8_8_reference"],
        "phase_8_9_champion": model_results["phase_8_9_champion"],
        "comparison": {
            "champion_minus_reference_wape_points": float(
                champion_wape - reference_wape
            ),
            "champion_improvement_vs_reference_wape_points": float(
                reference_wape - champion_wape
            ),
            "champion_improvement_vs_rolling_28_wape_points": float(
                rolling_wape - champion_wape
            ),
            "champion_beats_reference": bool(
                champion_wape < reference_wape
            ),
            "champion_beats_rolling_28": bool(
                champion_wape < rolling_wape
            ),
        },
    }

    return fold_result, prediction_arrays


# ============================================================================
# Aggregate evaluation
# ============================================================================


def _pooled_metrics(
    target_parts: list[np.ndarray],
    prediction_parts: list[np.ndarray],
) -> dict[str, float]:
    target = np.concatenate(target_parts)
    prediction = np.concatenate(prediction_parts)

    return _round_metrics(
        forecasting_metrics(target, prediction)
    )


def aggregate_results(
    fold_results: list[dict[str, Any]],
    fold_predictions: dict[str, dict[str, np.ndarray]],
) -> dict[str, Any]:
    robustness_fold_names = [
        result["fold"]
        for result in fold_results
        if result["role"] == "historical_robustness"
    ]

    all_fold_names = [result["fold"] for result in fold_results]

    def pooled_for(names: list[str], key: str) -> dict[str, float]:
        target_parts = [fold_predictions[name]["target"] for name in names]
        prediction_parts = [fold_predictions[name][key] for name in names]
        return _pooled_metrics(target_parts, prediction_parts)

    robustness_reference = pooled_for(
        robustness_fold_names,
        "phase_8_8_reference",
    )
    robustness_champion = pooled_for(
        robustness_fold_names,
        "phase_8_9_champion",
    )
    robustness_rolling = pooled_for(
        robustness_fold_names,
        "rolling_28",
    )

    all_reference = pooled_for(
        all_fold_names,
        "phase_8_8_reference",
    )
    all_champion = pooled_for(
        all_fold_names,
        "phase_8_9_champion",
    )
    all_rolling = pooled_for(
        all_fold_names,
        "rolling_28",
    )

    champion_wins_robustness = sum(
        bool(result["comparison"]["champion_beats_reference"])
        for result in fold_results
        if result["role"] == "historical_robustness"
    )

    champion_wins_all = sum(
        bool(result["comparison"]["champion_beats_reference"])
        for result in fold_results
    )

    reference_fold_wapes = np.asarray(
        [
            float(result["phase_8_8_reference"]["metrics"]["wape"])
            for result in fold_results
            if result["role"] == "historical_robustness"
        ],
        dtype=float,
    )

    champion_fold_wapes = np.asarray(
        [
            float(result["phase_8_9_champion"]["metrics"]["wape"])
            for result in fold_results
            if result["role"] == "historical_robustness"
        ],
        dtype=float,
    )

    robustness_delta = (
        float(robustness_reference["wape"])
        - float(robustness_champion["wape"])
    )

    # Conservative diagnostic only. This is not a statistical significance test.
    stability_supported = bool(
        robustness_delta > 0
        and champion_wins_robustness >= 2
    )

    return {
        "historical_robustness_jan_apr": {
            "folds": robustness_fold_names,
            "phase_8_8_reference_pooled_metrics": robustness_reference,
            "phase_8_9_champion_pooled_metrics": robustness_champion,
            "rolling_28_pooled_metrics": robustness_rolling,
            "champion_improvement_vs_reference_wape_points": float(
                robustness_delta
            ),
            "champion_fold_wins_vs_reference": int(
                champion_wins_robustness
            ),
            "fold_count": int(len(robustness_fold_names)),
            "phase_8_8_reference_fold_wape_mean": float(
                reference_fold_wapes.mean()
            ),
            "phase_8_8_reference_fold_wape_std": float(
                reference_fold_wapes.std(ddof=0)
            ),
            "phase_8_9_champion_fold_wape_mean": float(
                champion_fold_wapes.mean()
            ),
            "phase_8_9_champion_fold_wape_std": float(
                champion_fold_wapes.std(ddof=0)
            ),
            "stability_supported": stability_supported,
            "stability_rule": (
                "Champion pooled Jan-Apr WAPE must beat reference and champion "
                "must win at least 2 of 4 historical robustness folds."
            ),
        },
        "all_backtest_months_jan_may": {
            "folds": all_fold_names,
            "phase_8_8_reference_pooled_metrics": all_reference,
            "phase_8_9_champion_pooled_metrics": all_champion,
            "rolling_28_pooled_metrics": all_rolling,
            "champion_improvement_vs_reference_wape_points": float(
                float(all_reference["wape"])
                - float(all_champion["wape"])
            ),
            "champion_fold_wins_vs_reference": int(champion_wins_all),
            "fold_count": int(len(all_fold_names)),
            "note": (
                "May is the Phase 8.9 selection-period replay and should not be "
                "treated as independent confirmation."
            ),
        },
    }


# ============================================================================
# Artifact persistence
# ============================================================================


def save_backtest_artifact(
    *,
    champion_name: str,
    champion_candidate: dict[str, Any],
    reference_candidate: dict[str, Any],
    tuning_payload: dict[str, Any],
    fold_results: list[dict[str, Any]],
    aggregate: dict[str, Any],
    total_seconds: float,
    may_baseline_reproduced: bool,
    may_baseline_difference_points: float,
) -> Path:
    ensure_artifact_directories()
    BACKTEST_RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "artifact_version": 1,
        "phase": PHASE,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "task": TASK_NAME,
        "experiment": "expanding_window_monthly_hgb_backtest",
        "primary_metric": PRIMARY_METRIC,
        "test_set_used": False,
        "test_partition_locked": True,
        "data_sources": {
            "train_parquet": str(TRAIN_PARQUET),
            "validation_parquet": str(VALIDATION_PARQUET),
            "test_parquet_opened": False,
        },
        "feature_contract": {
            "source_predictor_count": int(
                len(EXPECTED_PHASE_8_8_PREDICTORS)
            ),
            "safe_predictor_count": int(len(SAFE_COLUMNS)),
            "safe_predictors": list(SAFE_COLUMNS),
        },
        "phase_8_8_reference": {
            "candidate_name": str(reference_candidate["name"]),
            "parameters": _candidate_parameters(reference_candidate),
        },
        "phase_8_9_validation_champion": {
            "candidate_name": champion_name,
            "parameters": _candidate_parameters(champion_candidate),
            "original_validation_wape": float(
                tuning_payload["best_validation_candidate"]["metrics"]["wape"]
            ),
            "selection_artifact": str(TUNING_RESULTS_PATH),
        },
        "rolling_28_audit": {
            "source_column": ROLLING_28_COLUMN,
            "expected_may_validation_wape": float(
                ROLLING_28_VALIDATION_WAPE
            ),
            "reproduced_within_tolerance": bool(
                may_baseline_reproduced
            ),
            "absolute_difference_points": float(
                may_baseline_difference_points
            ),
            "tolerance_points": float(
                MAY_BASELINE_TOLERANCE_POINTS
            ),
        },
        "folds": fold_results,
        "aggregate": aggregate,
        "total_seconds": float(total_seconds),
        "interpretation_guardrails": {
            "jan_apr": (
                "Historical robustness check using the fixed Phase 8.9 champion."
            ),
            "may": (
                "Selection-period replay; not independent confirmation."
            ),
            "test": (
                "June-July remains locked for the final one-time estimate."
            ),
        },
    }

    with BACKTEST_RESULTS_PATH.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")

    return BACKTEST_RESULTS_PATH


# ============================================================================
# Reporting
# ============================================================================


def _print_candidate(candidate: dict[str, Any]) -> None:
    params = _candidate_parameters(candidate)
    print(f"candidate : {candidate['name']}")
    for key in (
        "learning_rate",
        "max_iter",
        "max_leaf_nodes",
        "min_samples_leaf",
        "l2_regularization",
    ):
        print(f"  {key:<22}: {params[key]}")


def print_fold_result(result: dict[str, Any]) -> None:
    reference = result["phase_8_8_reference"]["metrics"]
    champion = result["phase_8_9_champion"]["metrics"]
    rolling = result["rolling_28"]["metrics"]
    comparison = result["comparison"]

    print()
    print("-" * 104)
    print(
        f"{result['fold']}  |  {result['role']}  |  "
        f"train rows={result['training_rows']:,}  "
        f"eval rows={result['evaluation_rows']:,}"
    )
    print("-" * 104)
    print(
        f"{'model':<34}"
        f"{'MAE':>12}"
        f"{'RMSE':>12}"
        f"{'WAPE':>14}"
        f"{'sMAPE':>14}"
    )
    print(
        f"{'rolling_28':<34}"
        f"{float(rolling['mae']):>12.6f}"
        f"{float(rolling['rmse']):>12.6f}"
        f"{float(rolling['wape']):>13.6f}%"
        f"{float(rolling['smape']):>13.6f}%"
    )
    print(
        f"{'Phase 8.8 reference':<34}"
        f"{float(reference['mae']):>12.6f}"
        f"{float(reference['rmse']):>12.6f}"
        f"{float(reference['wape']):>13.6f}%"
        f"{float(reference['smape']):>13.6f}%"
    )
    print(
        f"{'Phase 8.9 champion':<34}"
        f"{float(champion['mae']):>12.6f}"
        f"{float(champion['rmse']):>12.6f}"
        f"{float(champion['wape']):>13.6f}%"
        f"{float(champion['smape']):>13.6f}%"
    )
    print()
    print(
        "champion improvement vs reference : "
        f"{float(comparison['champion_improvement_vs_reference_wape_points']):+.6f} "
        "WAPE points"
    )
    print(
        "champion improvement vs rolling_28: "
        f"{float(comparison['champion_improvement_vs_rolling_28_wape_points']):+.6f} "
        "WAPE points"
    )


# ============================================================================
# Main
# ============================================================================


def main() -> None:
    started = time.perf_counter()

    print()
    print("=" * 104)
    print("FulfillAI Phase 8.10 — Temporal Backtest Before Test Unlock")
    print("=" * 104)
    print()
    print("TEST PARTITION: LOCKED / NOT READ / NOT EVALUATED 🔒")

    reference_candidate = _candidate_by_name(
        REFERENCE_CANDIDATE_NAME
    )

    champion_name, champion_candidate, tuning_payload = (
        load_phase_8_9_champion()
    )

    print()
    print("PHASE 8.8 REFERENCE")
    print("-" * 104)
    _print_candidate(reference_candidate)

    print()
    print("PHASE 8.9 VALIDATION CHAMPION")
    print("-" * 104)
    _print_candidate(champion_candidate)
    print(
        "  original May validation WAPE : "
        f"{float(tuning_payload['best_validation_candidate']['metrics']['wape']):.6f}%"
    )
    print("  test_set_used in tuning audit : FALSE ✓")

    if champion_name == REFERENCE_CANDIDATE_NAME:
        print()
        print(
            "NOTE: Phase 8.9 selected the Phase 8.8 reference itself. "
            "Backtest will still run for temporal stability auditing."
        )

    print()
    print("=" * 104)
    print("LOADING PRE-TEST DATA ONLY")
    print("=" * 104)

    frame = load_backtest_frame()

    print()
    print(f"combined pre-test rows : {len(frame):,}")
    print(
        "date range             : "
        f"{frame[DATE_COLUMN].min().date()} -> "
        f"{frame[DATE_COLUMN].max().date()}"
    )
    print(f"source predictor count : {len(EXPECTED_PHASE_8_8_PREDICTORS):,}")
    print(f"safe predictor count   : {len(SAFE_COLUMNS):,}")
    print("test parquet read       : NO ✓")

    fold_results: list[dict[str, Any]] = []
    fold_predictions: dict[str, dict[str, np.ndarray]] = {}

    print()
    print("=" * 104)
    print("EXPANDING-WINDOW MONTHLY BACKTEST")
    print("=" * 104)

    for fold in BACKTEST_FOLDS:
        train_frame, evaluation_frame = build_fold_frames(
            frame,
            fold,
        )

        print()
        print(
            f"Running {fold.name}: train <= {fold.train_end}; "
            f"evaluate {fold.evaluation_start} -> {fold.evaluation_end}"
        )

        fold_result, predictions = evaluate_fold(
            fold=fold,
            train_frame=train_frame,
            evaluation_frame=evaluation_frame,
            reference_candidate=reference_candidate,
            champion_candidate=champion_candidate,
        )

        fold_results.append(fold_result)
        fold_predictions[fold.name] = predictions
        print_fold_result(fold_result)

    may_result = next(
        result for result in fold_results if result["fold"] == "2026-05"
    )
    may_rolling_wape = float(
        may_result["rolling_28"]["metrics"]["wape"]
    )
    may_baseline_difference = abs(
        may_rolling_wape - float(ROLLING_28_VALIDATION_WAPE)
    )
    may_baseline_reproduced = bool(
        may_baseline_difference <= MAY_BASELINE_TOLERANCE_POINTS
    )

    if not may_baseline_reproduced:
        raise DemandBacktestError(
            "May rolling_28 backtest did not reproduce the established "
            "validation baseline closely enough. "
            f"Observed={may_rolling_wape:.6f}%, "
            f"expected={ROLLING_28_VALIDATION_WAPE:.6f}%, "
            f"difference={may_baseline_difference:.6f} points. "
            "Do not unlock the test set until the baseline definition is audited."
        )

    aggregate = aggregate_results(
        fold_results,
        fold_predictions,
    )

    elapsed = time.perf_counter() - started

    artifact_path = save_backtest_artifact(
        champion_name=champion_name,
        champion_candidate=champion_candidate,
        reference_candidate=reference_candidate,
        tuning_payload=tuning_payload,
        fold_results=fold_results,
        aggregate=aggregate,
        total_seconds=elapsed,
        may_baseline_reproduced=may_baseline_reproduced,
        may_baseline_difference_points=may_baseline_difference,
    )

    robustness = aggregate["historical_robustness_jan_apr"]
    all_months = aggregate["all_backtest_months_jan_may"]

    print()
    print("=" * 104)
    print("PHASE 8.10 HISTORICAL ROBUSTNESS SUMMARY — JANUARY THROUGH APRIL")
    print("=" * 104)
    print(
        f"Phase 8.8 reference pooled WAPE : "
        f"{float(robustness['phase_8_8_reference_pooled_metrics']['wape']):.6f}%"
    )
    print(
        f"Phase 8.9 champion pooled WAPE  : "
        f"{float(robustness['phase_8_9_champion_pooled_metrics']['wape']):.6f}%"
    )
    print(
        f"rolling_28 pooled WAPE          : "
        f"{float(robustness['rolling_28_pooled_metrics']['wape']):.6f}%"
    )
    print(
        "champion improvement vs reference: "
        f"{float(robustness['champion_improvement_vs_reference_wape_points']):+.6f} "
        "WAPE points"
    )
    print(
        "champion fold wins vs reference   : "
        f"{int(robustness['champion_fold_wins_vs_reference'])}/"
        f"{int(robustness['fold_count'])}"
    )
    print(
        "stability diagnostic              : "
        f"{'SUPPORTED ✓' if robustness['stability_supported'] else 'NOT SUPPORTED'}"
    )

    print()
    print("=" * 104)
    print("JANUARY-MAY REPLAY SUMMARY")
    print("=" * 104)
    print(
        f"Phase 8.8 reference pooled WAPE : "
        f"{float(all_months['phase_8_8_reference_pooled_metrics']['wape']):.6f}%"
    )
    print(
        f"Phase 8.9 champion pooled WAPE  : "
        f"{float(all_months['phase_8_9_champion_pooled_metrics']['wape']):.6f}%"
    )
    print(
        "champion improvement vs reference: "
        f"{float(all_months['champion_improvement_vs_reference_wape_points']):+.6f} "
        "WAPE points"
    )
    print("May is a selection-period replay, not independent confirmation.")

    print()
    print("=" * 104)
    print("AUDIT")
    print("=" * 104)
    print("preprocessing fitted per fold on TRAIN history only : YES ✓")
    print("same Phase 8.8 feature contract used                : YES ✓")
    print("Phase 8.9 champion loaded from tuning audit          : YES ✓")
    print("May rolling_28 baseline reproduced                   : YES ✓")
    print("test.parquet opened                                   : NO ✓")
    print("test set used                                         : FALSE ✓")
    print(f"metrics artifact                                      : {artifact_path}")
    print(f"total backtest seconds                                : {elapsed:.2f}")

    print()
    print("=" * 104)
    print("PHASE 8.10 TEMPORAL BACKTEST COMPLETE ✓")
    print("TEST REMAINS LOCKED — REVIEW THIS OUTPUT BEFORE FINAL TEST EVALUATION 🔒")
    print("=" * 104)


if __name__ == "__main__":
    main()
