"""
Phase 8.14 — one-time validation evaluation for the permanent FulfillAI
hurdle demand-forecasting model.

Rules
-----
- Loads the frozen Phase 8.13 model bundle.
- Reads validation.parquet exactly for evaluation.
- Does NOT refit preprocessing.
- Does NOT refit either model.
- Does NOT change the threshold.
- Does NOT read test.parquet.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from sklearn.metrics import (
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
    average_precision_score,
    confusion_matrix,
)

from src.fulfillai.ml.demand.train_hist_gradient_boosting import (
    validate_target,
)


# =============================================================================
# Paths
# =============================================================================

PROJECT_ROOT = Path(__file__).resolve().parents[4]

VALIDATION_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "features"
    / "demand_forecasting"
    / "validation.parquet"
)

TEST_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "features"
    / "demand_forecasting"
    / "test.parquet"
)

MODEL_PATH = (
    PROJECT_ROOT
    / "artifacts"
    / "models"
    / "demand"
    / "hurdle_phase_8_13.joblib"
)

METRICS_PATH = (
    PROJECT_ROOT
    / "artifacts"
    / "metrics"
    / "demand"
    / "hurdle_phase_8_14_validation.json"
)


TARGET_COLUMN = "units_sold"
DATE_COLUMN = "demand_date"

ROLLING_BASELINE_COLUMN = "rolling_28d_avg_units"

EXPECTED_THRESHOLD = 0.925


# =============================================================================
# Helpers
# =============================================================================

def header(title: str) -> None:
    print()
    print("=" * 100)
    print(title)
    print("=" * 100)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def mae(y_true, y_pred) -> float:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)

    return float(
        np.mean(
            np.abs(y_true - y_pred)
        )
    )


def rmse(y_true, y_pred) -> float:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)

    return float(
        np.sqrt(
            np.mean(
                np.square(y_true - y_pred)
            )
        )
    )


def wape(y_true, y_pred) -> float:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)

    denominator = np.sum(
        np.abs(y_true)
    )

    if denominator == 0:
        return float("nan")

    return float(
        np.sum(
            np.abs(y_true - y_pred)
        )
        / denominator
        * 100.0
    )


def smape(y_true, y_pred) -> float:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)

    denominator = (
        np.abs(y_true)
        + np.abs(y_pred)
    )

    mask = denominator > 0

    if not np.any(mask):
        return 0.0

    values = (
        2.0
        * np.abs(
            y_pred[mask]
            - y_true[mask]
        )
        / denominator[mask]
    )

    return float(
        np.mean(values)
        * 100.0
    )


def json_default(value):
    if isinstance(value, np.integer):
        return int(value)

    if isinstance(value, np.floating):
        return float(value)

    if isinstance(value, np.bool_):
        return bool(value)

    if isinstance(value, pd.Timestamp):
        return value.isoformat()

    if isinstance(value, Path):
        return str(value)

    raise TypeError(
        f"Cannot JSON serialize {type(value)!r}"
    )


# =============================================================================
# Evaluation
# =============================================================================

def main() -> None:

    header(
        "FULFILLAI PHASE 8.14 — ONE-TIME VALIDATION EVALUATION"
    )

    # -------------------------------------------------------------------------
    # Model bundle
    # -------------------------------------------------------------------------

    if not MODEL_PATH.exists():
        raise FileNotFoundError(
            f"Missing Phase 8.13 model bundle: {MODEL_PATH}"
        )

    print(
        f"model artifact             : {MODEL_PATH}"
    )

    bundle = joblib.load(
        MODEL_PATH
    )

    required_keys = {
        "threshold",
        "safe_predictors",
        "preprocessor",
        "occurrence_model",
        "magnitude_model",
        "contract",
    }

    missing_keys = sorted(
        required_keys
        - set(bundle)
    )

    if missing_keys:
        raise RuntimeError(
            f"Model bundle missing keys: {missing_keys}"
        )

    threshold = float(
        bundle["threshold"]
    )

    if not np.isclose(
        threshold,
        EXPECTED_THRESHOLD,
    ):
        raise RuntimeError(
            "Frozen threshold mismatch: "
            f"expected {EXPECTED_THRESHOLD}, "
            f"found {threshold}"
        )

    safe_predictors = list(
        bundle["safe_predictors"]
    )

    preprocessor = bundle[
        "preprocessor"
    ]

    occurrence_model = bundle[
        "occurrence_model"
    ]

    magnitude_model = bundle[
        "magnitude_model"
    ]

    print(
        f"frozen threshold           : {threshold:.3f}"
    )

    print(
        f"safe predictor count       : {len(safe_predictors)}"
    )

    print(
        "threshold tuning allowed  : NO"
    )

    print(
        "model refitting allowed   : NO"
    )


    # -------------------------------------------------------------------------
    # Validation dataset
    # -------------------------------------------------------------------------

    header(
        "READING VALIDATION PARTITION"
    )

    if not VALIDATION_PATH.exists():
        raise FileNotFoundError(
            f"Validation dataset not found: {VALIDATION_PATH}"
        )

    validation = pd.read_parquet(
        VALIDATION_PATH
    )

    if validation.empty:
        raise RuntimeError(
            "Validation dataset is empty."
        )

    if DATE_COLUMN not in validation.columns:
        raise RuntimeError(
            f"Missing {DATE_COLUMN!r}."
        )

    if TARGET_COLUMN not in validation.columns:
        raise RuntimeError(
            f"Missing {TARGET_COLUMN!r}."
        )

    if (
        ROLLING_BASELINE_COLUMN
        not in validation.columns
    ):
        raise RuntimeError(
            "Missing rolling-28 baseline column: "
            f"{ROLLING_BASELINE_COLUMN}"
        )

    validation = validation.copy()

    validation[DATE_COLUMN] = pd.to_datetime(
        validation[DATE_COLUMN],
        errors="raise",
    ).dt.normalize()

    validation = validation.sort_values(
        DATE_COLUMN,
        kind="mergesort",
    ).reset_index(drop=True)


    missing_predictors = sorted(
        set(safe_predictors)
        - set(validation.columns)
    )

    if missing_predictors:
        raise RuntimeError(
            "Validation data is missing frozen predictor columns: "
            f"{missing_predictors}"
        )


    print(
        f"rows                       : {len(validation):,}"
    )

    print(
        f"date range                 : "
        f"{validation[DATE_COLUMN].min().date()} "
        f"-> "
        f"{validation[DATE_COLUMN].max().date()}"
    )

    print(
        "validation partition read : YES — Phase 8.14"
    )

    print(
        "test partition read       : NO 🔒"
    )


    # -------------------------------------------------------------------------
    # Frozen feature contract
    # -------------------------------------------------------------------------

    header(
        "FROZEN FEATURE CONTRACT"
    )

    X_validation = validation[
        safe_predictors
    ].copy()

    y_validation = np.asarray(
        validate_target(
            validation[TARGET_COLUMN],
            split_name="phase_8_14/validation",
        ),
        dtype=float,
    )


    if len(X_validation) != len(y_validation):
        raise RuntimeError(
            "Validation predictors and target are misaligned."
        )


    print(
        f"predictor columns          : "
        f"{X_validation.shape[1]}"
    )

    print(
        "preprocessor fit          : NO"
    )

    print(
        "existing preprocessor     : TRANSFORM ONLY"
    )


    # -------------------------------------------------------------------------
    # Transform only — NO FIT
    # -------------------------------------------------------------------------

    X_encoded = preprocessor.transform(
        X_validation
    )

    X_encoded = np.asarray(
        X_encoded,
        dtype=np.float32,
    )


    print(
        f"encoded feature count      : "
        f"{X_encoded.shape[1]}"
    )


    # -------------------------------------------------------------------------
    # Frozen hurdle inference
    # -------------------------------------------------------------------------

    header(
        "FROZEN HURDLE INFERENCE"
    )

    occurrence_probability = (
        occurrence_model.predict_proba(
            X_encoded
        )[:, 1]
    )


    predicted_occurrence = (
        occurrence_probability
        >= threshold
    ).astype(np.int8)


    magnitude_prediction = np.asarray(
        magnitude_model.predict(
            X_encoded
        ),
        dtype=float,
    )

    magnitude_prediction = np.clip(
        magnitude_prediction,
        0.0,
        None,
    )


    hurdle_prediction = np.where(
        predicted_occurrence == 1,
        magnitude_prediction,
        0.0,
    )


    rolling_prediction = pd.to_numeric(
        validation[
            ROLLING_BASELINE_COLUMN
        ],
        errors="raise",
    ).to_numpy(dtype=float)


    if np.any(
        hurdle_prediction < 0
    ):
        raise RuntimeError(
            "Negative hurdle forecasts detected."
        )


    print(
        f"predictions                : "
        f"{len(hurdle_prediction):,}"
    )

    print(
        f"exact-zero forecasts       : "
        f"{np.sum(hurdle_prediction == 0):,}"
    )

    print(
        f"negative forecasts         : "
        f"{np.sum(hurdle_prediction < 0):,}"
    )


    # -------------------------------------------------------------------------
    # Forecast metrics
    # -------------------------------------------------------------------------

    header(
        "PHASE 8.14 VALIDATION FORECAST METRICS"
    )

    hurdle_mae = mae(
        y_validation,
        hurdle_prediction,
    )

    hurdle_rmse = rmse(
        y_validation,
        hurdle_prediction,
    )

    hurdle_wape = wape(
        y_validation,
        hurdle_prediction,
    )

    hurdle_smape = smape(
        y_validation,
        hurdle_prediction,
    )


    rolling_mae = mae(
        y_validation,
        rolling_prediction,
    )

    rolling_rmse = rmse(
        y_validation,
        rolling_prediction,
    )

    rolling_wape = wape(
        y_validation,
        rolling_prediction,
    )

    rolling_smape = smape(
        y_validation,
        rolling_prediction,
    )


    print(
        f"{'MODEL':<18}"
        f"{'MAE':>12}"
        f"{'RMSE':>12}"
        f"{'WAPE':>14}"
        f"{'sMAPE':>14}"
    )

    print("-" * 70)

    print(
        f"{'hurdle_0.925':<18}"
        f"{hurdle_mae:>12.6f}"
        f"{hurdle_rmse:>12.6f}"
        f"{hurdle_wape:>13.6f}%"
        f"{hurdle_smape:>13.6f}%"
    )

    print(
        f"{'rolling_28':<18}"
        f"{rolling_mae:>12.6f}"
        f"{rolling_rmse:>12.6f}"
        f"{rolling_wape:>13.6f}%"
        f"{rolling_smape:>13.6f}%"
    )


    improvement = (
        rolling_wape
        - hurdle_wape
    )

    relative_improvement = (
        improvement
        / rolling_wape
        * 100.0
    )


    print()

    print(
        f"WAPE improvement           : "
        f"{improvement:+.6f} points"
    )

    print(
        f"relative WAPE improvement  : "
        f"{relative_improvement:+.2f}%"
    )


    # -------------------------------------------------------------------------
    # Occurrence diagnostics
    # -------------------------------------------------------------------------

    header(
        "OCCURRENCE CLASSIFIER DIAGNOSTICS"
    )

    actual_occurrence = (
        y_validation > 0
    ).astype(np.int8)


    precision = precision_score(
        actual_occurrence,
        predicted_occurrence,
        zero_division=0,
    )

    recall = recall_score(
        actual_occurrence,
        predicted_occurrence,
        zero_division=0,
    )

    f1 = f1_score(
        actual_occurrence,
        predicted_occurrence,
        zero_division=0,
    )


    try:
        roc_auc = roc_auc_score(
            actual_occurrence,
            occurrence_probability,
        )
    except ValueError:
        roc_auc = float("nan")


    try:
        pr_auc = average_precision_score(
            actual_occurrence,
            occurrence_probability,
        )
    except ValueError:
        pr_auc = float("nan")


    tn, fp, fn, tp = confusion_matrix(
        actual_occurrence,
        predicted_occurrence,
        labels=[0, 1],
    ).ravel()


    actual_positive_rate = float(
        actual_occurrence.mean()
    )

    predicted_positive_rate = float(
        predicted_occurrence.mean()
    )


    print(
        f"actual positive rows       : "
        f"{actual_occurrence.sum():,} / "
        f"{len(actual_occurrence):,} "
        f"({actual_positive_rate * 100:.2f}%)"
    )

    print(
        f"predicted positive rows    : "
        f"{predicted_occurrence.sum():,} / "
        f"{len(predicted_occurrence):,} "
        f"({predicted_positive_rate * 100:.2f}%)"
    )

    print()

    print(
        f"PR-AUC                     : {pr_auc:.6f}"
    )

    print(
        f"ROC-AUC                    : {roc_auc:.6f}"
    )

    print(
        f"precision                  : {precision:.6f}"
    )

    print(
        f"recall                     : {recall:.6f}"
    )

    print(
        f"F1                         : {f1:.6f}"
    )

    print()

    print("CONFUSION MATRIX")

    print(
        f"TP : {tp:,}"
    )

    print(
        f"FP : {fp:,}"
    )

    print(
        f"TN : {tn:,}"
    )

    print(
        f"FN : {fn:,}"
    )


    # -------------------------------------------------------------------------
    # Zero / positive demand decomposition
    # -------------------------------------------------------------------------

    header(
        "VALIDATION ERROR DECOMPOSITION"
    )

    zero_mask = (
        y_validation == 0
    )

    positive_mask = (
        y_validation > 0
    )


    def absolute_error_total(mask, prediction):
        return float(
            np.sum(
                np.abs(
                    y_validation[mask]
                    - prediction[mask]
                )
            )
        )


    hurdle_zero_error = (
        absolute_error_total(
            zero_mask,
            hurdle_prediction,
        )
    )

    rolling_zero_error = (
        absolute_error_total(
            zero_mask,
            rolling_prediction,
        )
    )

    hurdle_positive_error = (
        absolute_error_total(
            positive_mask,
            hurdle_prediction,
        )
    )

    rolling_positive_error = (
        absolute_error_total(
            positive_mask,
            rolling_prediction,
        )
    )


    print(
        f"zero-demand rows           : "
        f"{zero_mask.sum():,} "
        f"({zero_mask.mean() * 100:.2f}%)"
    )

    print(
        f"positive-demand rows       : "
        f"{positive_mask.sum():,} "
        f"({positive_mask.mean() * 100:.2f}%)"
    )

    print()

    print(
        f"hurdle zero-row abs error  : "
        f"{hurdle_zero_error:,.2f}"
    )

    print(
        f"rolling zero-row abs error : "
        f"{rolling_zero_error:,.2f}"
    )

    print()

    print(
        f"hurdle +row abs error      : "
        f"{hurdle_positive_error:,.2f}"
    )

    print(
        f"rolling +row abs error     : "
        f"{rolling_positive_error:,.2f}"
    )


    # -------------------------------------------------------------------------
    # Final result
    # -------------------------------------------------------------------------

    header(
        "PHASE 8.14 MODEL DECISION"
    )

    if hurdle_wape < rolling_wape:
        decision = (
            "HURDLE MODEL BEATS ROLLING_28 ON VALIDATION"
        )
        passed = True
    else:
        decision = (
            "HURDLE MODEL DOES NOT BEAT ROLLING_28 "
            "ON VALIDATION"
        )
        passed = False


    print(
        f"rolling_28 WAPE            : "
        f"{rolling_wape:.6f}%"
    )

    print(
        f"hurdle WAPE                : "
        f"{hurdle_wape:.6f}%"
    )

    print(
        f"difference                 : "
        f"{improvement:+.6f} WAPE points"
    )

    print()

    print(
        f"RESULT: {decision}"
    )


    # -------------------------------------------------------------------------
    # Artifact
    # -------------------------------------------------------------------------

    metrics = {
        "artifact_version": 1,
        "phase": "8.14",
        "generated_at_utc": utc_now(),
        "evaluation_partition": "validation",
        "validation_rows": int(
            len(validation)
        ),
        "validation_min_date": (
            validation[DATE_COLUMN]
            .min()
            .date()
            .isoformat()
        ),
        "validation_max_date": (
            validation[DATE_COLUMN]
            .max()
            .date()
            .isoformat()
        ),
        "model_artifact": str(
            MODEL_PATH.relative_to(
                PROJECT_ROOT
            )
        ),
        "threshold": threshold,
        "threshold_retuned": False,
        "model_refit": False,
        "preprocessor_refit": False,
        "test_accessed": False,
        "forecast_metrics": {
            "hurdle": {
                "mae": hurdle_mae,
                "rmse": hurdle_rmse,
                "wape": hurdle_wape,
                "smape": hurdle_smape,
            },
            "rolling_28": {
                "mae": rolling_mae,
                "rmse": rolling_rmse,
                "wape": rolling_wape,
                "smape": rolling_smape,
            },
            "wape_improvement_points": (
                improvement
            ),
            "relative_wape_improvement_pct": (
                relative_improvement
            ),
        },
        "occurrence_metrics": {
            "actual_positive_rate": (
                actual_positive_rate
            ),
            "predicted_positive_rate": (
                predicted_positive_rate
            ),
            "precision": float(
                precision
            ),
            "recall": float(
                recall
            ),
            "f1": float(
                f1
            ),
            "roc_auc": float(
                roc_auc
            ),
            "pr_auc": float(
                pr_auc
            ),
            "confusion_matrix": {
                "tp": int(tp),
                "fp": int(fp),
                "tn": int(tn),
                "fn": int(fn),
            },
        },
        "decision": decision,
        "passed": passed,
    }


    METRICS_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with METRICS_PATH.open(
        "w",
        encoding="utf-8",
    ) as handle:
        json.dump(
            metrics,
            handle,
            indent=2,
            default=json_default,
        )

        handle.write("\n")


    print()

    print(
        f"metrics artifact           : "
        f"{METRICS_PATH}"
    )


    # -------------------------------------------------------------------------
    # Audit
    # -------------------------------------------------------------------------

    header(
        "PHASE 8.14 AUDIT"
    )

    print(
        "Phase 8.13 model loaded    : YES"
    )

    print(
        "train.parquet read         : NO"
    )

    print(
        "validation.parquet read    : YES"
    )

    print(
        "test.parquet read          : NO 🔒"
    )

    print(
        "preprocessor refit         : NO"
    )

    print(
        "occurrence model refit     : NO"
    )

    print(
        "magnitude model refit      : NO"
    )

    print(
        f"threshold                  : "
        f"{threshold:.3f}"
    )

    print(
        "threshold retuned          : NO"
    )

    print(
        "model selection performed  : NO"
    )

    print()

    print(
        "PHASE 8.14 VALIDATION EVALUATION COMPLETE ✓"
    )

    print(
        "TEST PARTITION REMAINS LOCKED 🔒"
    )

    print("=" * 100)


if __name__ == "__main__":
    main()
