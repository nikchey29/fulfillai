"""
Train the first FulfillAI demand forecasting model.

Model
-----
PoissonRegressor

Why Poisson?
------------
Demand is non-negative and count-like. A Poisson generalized linear
model therefore provides a substantially more appropriate first trained
baseline than ordinary least-squares regression.

Model selection uses validation data only.

The test partition is deliberately never evaluated by this module.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from sklearn.linear_model import PoissonRegressor
from sklearn.pipeline import Pipeline

from ..config import (
    METRIC_ROOT,
    MODEL_ROOT,
    ensure_artifact_directories,
)
from ..data import load_train_validation_dataset
from ..metrics import forecasting_metrics
from ..preprocessing import (
    build_preprocessor,
    infer_feature_schema,
    print_feature_schema,
)


# ======================================================================
# Configuration
# ======================================================================

TASK_NAME = "demand_forecasting"

MODEL_NAME = "poisson_regression"

PRIMARY_METRIC = "wape"

BASELINE_NAME = "rolling_28"

BASELINE_VALIDATION_WAPE = 88.27831765529037

MODEL_PATH = (
    MODEL_ROOT
    / "demand"
    / "poisson_regression.joblib"
)

METRICS_PATH = (
    METRIC_ROOT
    / "demand_poisson_validation.json"
)


# ======================================================================
# Exceptions
# ======================================================================

class DemandTrainingError(RuntimeError):
    """Raised when demand training cannot continue safely."""


# ======================================================================
# Helpers
# ======================================================================

def validate_target(
    target: pd.Series,
    *,
    split_name: str,
) -> np.ndarray:
    """Validate non-negative demand target."""

    values = pd.to_numeric(
        target,
        errors="raise",
    ).to_numpy(
        dtype=float
    )

    if not np.isfinite(values).all():
        raise DemandTrainingError(
            f"{split_name}: target contains NaN or infinite values."
        )

    negative_count = int(
        (values < 0).sum()
    )

    if negative_count:
        raise DemandTrainingError(
            f"{split_name}: target contains "
            f"{negative_count:,} negative values."
        )

    return values


def print_target_profile(
    target: np.ndarray,
    *,
    split_name: str,
) -> None:
    """Print demand sparsity information."""

    zero_rows = int(
        np.sum(target == 0)
    )

    positive_rows = int(
        np.sum(target > 0)
    )

    print()
    print(
        f"{split_name.upper()} TARGET PROFILE"
    )
    print(
        "-" * 78
    )
    print(
        f"rows                 : {len(target):,}"
    )
    print(
        f"zero-demand rows     : {zero_rows:,} "
        f"({zero_rows / len(target) * 100:.2f}%)"
    )
    print(
        f"positive-demand rows : {positive_rows:,} "
        f"({positive_rows / len(target) * 100:.2f}%)"
    )
    print(
        f"mean units           : {target.mean():.6f}"
    )
    print(
        f"total units          : {target.sum():,.0f}"
    )


def prediction_diagnostics(
    predictions: np.ndarray,
) -> dict[str, float | int]:
    """Return useful demand prediction statistics."""

    predictions = np.asarray(
        predictions,
        dtype=float,
    )

    return {
        "rows": int(len(predictions)),
        "minimum": float(predictions.min()),
        "maximum": float(predictions.max()),
        "mean": float(predictions.mean()),
        "median": float(np.median(predictions)),
        "predictions_below_zero": int(
            np.sum(predictions < 0)
        ),
        "predictions_below_0_01": int(
            np.sum(predictions < 0.01)
        ),
    }


def save_artifacts(
    *,
    pipeline: Pipeline,
    metrics: dict[str, float],
    diagnostics: dict[str, float | int],
    training_rows: int,
    validation_rows: int,
    numeric_columns: tuple[str, ...],
    categorical_columns: tuple[str, ...],
    elapsed_seconds: float,
) -> tuple[Path, Path]:
    """
    Save model and validation metadata.

    Generated artifacts are ignored by Git.
    """

    ensure_artifact_directories()

    MODEL_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    METRICS_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    joblib.dump(
        pipeline,
        MODEL_PATH,
    )

    model_wape = float(
        metrics["wape"]
    )

    improvement_points = (
        BASELINE_VALIDATION_WAPE
        - model_wape
    )

    relative_improvement_pct = (
        improvement_points
        / BASELINE_VALIDATION_WAPE
        * 100.0
    )

    payload = {
        "artifact_version": 1,
        "generated_at_utc": (
            datetime.now(
                timezone.utc
            ).isoformat()
        ),
        "task": TASK_NAME,
        "model": MODEL_NAME,
        "training_split": "train",
        "evaluation_split": "validation",
        "test_set_used": False,
        "training_rows": int(
            training_rows
        ),
        "validation_rows": int(
            validation_rows
        ),
        "predictor_count": (
            len(numeric_columns)
            + len(categorical_columns)
        ),
        "numeric_predictor_count": (
            len(numeric_columns)
        ),
        "categorical_predictor_count": (
            len(categorical_columns)
        ),
        "primary_metric": PRIMARY_METRIC,
        "metrics": {
            key: float(value)
            for key, value in metrics.items()
        },
        "prediction_diagnostics": diagnostics,
        "baseline": {
            "name": BASELINE_NAME,
            "validation_wape": (
                BASELINE_VALIDATION_WAPE
            ),
        },
        "comparison": {
            "beats_baseline": bool(
                model_wape
                < BASELINE_VALIDATION_WAPE
            ),
            "wape_improvement_points": float(
                improvement_points
            ),
            "relative_wape_improvement_pct": float(
                relative_improvement_pct
            ),
        },
        "training_seconds": float(
            elapsed_seconds
        ),
    }

    with METRICS_PATH.open(
        "w",
        encoding="utf-8",
    ) as handle:
        json.dump(
            payload,
            handle,
            indent=2,
        )
        handle.write(
            "\n"
        )

    return (
        MODEL_PATH,
        METRICS_PATH,
    )


# ======================================================================
# Main training workflow
# ======================================================================

def main() -> None:
    """
    Fit Poisson regression on train and evaluate on validation.

    TEST DATA IS NOT TOUCHED.
    """

    print()
    print(
        "=" * 88
    )
    print(
        "FulfillAI demand model: Poisson regression"
    )
    print(
        "=" * 88
    )

    dataset = load_train_validation_dataset(
        TASK_NAME
    )

    train = dataset.train
    validation = dataset.validation

    print()
    print(
        f"training rows     : {train.rows:,}"
    )
    print(
        f"validation rows   : {validation.rows:,}"
    )
    print(
        f"predictor count   : "
        f"{len(dataset.predictors):,}"
    )
    print(
        f"target            : "
        f"{dataset.task.target_column}"
    )
    print(
        "test partition    : LOCKED / NOT USED"
    )

    X_train = train.X
    X_validation = validation.X

    y_train = validate_target(
        train.y,
        split_name="train",
    )

    y_validation = validate_target(
        validation.y,
        split_name="validation",
    )

    print_target_profile(
        y_train,
        split_name="train",
    )

    print_target_profile(
        y_validation,
        split_name="validation",
    )

    # --------------------------------------------------------------
    # Feature schema comes exclusively from training data.
    # --------------------------------------------------------------

    schema = infer_feature_schema(
        X_train
    )

    print_feature_schema(
        schema
    )

    if schema.feature_count != len(
        dataset.predictors
    ):
        raise DemandTrainingError(
            "Feature-schema count differs from "
            "Phase 7 predictor contract."
        )

    # --------------------------------------------------------------
    # Build preprocessing + estimator.
    # --------------------------------------------------------------

    preprocessor = build_preprocessor(
        schema
    )

    model = PoissonRegressor(
        alpha=1.0,
        max_iter=2000,
        tol=1e-6,
    )

    pipeline = Pipeline(
        steps=[
            (
                "preprocessing",
                preprocessor,
            ),
            (
                "model",
                model,
            ),
        ]
    )

    # --------------------------------------------------------------
    # TRAIN ONLY
    # --------------------------------------------------------------

    print()
    print(
        "=" * 88
    )
    print(
        "TRAINING"
    )
    print(
        "=" * 88
    )

    print(
        "Fitting preprocessing on TRAIN only..."
    )

    print(
        "Fitting PoissonRegressor..."
    )

    start_time = time.perf_counter()

    pipeline.fit(
        X_train,
        y_train,
    )

    elapsed_seconds = (
        time.perf_counter()
        - start_time
    )

    print(
        f"training completed in "
        f"{elapsed_seconds:.2f} seconds ✓"
    )

    # --------------------------------------------------------------
    # VALIDATION ONLY
    # --------------------------------------------------------------

    print()
    print(
        "=" * 88
    )
    print(
        "VALIDATION EVALUATION"
    )
    print(
        "=" * 88
    )

    prediction = pipeline.predict(
        X_validation
    )

    prediction = np.asarray(
        prediction,
        dtype=float,
    )

    if not np.isfinite(
        prediction
    ).all():
        raise DemandTrainingError(
            "Model produced NaN or infinite predictions."
        )

    negative_predictions = int(
        np.sum(
            prediction < 0
        )
    )

    if negative_predictions:
        raise DemandTrainingError(
            "Poisson model produced "
            f"{negative_predictions:,} negative predictions."
        )

    metrics = forecasting_metrics(
        y_validation,
        prediction,
    )

    diagnostics = prediction_diagnostics(
        prediction
    )

    print()
    print(
        "POISSON VALIDATION METRICS"
    )
    print(
        "-" * 88
    )

    print(
        f"MAE    : {metrics['mae']:.6f}"
    )
    print(
        f"RMSE   : {metrics['rmse']:.6f}"
    )
    print(
        f"WAPE   : {metrics['wape']:.6f}%"
    )
    print(
        f"sMAPE  : {metrics['smape']:.6f}%"
    )

    print()
    print(
        "PREDICTION PROFILE"
    )
    print(
        "-" * 88
    )

    print(
        f"minimum       : "
        f"{diagnostics['minimum']:.6f}"
    )
    print(
        f"maximum       : "
        f"{diagnostics['maximum']:.6f}"
    )
    print(
        f"mean          : "
        f"{diagnostics['mean']:.6f}"
    )
    print(
        f"median        : "
        f"{diagnostics['median']:.6f}"
    )
    print(
        f"negative      : "
        f"{diagnostics['predictions_below_zero']:,}"
    )

    # --------------------------------------------------------------
    # Baseline comparison
    # --------------------------------------------------------------

    model_wape = float(
        metrics["wape"]
    )

    difference = (
        BASELINE_VALIDATION_WAPE
        - model_wape
    )

    relative_improvement = (
        difference
        / BASELINE_VALIDATION_WAPE
        * 100.0
    )

    print()
    print(
        "=" * 88
    )
    print(
        "BASELINE COMPARISON"
    )
    print(
        "=" * 88
    )

    print(
        f"{BASELINE_NAME:<24}: "
        f"{BASELINE_VALIDATION_WAPE:.6f}% WAPE"
    )

    print(
        f"{MODEL_NAME:<24}: "
        f"{model_wape:.6f}% WAPE"
    )

    print()

    if model_wape < (
        BASELINE_VALIDATION_WAPE
    ):
        print(
            "RESULT: MODEL BEATS BASELINE ✓"
        )

        print(
            f"WAPE improvement       : "
            f"{difference:.6f} percentage points"
        )

        print(
            f"relative improvement   : "
            f"{relative_improvement:.2f}%"
        )

    else:
        degradation = (
            model_wape
            - BASELINE_VALIDATION_WAPE
        )

        print(
            "RESULT: MODEL DOES NOT BEAT BASELINE"
        )

        print(
            f"WAPE worse by          : "
            f"{degradation:.6f} percentage points"
        )

        print(
            "This is still a valid experimental result."
        )

    # --------------------------------------------------------------
    # Persistence
    # --------------------------------------------------------------

    model_path, metrics_path = save_artifacts(
        pipeline=pipeline,
        metrics=metrics,
        diagnostics=diagnostics,
        training_rows=train.rows,
        validation_rows=validation.rows,
        numeric_columns=schema.numeric_columns,
        categorical_columns=schema.categorical_columns,
        elapsed_seconds=elapsed_seconds,
    )

    print()
    print(
        "ARTIFACTS"
    )
    print(
        "-" * 88
    )

    print(
        f"model   : {model_path}"
    )
    print(
        f"metrics : {metrics_path}"
    )
    print(
        "test set used : FALSE ✓"
    )

    print()
    print(
        "=" * 88
    )
    print(
        "POISSON DEMAND MODEL TRAINING PASSED ✓"
    )
    print(
        "=" * 88
    )


if __name__ == "__main__":
    main()