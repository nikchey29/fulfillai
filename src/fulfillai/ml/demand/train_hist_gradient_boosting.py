"""
FulfillAI Phase 8.8 leakage-safe nonlinear demand forecasting model.

Purpose
-------
Evaluate the new Phase 8.8 historical demand features with the SAME
HistGradientBoosting hyperparameters used by the earlier leakage-safe model.
That makes this run a controlled feature-engineering comparison rather than a
mixture of feature and hyperparameter changes.

Prediction-time contract
------------------------
Only information available BEFORE the forecasted day's demand occurs may enter
the model.

TRAIN      -> preprocessing + fitting
VALIDATION -> evaluation / model selection
TEST       -> completely untouched

Important
---------
The historical ~6.89% WAPE exploratory result is intentionally kept only as an
invalid diagnostic reference because that experiment used contemporaneous
same-day demand proxies and current inventory snapshot fields.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, OneHotEncoder

from ..config import METRIC_ROOT, MODEL_ROOT, ensure_artifact_directories
from ..data import load_task_dataset
from ..metrics import forecasting_metrics


# ============================================================================
# Experiment identity
# ============================================================================

TASK_NAME = "demand_forecasting"
MODEL_NAME = "hist_gradient_boosting_poisson_phase_8_8"
PRIMARY_METRIC = "wape"
PHASE = "8.8"


# ============================================================================
# Existing validation benchmarks
# ============================================================================

ROLLING_28_NAME = "rolling_28"
ROLLING_28_VALIDATION_WAPE = 88.27831765529037

PRE_PHASE_8_8_HGB_NAME = "hist_gradient_boosting_poisson_leakage_safe"
PRE_PHASE_8_8_HGB_VALIDATION_WAPE = 88.417854

POISSON_MODEL_NAME = "poisson_regression"
POISSON_VALIDATION_WAPE = 119.629731

LEAKED_EXPERIMENT_NAME = "hist_gradient_boosting_poisson_leaked"
LEAKED_EXPERIMENT_WAPE = 6.889747


# ============================================================================
# Artifacts — do not overwrite the pre-Phase-8.8 model
# ============================================================================

MODEL_PATH = (
    MODEL_ROOT
    / "demand"
    / "hist_gradient_boosting_poisson_phase_8_8.joblib"
)

METRICS_PATH = (
    METRIC_ROOT
    / "demand_hist_gradient_boosting_phase_8_8_validation.json"
)


# ============================================================================
# Strict Phase 8.8 prediction-time feature contract
# ============================================================================

SAFE_CATEGORICAL_COLUMNS = (
    "warehouse_code",
    "sku",
    "category_name",
)


SAFE_NUMERIC_COLUMNS = (
    # Calendar information known before prediction.
    "demand_year",
    "demand_month_number",
    "day_of_week",
    "day_of_year",
    "is_weekend",

    # Static catalog information.
    "catalog_unit_price",
    "catalog_unit_cost",
    "weight_kg",
    "catalog_unit_margin",
    "catalog_margin_pct",

    # Original historical lags.
    "lag_1_units",
    "lag_7_units",
    "lag_14_units",
    "lag_28_units",

    # Original historical rolling windows.
    # SQL audit verified these terminate at 1 PRECEDING.
    "rolling_7d_units",
    "rolling_7d_avg_units",
    "rolling_28d_units",
    "rolling_28d_avg_units",
    "rolling_7d_orders",
    "rolling_7d_revenue",

    # --------------------------------------------------------------------
    # Phase 8.8: stronger leakage-safe historical demand signals.
    # --------------------------------------------------------------------

    # Additional lags.
    "lag_21_units",
    "lag_35_units",

    # Window coverage / activity.
    "rolling_7d_observation_days",
    "rolling_28d_observation_days",
    "nonzero_days_last_7d",
    "nonzero_days_last_28d",

    # Volatility.
    "rolling_7d_std_units",
    "rolling_28d_std_units",

    # Recent vs prior history.
    "prior_7d_avg_units",

    # Longer-window operational history.
    "rolling_28d_orders",
    "rolling_28d_revenue",

    # Expanding historical behavior.
    "historical_observation_days",
    "historical_nonzero_days",
    "historical_avg_units",
    "historical_nonzero_avg_units",

    # Same-weekday history.
    "same_weekday_historical_observation_days",
    "same_weekday_historical_nonzero_days",
    "same_weekday_historical_avg_units",

    # Demand frequency / probability.
    "demand_frequency_7d",
    "demand_frequency_28d",
    "historical_sale_probability",
    "same_weekday_sale_probability",

    # Intermittency / recency.
    "days_since_last_positive_demand",
    "zero_demand_streak",

    # Trend / dispersion / acceleration.
    "coefficient_of_variation_28d",
    "recent_mean_minus_long_mean",
    "recent_7d_vs_28d_ratio",
    "demand_acceleration_7d",
    "recent_vs_prior_7d_ratio",
)


PHASE_8_8_ADDED_SAFE_COLUMNS = (
    "lag_21_units",
    "lag_35_units",
    "rolling_7d_observation_days",
    "rolling_28d_observation_days",
    "nonzero_days_last_7d",
    "nonzero_days_last_28d",
    "rolling_7d_std_units",
    "rolling_28d_std_units",
    "prior_7d_avg_units",
    "rolling_28d_orders",
    "rolling_28d_revenue",
    "historical_observation_days",
    "historical_nonzero_days",
    "historical_avg_units",
    "historical_nonzero_avg_units",
    "same_weekday_historical_observation_days",
    "same_weekday_historical_nonzero_days",
    "same_weekday_historical_avg_units",
    "demand_frequency_7d",
    "demand_frequency_28d",
    "historical_sale_probability",
    "same_weekday_sale_probability",
    "days_since_last_positive_demand",
    "zero_demand_streak",
    "coefficient_of_variation_28d",
    "recent_mean_minus_long_mean",
    "recent_7d_vs_28d_ratio",
    "demand_acceleration_7d",
    "recent_vs_prior_7d_ratio",
)


# These eight columns are present in the 60-column Phase 8.8 predictor dataset,
# but are intentionally not fed to the model.
INTENTIONALLY_UNUSED_PREDICTORS = (
    # Redundant calendar labels.
    "demand_week",
    "demand_month",

    # Human-readable / duplicate identity columns.
    "warehouse_name",
    "warehouse_city",
    "warehouse_country_code",
    "product_name",
    "category_id",

    # Historical and prediction-time safe, but raw date encoding is not useful
    # here because the model already receives days_since_last_positive_demand.
    "last_positive_demand_date",
)


SAFE_COLUMNS = (
    *SAFE_CATEGORICAL_COLUMNS,
    *SAFE_NUMERIC_COLUMNS,
)

EXPECTED_PHASE_8_8_PREDICTORS = (
    *SAFE_COLUMNS,
    *INTENTIONALLY_UNUSED_PREDICTORS,
)


# These fields should not appear in demand_forecasting X at all.  They are kept
# as explicit fail-fast guards in case a later feature-config change exposes
# them again.
SAME_DAY_LEAKAGE_COLUMNS = (
    "gross_order_count",
    "gross_requested_value",
    "order_count",
    "cancelled_order_count",
    "avg_selling_price",
    "gross_units_requested",
    "cancelled_units",
    "revenue",
)

CURRENT_SNAPSHOT_COLUMNS = (
    "snapshot_on_hand_qty",
    "snapshot_reserved_qty",
    "snapshot_reorder_point",
)

STRICTLY_FORBIDDEN_COLUMNS = (
    *SAME_DAY_LEAKAGE_COLUMNS,
    *CURRENT_SNAPSHOT_COLUMNS,
)


# ============================================================================
# Errors
# ============================================================================


class DemandTrainingError(RuntimeError):
    """Raised when Phase 8.8 demand training cannot continue safely."""


# ============================================================================
# Data conversion
# ============================================================================


def _to_numeric_matrix(frame: pd.DataFrame) -> np.ndarray:
    """Convert PostgreSQL numeric/Decimal-like columns to float32."""

    if not isinstance(frame, pd.DataFrame):
        frame = pd.DataFrame(frame)

    converted = frame.apply(pd.to_numeric, errors="coerce")
    return converted.to_numpy(dtype=np.float32)


def _as_float32(matrix: np.ndarray) -> np.ndarray:
    """Reduce histogram-training memory usage."""

    return np.asarray(matrix, dtype=np.float32)


# ============================================================================
# Feature-contract validation
# ============================================================================


def validate_feature_contract(
    frame: pd.DataFrame,
    *,
    split_name: str,
) -> None:
    """
    Enforce the exact Phase 8.8 predictor contract.

    The model uses an explicit allowlist.  Any newly introduced source column
    must be reviewed before it is allowed into training.
    """

    source_columns = tuple(frame.columns)
    source_set = set(source_columns)
    expected_set = set(EXPECTED_PHASE_8_8_PREDICTORS)

    duplicates = frame.columns[frame.columns.duplicated()].tolist()
    if duplicates:
        raise DemandTrainingError(
            f"{split_name}: duplicate predictor columns detected: {duplicates}"
        )

    missing = sorted(expected_set - source_set)
    unexpected = sorted(source_set - expected_set)

    if missing:
        raise DemandTrainingError(
            f"{split_name}: expected Phase 8.8 predictors are missing: {missing}"
        )

    if unexpected:
        raise DemandTrainingError(
            f"{split_name}: unreviewed predictors reached the model dataset: "
            f"{unexpected}"
        )

    forbidden_present = sorted(source_set & set(STRICTLY_FORBIDDEN_COLUMNS))
    if forbidden_present:
        raise DemandTrainingError(
            f"{split_name}: leakage/snapshot fields reached X: "
            f"{forbidden_present}"
        )

    overlap = set(SAFE_COLUMNS) & set(INTENTIONALLY_UNUSED_PREDICTORS)
    if overlap:
        raise DemandTrainingError(
            "Feature contract bug: safe and intentionally-unused predictors "
            f"overlap: {sorted(overlap)}"
        )

    if len(SAFE_COLUMNS) != len(set(SAFE_COLUMNS)):
        raise DemandTrainingError("SAFE_COLUMNS contains duplicate names.")

    if len(EXPECTED_PHASE_8_8_PREDICTORS) != 60:
        raise DemandTrainingError(
            "Phase 8.8 contract must describe exactly 60 source predictors; "
            f"found {len(EXPECTED_PHASE_8_8_PREDICTORS)}."
        )

    if len(SAFE_COLUMNS) != 52:
        raise DemandTrainingError(
            "Phase 8.8 safe allowlist must contain exactly 52 predictors; "
            f"found {len(SAFE_COLUMNS)}."
        )

    if not set(PHASE_8_8_ADDED_SAFE_COLUMNS).issubset(set(SAFE_COLUMNS)):
        raise DemandTrainingError(
            "Phase 8.8 added-feature list is not a subset of SAFE_COLUMNS."
        )

    for column in SAFE_NUMERIC_COLUMNS:
        original = frame[column]
        converted = pd.to_numeric(original, errors="coerce")

        invalid = original.notna() & converted.isna()
        if bool(invalid.any()):
            examples = original.loc[invalid].astype(str).head(5).tolist()
            raise DemandTrainingError(
                f"{split_name}: {column!r} contains unexpected non-numeric "
                f"values: {examples}"
            )


def select_safe_features(
    frame: pd.DataFrame,
    *,
    split_name: str,
) -> pd.DataFrame:
    """Return only the explicit prediction-time-safe Phase 8.8 columns."""

    validate_feature_contract(frame, split_name=split_name)

    result = frame.loc[:, list(SAFE_COLUMNS)].copy()

    if tuple(result.columns) != SAFE_COLUMNS:
        raise DemandTrainingError(
            f"{split_name}: safe feature ordering changed unexpectedly."
        )

    return result


# ============================================================================
# Target
# ============================================================================


def validate_target(
    target: pd.Series,
    *,
    split_name: str,
) -> np.ndarray:
    """Validate non-negative finite count target."""

    values = pd.to_numeric(target, errors="raise").to_numpy(dtype=float)

    if not np.isfinite(values).all():
        raise DemandTrainingError(
            f"{split_name}: target contains NaN or infinite values."
        )

    negative = int(np.sum(values < 0))
    if negative:
        raise DemandTrainingError(
            f"{split_name}: target contains {negative:,} negative values."
        )

    return values


# ============================================================================
# Preprocessing
# ============================================================================


def build_preprocessor() -> ColumnTransformer:
    """
    Build HGB-specific preprocessing using only safe predictors.

    Numeric values:
        PostgreSQL numeric/Decimal -> float32 -> median imputation

    Categorical values:
        most-frequent imputation -> one-hot encoding

    Scaling is unnecessary for a tree-based estimator.
    """

    numeric_pipeline = Pipeline(
        steps=[
            (
                "numeric_cast",
                FunctionTransformer(
                    _to_numeric_matrix,
                    validate=False,
                    feature_names_out="one-to-one",
                ),
            ),
            (
                "imputer",
                SimpleImputer(strategy="median"),
            ),
        ]
    )

    categorical_pipeline = Pipeline(
        steps=[
            (
                "imputer",
                SimpleImputer(strategy="most_frequent"),
            ),
            (
                "one_hot",
                OneHotEncoder(
                    handle_unknown="ignore",
                    sparse_output=False,
                    dtype=np.float32,
                ),
            ),
        ]
    )

    return ColumnTransformer(
        transformers=[
            (
                "numeric",
                numeric_pipeline,
                list(SAFE_NUMERIC_COLUMNS),
            ),
            (
                "categorical",
                categorical_pipeline,
                list(SAFE_CATEGORICAL_COLUMNS),
            ),
        ],
        remainder="drop",
        sparse_threshold=0.0,
    )


# ============================================================================
# Prediction diagnostics
# ============================================================================


def prediction_diagnostics(predictions: np.ndarray) -> dict[str, float | int]:
    values = np.asarray(predictions, dtype=float)

    return {
        "rows": int(len(values)),
        "minimum": float(values.min()),
        "maximum": float(values.max()),
        "mean": float(values.mean()),
        "median": float(np.median(values)),
        "predictions_below_zero": int(np.sum(values < 0)),
        "predictions_below_0_01": int(np.sum(values < 0.01)),
    }


# ============================================================================
# Artifact persistence
# ============================================================================


def save_artifacts(
    *,
    pipeline: Pipeline,
    metrics: dict[str, float],
    diagnostics: dict[str, float | int],
    training_rows: int,
    validation_rows: int,
    source_predictor_count: int,
    encoded_feature_count: int,
    elapsed_seconds: float,
) -> tuple[Path, Path]:
    ensure_artifact_directories()

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    METRICS_PATH.parent.mkdir(parents=True, exist_ok=True)

    joblib.dump(pipeline, MODEL_PATH)

    model_wape = float(metrics["wape"])

    rolling_improvement_points = (
        ROLLING_28_VALIDATION_WAPE - model_wape
    )
    old_hgb_improvement_points = (
        PRE_PHASE_8_8_HGB_VALIDATION_WAPE - model_wape
    )

    payload = {
        "artifact_version": 1,
        "phase": PHASE,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "task": TASK_NAME,
        "model": MODEL_NAME,
        "training_split": "train",
        "evaluation_split": "validation",
        "test_set_used": False,
        "training_rows": int(training_rows),
        "validation_rows": int(validation_rows),
        "source_predictor_count": int(source_predictor_count),
        "safe_predictor_count": len(SAFE_COLUMNS),
        "phase_8_8_added_safe_predictor_count": len(
            PHASE_8_8_ADDED_SAFE_COLUMNS
        ),
        "encoded_feature_count": int(encoded_feature_count),
        "prediction_time_contract": {
            "safe_categorical_predictors": list(SAFE_CATEGORICAL_COLUMNS),
            "safe_numeric_predictors": list(SAFE_NUMERIC_COLUMNS),
            "phase_8_8_added_safe_predictors": list(
                PHASE_8_8_ADDED_SAFE_COLUMNS
            ),
            "intentionally_unused_predictors": list(
                INTENTIONALLY_UNUSED_PREDICTORS
            ),
            "same_day_leakage_excluded": list(SAME_DAY_LEAKAGE_COLUMNS),
            "current_snapshot_columns_excluded": list(
                CURRENT_SNAPSHOT_COLUMNS
            ),
            "rolling_windows_verified_to_end_at": "1 PRECEDING",
            "raw_last_positive_demand_date_used": False,
        },
        "model_parameters": {
            "loss": "poisson",
            "learning_rate": 0.06,
            "max_iter": 200,
            "max_leaf_nodes": 31,
            "min_samples_leaf": 100,
            "l2_regularization": 1.0,
            "max_bins": 255,
            "early_stopping": False,
            "random_state": 42,
        },
        "experiment_design": {
            "purpose": (
                "Controlled Phase 8.8 feature ablation using the same HGB "
                "hyperparameters as the pre-Phase-8.8 leakage-safe model."
            ),
            "hyperparameters_changed_vs_pre_phase_8_8_hgb": False,
        },
        "primary_metric": PRIMARY_METRIC,
        "metrics": {key: float(value) for key, value in metrics.items()},
        "prediction_diagnostics": diagnostics,
        "benchmarks": {
            ROLLING_28_NAME: {
                "validation_wape": ROLLING_28_VALIDATION_WAPE,
                "valid_forecasting_result": True,
            },
            PRE_PHASE_8_8_HGB_NAME: {
                "validation_wape": PRE_PHASE_8_8_HGB_VALIDATION_WAPE,
                "valid_forecasting_result": True,
            },
            POISSON_MODEL_NAME: {
                "validation_wape": POISSON_VALIDATION_WAPE,
                "valid_forecasting_result": True,
            },
            LEAKED_EXPERIMENT_NAME: {
                "validation_wape": LEAKED_EXPERIMENT_WAPE,
                "valid_forecasting_result": False,
                "reason": (
                    "Contemporaneous demand proxies and current inventory "
                    "snapshot fields."
                ),
            },
        },
        "comparison_to_rolling_28": {
            "beats_baseline": bool(
                model_wape < ROLLING_28_VALIDATION_WAPE
            ),
            "wape_improvement_points": float(rolling_improvement_points),
            "relative_wape_improvement_pct": float(
                rolling_improvement_points
                / ROLLING_28_VALIDATION_WAPE
                * 100.0
            ),
        },
        "comparison_to_pre_phase_8_8_hgb": {
            "beats_previous_hgb": bool(
                model_wape < PRE_PHASE_8_8_HGB_VALIDATION_WAPE
            ),
            "wape_improvement_points": float(old_hgb_improvement_points),
            "relative_wape_improvement_pct": float(
                old_hgb_improvement_points
                / PRE_PHASE_8_8_HGB_VALIDATION_WAPE
                * 100.0
            ),
        },
        "training_seconds": float(elapsed_seconds),
    }

    with METRICS_PATH.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")

    return MODEL_PATH, METRICS_PATH


# ============================================================================
# Reporting helpers
# ============================================================================


def print_validation_leaderboard(model_wape: float) -> None:
    """Print valid validation results sorted by WAPE."""

    valid_results = [
        (ROLLING_28_NAME, ROLLING_28_VALIDATION_WAPE),
        (PRE_PHASE_8_8_HGB_NAME, PRE_PHASE_8_8_HGB_VALIDATION_WAPE),
        (POISSON_MODEL_NAME, POISSON_VALIDATION_WAPE),
        (MODEL_NAME, model_wape),
    ]

    valid_results.sort(key=lambda item: item[1])

    print()
    print("=" * 88)
    print("VALIDATION LEADERBOARD — VALID RESULTS ONLY")
    print("=" * 88)

    for rank, (name, wape) in enumerate(valid_results, start=1):
        print(f"{rank:>2}. {name:<48}{wape:>12.6f}% WAPE")

    print()
    print("INVALID EXPLORATORY SCORE — NOT A LEADERBOARD ENTRY")
    print("-" * 88)
    print(
        f"{LEAKED_EXPERIMENT_NAME:<52}"
        f"{LEAKED_EXPERIMENT_WAPE:>12.6f}% WAPE"
    )
    print(
        "Reason: contemporaneous target proxies + current inventory snapshot."
    )


# ============================================================================
# Main experiment
# ============================================================================


def main() -> None:
    """Train and validate the Phase 8.8 leakage-safe HGB demand model."""

    print()
    print("=" * 88)
    print("FulfillAI Phase 8.8 demand model: Leakage-Safe HistGradientBoosting")
    print("=" * 88)

    dataset = load_task_dataset(TASK_NAME)

    train = dataset.train
    validation = dataset.validation

    # Deliberately do not access dataset.test.

    print()
    print(f"training rows                     : {train.rows:,}")
    print(f"validation rows                   : {validation.rows:,}")
    print(f"Phase 8.8 source predictor count  : {len(dataset.predictors):,}")
    print(f"safe predictor count              : {len(SAFE_COLUMNS):,}")
    print(
        "Phase 8.8 added safe predictors : "
        f"{len(PHASE_8_8_ADDED_SAFE_COLUMNS):,}"
    )
    print(
        "intentionally unused predictors : "
        f"{len(INTENTIONALLY_UNUSED_PREDICTORS):,}"
    )
    print(f"target                            : {dataset.task.target_column}")
    print("test partition                    : LOCKED / NOT USED")

    if len(dataset.predictors) != 60:
        raise DemandTrainingError(
            "Expected the rebuilt Phase 8.8 demand dataset to contain 60 "
            f"predictors; found {len(dataset.predictors)}."
        )

    X_train = select_safe_features(train.X, split_name="train")
    X_validation = select_safe_features(
        validation.X,
        split_name="validation",
    )

    y_train = validate_target(train.y, split_name="train")
    y_validation = validate_target(validation.y, split_name="validation")

    print()
    print("=" * 88)
    print("PHASE 8.8 PREDICTION-TIME FEATURE CONTRACT")
    print("=" * 88)

    print()
    print("SAFE CATEGORICAL FEATURES")
    for column in SAFE_CATEGORICAL_COLUMNS:
        cardinality = int(X_train[column].nunique(dropna=False))
        print(f"  {column:<40}{cardinality:>8,} categories")

    print()
    print("PHASE 8.8 ADDED SAFE HISTORICAL FEATURES")
    for column in PHASE_8_8_ADDED_SAFE_COLUMNS:
        print(f"  {column}")

    print()
    print("INTENTIONALLY UNUSED SOURCE PREDICTORS")
    for column in INTENTIONALLY_UNUSED_PREDICTORS:
        print(f"  {column}")

    print()
    print("same-day leakage fields present in X : 0 ✓")
    print("current snapshot fields present in X : 0 ✓")
    print("rolling windows include day t        : NO ✓")
    print("raw last_positive_demand_date used    : NO ✓")
    print("test partition accessed               : NO ✓")

    preprocessor = build_preprocessor()

    # IMPORTANT: these are intentionally the SAME hyperparameters as the
    # earlier leakage-safe HGB experiment.  Phase 8.8 is therefore a clean
    # feature-engineering comparison first; tuning comes only after this run.
    model = HistGradientBoostingRegressor(
        loss="poisson",
        learning_rate=0.06,
        max_iter=200,
        max_leaf_nodes=31,
        min_samples_leaf=100,
        l2_regularization=1.0,
        max_bins=255,
        early_stopping=False,
        random_state=42,
        verbose=1,
    )

    pipeline = Pipeline(
        steps=[
            ("preprocessing", preprocessor),
            (
                "float32",
                FunctionTransformer(
                    _as_float32,
                    validate=False,
                ),
            ),
            ("model", model),
        ]
    )

    print()
    print("=" * 88)
    print("TRAINING — TRAIN SPLIT ONLY")
    print("=" * 88)
    print("Fitting preprocessing on TRAIN only...")
    print("Fitting Phase 8.8 leakage-safe HistGradientBoostingRegressor...")

    started = time.perf_counter()
    pipeline.fit(X_train, y_train)
    elapsed_seconds = time.perf_counter() - started

    print()
    print(f"training completed in {elapsed_seconds:.2f} seconds ✓")

    encoded_feature_count = int(
        pipeline.named_steps["preprocessing"]
        .transform(X_train.iloc[:1])
        .shape[1]
    )

    print(f"encoded feature count      : {encoded_feature_count:,}")

    print()
    print("=" * 88)
    print("VALIDATION EVALUATION — VALIDATION SPLIT ONLY")
    print("=" * 88)

    prediction = pipeline.predict(X_validation)
    prediction = np.asarray(prediction, dtype=float)

    if not np.isfinite(prediction).all():
        raise DemandTrainingError(
            "Model produced NaN or infinite validation predictions."
        )

    negative_predictions = int(np.sum(prediction < 0))
    if negative_predictions:
        raise DemandTrainingError(
            "Poisson-loss model produced "
            f"{negative_predictions:,} negative predictions."
        )

    metrics = forecasting_metrics(y_validation, prediction)
    diagnostics = prediction_diagnostics(prediction)

    print()
    print("PHASE 8.8 LEAKAGE-SAFE HGB VALIDATION METRICS")
    print("-" * 88)
    print(f"MAE    : {metrics['mae']:.6f}")
    print(f"RMSE   : {metrics['rmse']:.6f}")
    print(f"WAPE   : {metrics['wape']:.6f}%")
    print(f"sMAPE  : {metrics['smape']:.6f}%")

    print()
    print("PREDICTION PROFILE")
    print("-" * 88)
    print(f"minimum       : {diagnostics['minimum']:.6f}")
    print(f"maximum       : {diagnostics['maximum']:.6f}")
    print(f"mean          : {diagnostics['mean']:.6f}")
    print(f"median        : {diagnostics['median']:.6f}")
    print(f"negative      : {diagnostics['predictions_below_zero']:,}")
    print(f"below 0.01    : {diagnostics['predictions_below_0_01']:,}")

    model_wape = float(metrics["wape"])
    print_validation_leaderboard(model_wape)

    rolling_delta = ROLLING_28_VALIDATION_WAPE - model_wape
    old_hgb_delta = PRE_PHASE_8_8_HGB_VALIDATION_WAPE - model_wape

    print()
    print("=" * 88)
    print("PHASE 8.8 CONTROLLED FEATURE COMPARISON")
    print("=" * 88)
    print(
        f"rolling_28 benchmark              : "
        f"{ROLLING_28_VALIDATION_WAPE:.6f}% WAPE"
    )
    print(
        f"pre-Phase-8.8 leakage-safe HGB    : "
        f"{PRE_PHASE_8_8_HGB_VALIDATION_WAPE:.6f}% WAPE"
    )
    print(f"Phase 8.8 HGB                     : {model_wape:.6f}% WAPE")
    print()
    print(
        f"delta vs rolling_28               : {rolling_delta:+.6f} points"
    )
    print(
        f"delta vs pre-Phase-8.8 HGB        : {old_hgb_delta:+.6f} points"
    )

    if model_wape < ROLLING_28_VALIDATION_WAPE:
        print("RESULT: PHASE 8.8 MODEL BEATS ROLLING_28 ✓")
    else:
        print("RESULT: PHASE 8.8 MODEL DOES NOT BEAT ROLLING_28")

    if model_wape < PRE_PHASE_8_8_HGB_VALIDATION_WAPE:
        print("FEATURE RESULT: PHASE 8.8 IMPROVES THE SAME HGB MODEL ✓")
    else:
        print("FEATURE RESULT: PHASE 8.8 DOES NOT IMPROVE THE SAME HGB MODEL")

    model_path, metrics_path = save_artifacts(
        pipeline=pipeline,
        metrics=metrics,
        diagnostics=diagnostics,
        training_rows=train.rows,
        validation_rows=validation.rows,
        source_predictor_count=len(dataset.predictors),
        encoded_feature_count=encoded_feature_count,
        elapsed_seconds=elapsed_seconds,
    )

    print()
    print("=" * 88)
    print("ARTIFACTS")
    print("=" * 88)
    print(f"model   : {model_path}")
    print(f"metrics : {metrics_path}")

    print()
    print("same-day leakage columns used     : 0 ✓")
    print("current snapshot columns used     : 0 ✓")
    print("rolling windows include day t     : NO ✓")
    print("Phase 8.8 historical features used: YES ✓")
    print("test set used                     : FALSE ✓")

    print()
    print("=" * 88)
    print("PHASE 8.8 LEAKAGE-SAFE HGB TRAINING PASSED ✓")
    print("=" * 88)


if __name__ == "__main__":
    main()
