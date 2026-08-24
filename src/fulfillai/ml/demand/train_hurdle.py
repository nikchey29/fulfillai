"""
Permanent hurdle demand-forecasting training pipeline for FulfillAI.

Architecture
------------
1. Binary occurrence model:
       P(units_sold > 0)

2. Positive-demand magnitude model:
       E[units_sold | units_sold > 0]

3. Frozen decision threshold:
       0.925

The threshold was selected using historical Sep-Dec 2025 backtesting
and subsequently tested for temporal robustness across Jan-Apr 2026.

IMPORTANT
---------
This module trains ONLY from:

    data/processed/features/demand_forecasting/train.parquet

It does NOT read validation.parquet.
It does NOT read test.parquet.

Validation and final test evaluation are intentionally separate phases.
"""

from __future__ import annotations

import json
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from sklearn.ensemble import (
    HistGradientBoostingClassifier,
    HistGradientBoostingRegressor,
)
from sklearn.metrics import (
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

from src.fulfillai.ml.demand.train_hist_gradient_boosting import (
    EXPECTED_PHASE_8_8_PREDICTORS,
    build_preprocessor,
    select_safe_features,
    validate_target,
)


# =============================================================================
# Frozen Phase 8.13 contract
# =============================================================================

PROJECT_ROOT = Path(__file__).resolve().parents[4]

TRAIN_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "features"
    / "demand_forecasting"
    / "train.parquet"
)

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

MODEL_DIR = (
    PROJECT_ROOT
    / "artifacts"
    / "models"
    / "demand"
)

METRICS_DIR = (
    PROJECT_ROOT
    / "artifacts"
    / "metrics"
    / "demand"
)

EXPERIMENT_DIR = (
    PROJECT_ROOT
    / "artifacts"
    / "experiments"
    / "demand"
)

MODEL_PATH = (
    MODEL_DIR
    / "hurdle_phase_8_13.joblib"
)

METADATA_PATH = (
    METRICS_DIR
    / "hurdle_phase_8_13_training.json"
)

CONTRACT_PATH = (
    EXPERIMENT_DIR
    / "hurdle_phase_8_13_contract.json"
)


TARGET_COLUMN = "units_sold"
DATE_COLUMN = "demand_date"

FROZEN_OCCURRENCE_THRESHOLD = 0.925

RANDOM_STATE = 42

ARTIFACT_VERSION = 1
MODEL_VERSION = "phase_8_13"


# =============================================================================
# Model factories
# =============================================================================

def make_occurrence_model() -> HistGradientBoostingClassifier:
    """
    Binary model predicting whether demand is greater than zero.
    """

    return HistGradientBoostingClassifier(
        learning_rate=0.06,
        max_iter=200,
        max_leaf_nodes=31,
        min_samples_leaf=100,
        l2_regularization=3.0,
        max_bins=255,
        early_stopping=False,
        random_state=RANDOM_STATE,
        verbose=0,
    )


def make_magnitude_model() -> HistGradientBoostingRegressor:
    """
    Positive-demand magnitude model.

    This model is fit ONLY on observations where units_sold > 0.
    """

    return HistGradientBoostingRegressor(
        loss="poisson",
        learning_rate=0.06,
        max_iter=200,
        max_leaf_nodes=31,
        min_samples_leaf=100,
        l2_regularization=3.0,
        max_bins=255,
        early_stopping=False,
        random_state=RANDOM_STATE,
        verbose=0,
    )


# =============================================================================
# Helpers
# =============================================================================

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def to_builtin(value: Any) -> Any:
    """
    Convert NumPy / pandas scalar values into JSON-safe Python values.
    """

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

    return value


def json_dump(data: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with path.open(
        "w",
        encoding="utf-8",
    ) as handle:
        json.dump(
            data,
            handle,
            indent=2,
            default=to_builtin,
        )

        handle.write("\n")


def print_header(title: str) -> None:
    print()
    print("=" * 100)
    print(title)
    print("=" * 100)


def wape(
    y_true: np.ndarray,
    y_pred: np.ndarray,
) -> float:
    y_true = np.asarray(
        y_true,
        dtype=float,
    )

    y_pred = np.asarray(
        y_pred,
        dtype=float,
    )

    denominator = np.sum(
        np.abs(y_true)
    )

    if denominator == 0:
        return float("nan")

    return float(
        np.sum(
            np.abs(
                y_true - y_pred
            )
        )
        / denominator
        * 100.0
    )


def rmse(
    y_true: np.ndarray,
    y_pred: np.ndarray,
) -> float:
    y_true = np.asarray(
        y_true,
        dtype=float,
    )

    y_pred = np.asarray(
        y_pred,
        dtype=float,
    )

    return float(
        np.sqrt(
            np.mean(
                np.square(
                    y_true - y_pred
                )
            )
        )
    )


def mae(
    y_true: np.ndarray,
    y_pred: np.ndarray,
) -> float:
    y_true = np.asarray(
        y_true,
        dtype=float,
    )

    y_pred = np.asarray(
        y_pred,
        dtype=float,
    )

    return float(
        np.mean(
            np.abs(
                y_true - y_pred
            )
        )
    )


# =============================================================================
# Training-data loading
# =============================================================================

def load_training_data() -> pd.DataFrame:
    """
    Load the permanent Phase 8.13 training source.

    Intentionally reads train.parquet ONLY.
    """

    if not TRAIN_PATH.exists():
        raise FileNotFoundError(
            f"Training dataset does not exist: {TRAIN_PATH}"
        )

    print(
        f"reading training artifact : "
        f"{TRAIN_PATH}"
    )

    frame = pd.read_parquet(
        TRAIN_PATH
    )

    if frame.empty:
        raise ValueError(
            "Training dataset is empty."
        )

    if DATE_COLUMN not in frame.columns:
        raise ValueError(
            f"Missing date column: {DATE_COLUMN}"
        )

    if TARGET_COLUMN not in frame.columns:
        raise ValueError(
            f"Missing target column: {TARGET_COLUMN}"
        )

    frame = frame.copy()

    frame[DATE_COLUMN] = pd.to_datetime(
        frame[DATE_COLUMN],
        errors="raise",
    ).dt.normalize()

    frame = frame.sort_values(
        [
            DATE_COLUMN,
        ],
        kind="mergesort",
    ).reset_index(drop=True)

    return frame


# =============================================================================
# Feature / target preparation
# =============================================================================

def prepare_predictors(
    frame: pd.DataFrame,
    *,
    split_name: str,
) -> pd.DataFrame:
    """
    Apply the existing Phase 8 leakage-safe predictor contract.
    """

    expected = list(
        EXPECTED_PHASE_8_8_PREDICTORS
    )

    missing = sorted(
        set(expected)
        - set(frame.columns)
    )

    if missing:
        raise ValueError(
            "Training data is missing expected Phase 8.8 "
            f"predictors: {missing}"
        )

    source = frame[
        expected
    ].copy()

    safe = select_safe_features(
        source,
        split_name=split_name,
    )

    if safe.empty:
        raise ValueError(
            "No safe predictors remain after leakage filtering."
        )

    return safe


def prepare_target(
    frame: pd.DataFrame,
    *,
    split_name: str,
) -> np.ndarray:
    target = validate_target(
        frame[TARGET_COLUMN],
        split_name=split_name,
    )

    target = np.asarray(
        target,
        dtype=float,
    )

    if target.ndim != 1:
        raise ValueError(
            "Target must be one-dimensional."
        )

    if len(target) != len(frame):
        raise ValueError(
            "Target length does not match training frame."
        )

    if not np.all(
        np.isfinite(target)
    ):
        raise ValueError(
            "Target contains non-finite values."
        )

    if np.any(target < 0):
        raise ValueError(
            "Demand target contains negative values."
        )

    return target


# =============================================================================
# Main fitting logic
# =============================================================================

def fit_hurdle_model() -> dict[str, Any]:

    print_header(
        "FULFILLAI PHASE 8.13 — PERMANENT HURDLE MODEL TRAINING"
    )

    print(
        f"model version              : {MODEL_VERSION}"
    )

    print(
        f"occurrence threshold       : "
        f"{FROZEN_OCCURRENCE_THRESHOLD:.3f}"
    )

    print(
        "threshold status          : FROZEN"
    )

    print(
        "threshold selection data  : Sep-Dec 2025 historical backtest"
    )

    print(
        "robustness confirmation   : Jan-Apr 2026, 4/4 monthly wins"
    )

    print(
        "validation partition      : LOCKED / NOT READ"
    )

    print(
        "test partition            : LOCKED / NOT READ"
    )


    # -------------------------------------------------------------------------
    # Data
    # -------------------------------------------------------------------------

    print_header(
        "TRAINING DATA"
    )

    frame = load_training_data()

    X = prepare_predictors(
        frame,
        split_name="phase_8_13/train",
    )

    y = prepare_target(
        frame,
        split_name="phase_8_13/train",
    )

    occurrence_target = (
        y > 0
    ).astype(np.int8)

    positive_mask = (
        y > 0
    )

    positive_rows = int(
        positive_mask.sum()
    )

    zero_rows = int(
        len(y) - positive_rows
    )

    if positive_rows == 0:
        raise RuntimeError(
            "Magnitude model cannot be trained: "
            "training data contains no positive-demand rows."
        )

    if zero_rows == 0:
        raise RuntimeError(
            "Occurrence model cannot be trained: "
            "training data contains no zero-demand rows."
        )


    print(
        f"rows                       : "
        f"{len(frame):,}"
    )

    print(
        f"date range                 : "
        f"{frame[DATE_COLUMN].min().date()} "
        f"-> "
        f"{frame[DATE_COLUMN].max().date()}"
    )

    print(
        f"source predictor count     : "
        f"{len(EXPECTED_PHASE_8_8_PREDICTORS)}"
    )

    print(
        f"safe predictor count       : "
        f"{X.shape[1]}"
    )

    print(
        f"positive-demand rows       : "
        f"{positive_rows:,}"
    )

    print(
        f"zero-demand rows           : "
        f"{zero_rows:,}"
    )

    print(
        f"positive-demand prevalence : "
        f"{positive_rows / len(y) * 100:.2f}%"
    )


    # -------------------------------------------------------------------------
    # Preprocessing
    # -------------------------------------------------------------------------

    print_header(
        "PREPROCESSING — TRAIN ONLY"
    )

    preprocessor = build_preprocessor()

    preprocessing_started = (
        time.perf_counter()
    )

    X_encoded = preprocessor.fit_transform(
        X
    )

    X_encoded = np.asarray(
        X_encoded,
        dtype=np.float32,
    )

    preprocessing_seconds = (
        time.perf_counter()
        - preprocessing_started
    )


    if X_encoded.ndim != 2:
        raise RuntimeError(
            "Encoded feature matrix is not two-dimensional."
        )

    if X_encoded.shape[0] != len(frame):
        raise RuntimeError(
            "Encoded training matrix lost rows."
        )

    print(
        f"encoded feature count      : "
        f"{X_encoded.shape[1]:,}"
    )

    print(
        f"preprocessing seconds      : "
        f"{preprocessing_seconds:.2f}"
    )


    # -------------------------------------------------------------------------
    # Occurrence model
    # -------------------------------------------------------------------------

    print_header(
        "OCCURRENCE MODEL"
    )

    positive_count = int(
        occurrence_target.sum()
    )

    negative_count = int(
        len(occurrence_target)
        - positive_count
    )

    positive_weight = (
        negative_count
        / positive_count
    )

    sample_weight = np.where(
        occurrence_target == 1,
        positive_weight,
        1.0,
    )

    print(
        f"positive class weight      : "
        f"{positive_weight:.6f}"
    )

    occurrence = (
        make_occurrence_model()
    )

    occurrence_started = (
        time.perf_counter()
    )

    occurrence.fit(
        X_encoded,
        occurrence_target,
        sample_weight=sample_weight,
    )

    occurrence_seconds = (
        time.perf_counter()
        - occurrence_started
    )

    print(
        f"training seconds           : "
        f"{occurrence_seconds:.2f}"
    )


    # -------------------------------------------------------------------------
    # Positive-demand magnitude model
    # -------------------------------------------------------------------------

    print_header(
        "POSITIVE-DEMAND MAGNITUDE MODEL"
    )

    magnitude = make_magnitude_model()

    magnitude_started = (
        time.perf_counter()
    )

    magnitude.fit(
        X_encoded[
            positive_mask
        ],
        y[
            positive_mask
        ],
    )

    magnitude_seconds = (
        time.perf_counter()
        - magnitude_started
    )

    print(
        f"positive training rows     : "
        f"{positive_rows:,}"
    )

    print(
        f"training seconds           : "
        f"{magnitude_seconds:.2f}"
    )


    # -------------------------------------------------------------------------
    # Training-only smoke-test predictions
    #
    # These metrics are NOT model-selection estimates.
    # They exist only as fit/integrity diagnostics.
    # -------------------------------------------------------------------------

    print_header(
        "TRAINING-ONLY INTEGRITY DIAGNOSTICS"
    )

    occurrence_probability = (
        occurrence.predict_proba(
            X_encoded
        )[:, 1]
    )

    predicted_occurrence = (
        occurrence_probability
        >= FROZEN_OCCURRENCE_THRESHOLD
    ).astype(np.int8)

    magnitude_prediction = np.asarray(
        magnitude.predict(
            X_encoded
        ),
        dtype=float,
    )

    magnitude_prediction = np.clip(
        magnitude_prediction,
        0.0,
        None,
    )

    final_prediction = np.where(
        predicted_occurrence == 1,
        magnitude_prediction,
        0.0,
    )


    predicted_positive_rows = int(
        predicted_occurrence.sum()
    )

    predicted_positive_rate = float(
        predicted_positive_rows
        / len(predicted_occurrence)
    )


    train_precision = precision_score(
        occurrence_target,
        predicted_occurrence,
        zero_division=0,
    )

    train_recall = recall_score(
        occurrence_target,
        predicted_occurrence,
        zero_division=0,
    )

    train_f1 = f1_score(
        occurrence_target,
        predicted_occurrence,
        zero_division=0,
    )


    try:
        train_roc_auc = roc_auc_score(
            occurrence_target,
            occurrence_probability,
        )
    except ValueError:
        train_roc_auc = float("nan")


    train_mae = mae(
        y,
        final_prediction,
    )

    train_rmse = rmse(
        y,
        final_prediction,
    )

    train_wape = wape(
        y,
        final_prediction,
    )


    print(
        "NOTE: these are TRAIN diagnostics, "
        "not validation estimates."
    )

    print()

    print(
        f"actual positive rate       : "
        f"{positive_rows / len(y) * 100:.2f}%"
    )

    print(
        f"predicted positive rate    : "
        f"{predicted_positive_rate * 100:.2f}%"
    )

    print(
        f"precision                  : "
        f"{train_precision:.6f}"
    )

    print(
        f"recall                     : "
        f"{train_recall:.6f}"
    )

    print(
        f"F1                         : "
        f"{train_f1:.6f}"
    )

    print(
        f"ROC-AUC                    : "
        f"{train_roc_auc:.6f}"
    )

    print(
        f"MAE                        : "
        f"{train_mae:.6f}"
    )

    print(
        f"RMSE                       : "
        f"{train_rmse:.6f}"
    )

    print(
        f"WAPE                       : "
        f"{train_wape:.6f}%"
    )

    print(
        f"exact-zero forecasts       : "
        f"{int(np.sum(final_prediction == 0)):,}"
    )

    print(
        f"negative forecasts         : "
        f"{int(np.sum(final_prediction < 0)):,}"
    )


    if np.any(
        final_prediction < 0
    ):
        raise RuntimeError(
            "Hurdle model generated negative forecasts."
        )


    # -------------------------------------------------------------------------
    # Persist model bundle
    # -------------------------------------------------------------------------

    print_header(
        "PERSISTING MODEL ARTIFACTS"
    )

    MODEL_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    METRICS_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    EXPERIMENT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )


    contract = {
        "artifact_version": ARTIFACT_VERSION,
        "model_version": MODEL_VERSION,
        "task": "demand_forecasting",
        "architecture": "hurdle",
        "target_column": TARGET_COLUMN,
        "date_column": DATE_COLUMN,
        "source_predictors": list(
            EXPECTED_PHASE_8_8_PREDICTORS
        ),
        "safe_predictors": list(
            X.columns
        ),
        "safe_predictor_count": int(
            X.shape[1]
        ),
        "encoded_feature_count": int(
            X_encoded.shape[1]
        ),
        "occurrence_target": "units_sold > 0",
        "occurrence_threshold": (
            FROZEN_OCCURRENCE_THRESHOLD
        ),
        "threshold_status": "frozen",
        "threshold_selection_period": (
            "Sep-Dec 2025 historical backtest"
        ),
        "temporal_robustness_period": (
            "Jan-Apr 2026"
        ),
        "temporal_robustness_monthly_wins": "4/4",
        "primary_metric": "WAPE",
        "occurrence_secondary_metrics": [
            "precision",
            "recall",
            "f1",
            "roc_auc",
        ],
        "magnitude_training_rule": (
            "fit only where units_sold > 0"
        ),
        "validation_accessed": False,
        "test_accessed": False,
    }


    metadata = {
        **contract,
        "generated_at_utc": utc_now(),
        "training_source": str(
            TRAIN_PATH.relative_to(
                PROJECT_ROOT
            )
        ),
        "training_rows": int(
            len(frame)
        ),
        "training_min_date": (
            frame[DATE_COLUMN]
            .min()
            .date()
            .isoformat()
        ),
        "training_max_date": (
            frame[DATE_COLUMN]
            .max()
            .date()
            .isoformat()
        ),
        "positive_demand_rows": (
            positive_rows
        ),
        "zero_demand_rows": (
            zero_rows
        ),
        "positive_demand_prevalence": float(
            positive_rows / len(frame)
        ),
        "positive_class_weight": float(
            positive_weight
        ),
        "training_diagnostics": {
            "occurrence_precision": float(
                train_precision
            ),
            "occurrence_recall": float(
                train_recall
            ),
            "occurrence_f1": float(
                train_f1
            ),
            "occurrence_roc_auc": float(
                train_roc_auc
            ),
            "forecast_mae": float(
                train_mae
            ),
            "forecast_rmse": float(
                train_rmse
            ),
            "forecast_wape": float(
                train_wape
            ),
            "predicted_positive_rate": float(
                predicted_positive_rate
            ),
            "exact_zero_forecasts": int(
                np.sum(
                    final_prediction == 0
                )
            ),
        },
        "timing_seconds": {
            "preprocessing": float(
                preprocessing_seconds
            ),
            "occurrence_model": float(
                occurrence_seconds
            ),
            "magnitude_model": float(
                magnitude_seconds
            ),
        },
        "occurrence_model_parameters": (
            occurrence.get_params(
                deep=False
            )
        ),
        "magnitude_model_parameters": (
            magnitude.get_params(
                deep=False
            )
        ),
        "software": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "pandas": pd.__version__,
            "numpy": np.__version__,
        },
    }


    bundle = {
        "artifact_version": ARTIFACT_VERSION,
        "model_version": MODEL_VERSION,
        "task": "demand_forecasting",
        "architecture": "hurdle",
        "target_column": TARGET_COLUMN,
        "date_column": DATE_COLUMN,
        "threshold": (
            FROZEN_OCCURRENCE_THRESHOLD
        ),
        "source_predictors": list(
            EXPECTED_PHASE_8_8_PREDICTORS
        ),
        "safe_predictors": list(
            X.columns
        ),
        "preprocessor": preprocessor,
        "occurrence_model": occurrence,
        "magnitude_model": magnitude,
        "contract": contract,
    }


    joblib.dump(
        bundle,
        MODEL_PATH,
    )

    json_dump(
        metadata,
        METADATA_PATH,
    )

    json_dump(
        contract,
        CONTRACT_PATH,
    )


    print(
        f"model bundle               : "
        f"{MODEL_PATH}"
    )

    print(
        f"training metadata          : "
        f"{METADATA_PATH}"
    )

    print(
        f"model contract             : "
        f"{CONTRACT_PATH}"
    )


    # -------------------------------------------------------------------------
    # Round-trip artifact verification
    # -------------------------------------------------------------------------

    print_header(
        "ARTIFACT ROUND-TRIP VERIFICATION"
    )

    loaded = joblib.load(
        MODEL_PATH
    )


    required_bundle_keys = {
        "artifact_version",
        "model_version",
        "task",
        "architecture",
        "target_column",
        "date_column",
        "threshold",
        "source_predictors",
        "safe_predictors",
        "preprocessor",
        "occurrence_model",
        "magnitude_model",
        "contract",
    }


    missing_bundle_keys = sorted(
        required_bundle_keys
        - set(
            loaded.keys()
        )
    )


    if missing_bundle_keys:
        raise RuntimeError(
            "Serialized model bundle is missing keys: "
            f"{missing_bundle_keys}"
        )


    if not np.isclose(
        float(
            loaded["threshold"]
        ),
        FROZEN_OCCURRENCE_THRESHOLD,
    ):
        raise RuntimeError(
            "Serialized occurrence threshold changed."
        )


    if list(
        loaded["safe_predictors"]
    ) != list(
        X.columns
    ):
        raise RuntimeError(
            "Serialized feature contract changed."
        )


    print(
        "model bundle reload       : PASSED ✓"
    )

    print(
        "threshold round-trip      : PASSED ✓"
    )

    print(
        "feature contract          : PASSED ✓"
    )


    # -------------------------------------------------------------------------
    # Final audit
    # -------------------------------------------------------------------------

    print_header(
        "PHASE 8.13 AUDIT"
    )

    print(
        "training source           : train.parquet"
    )

    print(
        "validation.parquet read   : NO"
    )

    print(
        "test.parquet read         : NO"
    )

    print(
        f"frozen threshold           : "
        f"{FROZEN_OCCURRENCE_THRESHOLD:.3f}"
    )

    print(
        "threshold retuned         : NO"
    )

    print(
        "safe feature contract     : YES"
    )

    print(
        "preprocessor fit scope    : TRAIN ONLY"
    )

    print(
        "occurrence model fit      : TRAIN ONLY"
    )

    print(
        "magnitude model fit       : TRAIN POSITIVE ROWS ONLY"
    )

    print(
        "model artifact created    : YES"
    )

    print(
        "test estimate produced    : NO"
    )

    print()
    print(
        "PHASE 8.13 PERMANENT HURDLE TRAINING PASSED ✓"
    )

    print(
        "VALIDATION REMAINS LOCKED UNTIL EXPLICIT "
        "PHASE 8.14 EVALUATION 🔒"
    )

    print(
        "TEST REMAINS LOCKED 🔒"
    )

    print("=" * 100)

    return metadata


def main() -> None:
    fit_hurdle_model()


if __name__ == "__main__":
    main()
