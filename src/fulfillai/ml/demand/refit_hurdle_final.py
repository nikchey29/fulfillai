"""
FulfillAI — Phase 8.15
Final hurdle-model refit before the one-time test evaluation.

Scientific protocol
-------------------
The model architecture has already been selected and validated.

Frozen before this script:
- predictor contract
- preprocessing architecture
- occurrence-model architecture/hyperparameters
- magnitude-model architecture/hyperparameters
- hurdle threshold = 0.925
- primary metric = WAPE

This script:

    train.parquet
          +
    validation.parquet
          |
          v
    final fitting population
          |
          v
    refit frozen preprocessing
          |
          v
    refit occurrence classifier
          |
          v
    refit magnitude model on positive-demand rows only
          |
          v
    save final Phase 8.15 bundle

The test partition is NEVER read here.
"""

from __future__ import annotations

import json
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.base import clone

from src.fulfillai.ml.demand.train_hist_gradient_boosting import (
    validate_target,
)


# =============================================================================
# Project paths
# =============================================================================

PROJECT_ROOT = Path(__file__).resolve().parents[4]

FEATURE_ROOT = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "features"
    / "demand_forecasting"
)

TRAIN_PATH = FEATURE_ROOT / "train.parquet"

VALIDATION_PATH = (
    FEATURE_ROOT
    / "validation.parquet"
)

TEST_PATH = (
    FEATURE_ROOT
    / "test.parquet"
)


PHASE_8_13_MODEL_PATH = (
    PROJECT_ROOT
    / "artifacts"
    / "models"
    / "demand"
    / "hurdle_phase_8_13.joblib"
)

FINAL_MODEL_PATH = (
    PROJECT_ROOT
    / "artifacts"
    / "models"
    / "demand"
    / "hurdle_phase_8_15_final.joblib"
)

FINAL_METADATA_PATH = (
    PROJECT_ROOT
    / "artifacts"
    / "metrics"
    / "demand"
    / "hurdle_phase_8_15_final_refit.json"
)

FINAL_CONTRACT_PATH = (
    PROJECT_ROOT
    / "artifacts"
    / "experiments"
    / "demand"
    / "hurdle_phase_8_15_contract.json"
)


# =============================================================================
# Frozen Phase 8 decision
# =============================================================================

TARGET_COLUMN = "units_sold"

DATE_COLUMN = "demand_date"

EXPECTED_THRESHOLD = 0.925

EXPECTED_TRAIN_ROWS = 284_193

EXPECTED_VALIDATION_ROWS = 32_271

EXPECTED_FINAL_ROWS = (
    EXPECTED_TRAIN_ROWS
    + EXPECTED_VALIDATION_ROWS
)


# =============================================================================
# Helpers
# =============================================================================

def header(title: str) -> None:
    print()
    print("=" * 100)
    print(title)
    print("=" * 100)


def utc_now() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat()


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
        f"Cannot serialize object of type "
        f"{type(value)!r}"
    )


def load_partition(
    path: Path,
    name: str,
) -> pd.DataFrame:

    if not path.exists():
        raise FileNotFoundError(
            f"{name} partition not found: {path}"
        )

    frame = pd.read_parquet(
        path
    )

    if frame.empty:
        raise RuntimeError(
            f"{name} partition is empty."
        )

    if DATE_COLUMN not in frame.columns:
        raise RuntimeError(
            f"{name}: missing "
            f"{DATE_COLUMN!r}."
        )

    if TARGET_COLUMN not in frame.columns:
        raise RuntimeError(
            f"{name}: missing "
            f"{TARGET_COLUMN!r}."
        )

    frame = frame.copy()

    frame[DATE_COLUMN] = pd.to_datetime(
        frame[DATE_COLUMN],
        errors="raise",
    ).dt.normalize()

    frame = frame.sort_values(
        DATE_COLUMN,
        kind="mergesort",
    ).reset_index(
        drop=True
    )

    return frame


# =============================================================================
# Main
# =============================================================================

def main() -> None:

    header(
        "FULFILLAI PHASE 8.15 — FINAL HURDLE REFIT"
    )

    print(
        "architecture               : FROZEN"
    )

    print(
        "hyperparameters             : FROZEN"
    )

    print(
        "feature contract            : FROZEN"
    )

    print(
        "primary metric              : WAPE"
    )

    print(
        f"hurdle threshold            : "
        f"{EXPECTED_THRESHOLD:.3f} 🔒"
    )

    print(
        "test evaluation allowed     : NO"
    )

    print(
        "test partition              : LOCKED 🔒"
    )


    # =========================================================================
    # Load the frozen Phase 8.13 bundle.
    #
    # This is deliberately used as the source of truth for the exact estimator
    # and preprocessing configurations so Phase 8.15 does not silently invent
    # a different model.
    # =========================================================================

    header(
        "LOADING FROZEN PHASE 8.13 CONTRACT"
    )

    if not PHASE_8_13_MODEL_PATH.exists():
        raise FileNotFoundError(
            "Missing Phase 8.13 model artifact: "
            f"{PHASE_8_13_MODEL_PATH}"
        )

    frozen_bundle = joblib.load(
        PHASE_8_13_MODEL_PATH
    )

    required_bundle_keys = {
        "threshold",
        "safe_predictors",
        "preprocessor",
        "occurrence_model",
        "magnitude_model",
        "contract",
    }

    missing_bundle_keys = sorted(
        required_bundle_keys
        - set(frozen_bundle)
    )

    if missing_bundle_keys:
        raise RuntimeError(
            "Phase 8.13 bundle is missing "
            f"required keys: "
            f"{missing_bundle_keys}"
        )


    threshold = float(
        frozen_bundle["threshold"]
    )

    if not np.isclose(
        threshold,
        EXPECTED_THRESHOLD,
    ):
        raise RuntimeError(
            "Frozen threshold changed unexpectedly. "
            f"Expected {EXPECTED_THRESHOLD}, "
            f"found {threshold}."
        )


    safe_predictors = list(
        frozen_bundle[
            "safe_predictors"
        ]
    )

    if not safe_predictors:
        raise RuntimeError(
            "Frozen predictor contract is empty."
        )


    original_preprocessor = (
        frozen_bundle[
            "preprocessor"
        ]
    )

    original_occurrence_model = (
        frozen_bundle[
            "occurrence_model"
        ]
    )

    original_magnitude_model = (
        frozen_bundle[
            "magnitude_model"
        ]
    )

    frozen_contract = (
        frozen_bundle[
            "contract"
        ]
    )


    print(
        f"source model               : "
        f"{PHASE_8_13_MODEL_PATH}"
    )

    print(
        f"safe predictor count       : "
        f"{len(safe_predictors)}"
    )

    print(
        f"frozen threshold           : "
        f"{threshold:.3f}"
    )

    print(
        "threshold retuned          : NO"
    )

    print(
        "hyperparameters changed    : NO"
    )


    # =========================================================================
    # Read fitting partitions.
    #
    # NOTICE:
    # Only TRAIN and VALIDATION are read here.
    # TEST is intentionally never passed to pandas.
    # =========================================================================

    header(
        "READING FINAL FITTING PARTITIONS"
    )

    train = load_partition(
        TRAIN_PATH,
        "train",
    )

    validation = load_partition(
        VALIDATION_PATH,
        "validation",
    )


    print(
        f"train rows                 : "
        f"{len(train):,}"
    )

    print(
        f"train range                : "
        f"{train[DATE_COLUMN].min().date()} "
        f"-> "
        f"{train[DATE_COLUMN].max().date()}"
    )

    print()

    print(
        f"validation rows            : "
        f"{len(validation):,}"
    )

    print(
        f"validation range           : "
        f"{validation[DATE_COLUMN].min().date()} "
        f"-> "
        f"{validation[DATE_COLUMN].max().date()}"
    )

    print()

    print(
        "test.parquet read          : NO 🔒"
    )


    # =========================================================================
    # Integrity checks
    # =========================================================================

    header(
        "FINAL REFIT INTEGRITY CHECKS"
    )


    if len(train) != EXPECTED_TRAIN_ROWS:
        raise RuntimeError(
            "Unexpected train row count. "
            f"Expected {EXPECTED_TRAIN_ROWS:,}, "
            f"found {len(train):,}."
        )


    if (
        len(validation)
        != EXPECTED_VALIDATION_ROWS
    ):
        raise RuntimeError(
            "Unexpected validation row count. "
            f"Expected "
            f"{EXPECTED_VALIDATION_ROWS:,}, "
            f"found {len(validation):,}."
        )


    if (
        train[DATE_COLUMN].max()
        >= validation[DATE_COLUMN].min()
    ):
        raise RuntimeError(
            "Train/validation chronology "
            "is invalid."
        )


    missing_train_predictors = sorted(
        set(safe_predictors)
        - set(train.columns)
    )

    missing_validation_predictors = sorted(
        set(safe_predictors)
        - set(validation.columns)
    )


    if missing_train_predictors:
        raise RuntimeError(
            "TRAIN is missing frozen "
            "predictors: "
            f"{missing_train_predictors}"
        )


    if missing_validation_predictors:
        raise RuntimeError(
            "VALIDATION is missing frozen "
            "predictors: "
            f"{missing_validation_predictors}"
        )


    print(
        "train row count            : PASSED ✓"
    )

    print(
        "validation row count       : PASSED ✓"
    )

    print(
        "chronological separation   : PASSED ✓"
    )

    print(
        "train feature contract     : PASSED ✓"
    )

    print(
        "validation feature contract: PASSED ✓"
    )


    # =========================================================================
    # Combine TRAIN + VALIDATION.
    #
    # Validation is no longer being used for tuning. All architecture choices
    # were frozen before reaching this phase.
    # =========================================================================

    header(
        "BUILDING FINAL FITTING POPULATION"
    )

    final_frame = pd.concat(
        [
            train,
            validation,
        ],
        axis=0,
        ignore_index=True,
    )

    final_frame = (
        final_frame
        .sort_values(
            DATE_COLUMN,
            kind="mergesort",
        )
        .reset_index(
            drop=True
        )
    )


    if len(final_frame) != EXPECTED_FINAL_ROWS:
        raise RuntimeError(
            "Final fitting row conservation "
            "failed. "
            f"Expected {EXPECTED_FINAL_ROWS:,}, "
            f"found {len(final_frame):,}."
        )


    y_final = np.asarray(
        validate_target(
            final_frame[
                TARGET_COLUMN
            ],
            split_name=(
                "phase_8_15/"
                "train_plus_validation"
            ),
        ),
        dtype=float,
    )


    if np.any(
        y_final < 0
    ):
        raise RuntimeError(
            "Negative demand targets detected."
        )


    X_final = final_frame[
        safe_predictors
    ].copy()


    occurrence_target = (
        y_final > 0
    ).astype(
        np.int8
    )

    positive_mask = (
        occurrence_target == 1
    )


    positive_rows = int(
        positive_mask.sum()
    )

    zero_rows = int(
        (~positive_mask).sum()
    )


    if positive_rows == 0:
        raise RuntimeError(
            "No positive-demand rows exist "
            "for the magnitude model."
        )


    print(
        f"train rows                 : "
        f"{len(train):,}"
    )

    print(
        f"validation rows            : "
        f"{len(validation):,}"
    )

    print(
        "--------------------------------"
    )

    print(
        f"final fitting rows         : "
        f"{len(final_frame):,}"
    )

    print()

    print(
        f"final date range           : "
        f"{final_frame[DATE_COLUMN].min().date()} "
        f"-> "
        f"{final_frame[DATE_COLUMN].max().date()}"
    )

    print(
        f"predictor count            : "
        f"{X_final.shape[1]}"
    )

    print(
        f"zero-demand rows           : "
        f"{zero_rows:,} "
        f"({zero_rows / len(final_frame) * 100:.2f}%)"
    )

    print(
        f"positive-demand rows       : "
        f"{positive_rows:,} "
        f"({positive_rows / len(final_frame) * 100:.2f}%)"
    )


    # =========================================================================
    # Clone the frozen architecture.
    #
    # sklearn.clone recreates the estimators with their exact parameter
    # configuration but WITHOUT their fitted state.
    # =========================================================================

    header(
        "CLONING FROZEN ARCHITECTURE"
    )


    final_preprocessor = clone(
        original_preprocessor
    )

    final_occurrence_model = clone(
        original_occurrence_model
    )

    final_magnitude_model = clone(
        original_magnitude_model
    )


    print(
        "preprocessor cloned        : YES ✓"
    )

    print(
        "occurrence model cloned    : YES ✓"
    )

    print(
        "magnitude model cloned     : YES ✓"
    )

    print(
        "hyperparameter tuning      : NO"
    )

    print(
        "threshold tuning           : NO"
    )

    print(
        "model selection            : NO"
    )


    # =========================================================================
    # Final preprocessing fit.
    #
    # Since this is the final production refit, preprocessing is fitted on
    # TRAIN + VALIDATION.
    # =========================================================================

    header(
        "FINAL PREPROCESSING FIT — TRAIN + VALIDATION"
    )


    preprocessing_start = (
        time.perf_counter()
    )

    X_encoded = (
        final_preprocessor
        .fit_transform(
            X_final
        )
    )


    preprocessing_seconds = (
        time.perf_counter()
        - preprocessing_start
    )


    if hasattr(
        X_encoded,
        "toarray",
    ):
        X_encoded = (
            X_encoded.toarray()
        )


    X_encoded = np.asarray(
        X_encoded,
        dtype=np.float32,
    )


    if (
        X_encoded.shape[0]
        != len(final_frame)
    ):
        raise RuntimeError(
            "Preprocessing row conservation "
            "failed."
        )


    if not np.all(
        np.isfinite(X_encoded)
    ):
        raise RuntimeError(
            "Non-finite encoded predictor "
            "values detected."
        )


    print(
        f"encoded rows               : "
        f"{X_encoded.shape[0]:,}"
    )

    print(
        f"encoded feature count      : "
        f"{X_encoded.shape[1]:,}"
    )

    print(
        f"preprocessing seconds      : "
        f"{preprocessing_seconds:.2f}"
    )

    print(
        "preprocessing fit scope    : "
        "TRAIN + VALIDATION ✓"
    )


    # =========================================================================
    # Final occurrence model
    # =========================================================================

    header(
        "FINAL OCCURRENCE MODEL FIT"
    )


    occurrence_start = (
        time.perf_counter()
    )

    final_occurrence_model.fit(
        X_encoded,
        occurrence_target,
    )

    occurrence_seconds = (
        time.perf_counter()
        - occurrence_start
    )


    print(
        f"training rows              : "
        f"{len(final_frame):,}"
    )

    print(
        f"positive target rows       : "
        f"{positive_rows:,}"
    )

    print(
        f"training seconds           : "
        f"{occurrence_seconds:.2f}"
    )

    print(
        "fit scope                  : "
        "TRAIN + VALIDATION"
    )


    # =========================================================================
    # Final magnitude model
    # =========================================================================

    header(
        "FINAL MAGNITUDE MODEL FIT"
    )


    X_positive = (
        X_encoded[
            positive_mask
        ]
    )

    y_positive = (
        y_final[
            positive_mask
        ]
    )


    magnitude_start = (
        time.perf_counter()
    )

    final_magnitude_model.fit(
        X_positive,
        y_positive,
    )

    magnitude_seconds = (
        time.perf_counter()
        - magnitude_start
    )


    print(
        f"positive-demand rows       : "
        f"{len(y_positive):,}"
    )

    print(
        f"target minimum             : "
        f"{y_positive.min():.6f}"
    )

    print(
        f"target maximum             : "
        f"{y_positive.max():.6f}"
    )

    print(
        f"training seconds           : "
        f"{magnitude_seconds:.2f}"
    )

    print(
        "fit scope                  : "
        "TRAIN + VALIDATION "
        "POSITIVE ROWS ONLY"
    )


    # =========================================================================
    # Training-only diagnostic
    #
    # This is NOT an estimate of generalization performance.
    # It merely confirms the persisted model can produce sensible predictions.
    # =========================================================================

    header(
        "FINAL REFIT INTEGRITY DIAGNOSTICS"
    )


    occurrence_probability = (
        final_occurrence_model
        .predict_proba(
            X_encoded
        )[:, 1]
    )


    predicted_occurrence = (
        occurrence_probability
        >= threshold
    ).astype(
        np.int8
    )


    magnitude_prediction = np.asarray(
        final_magnitude_model.predict(
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


    if len(final_prediction) != len(
        final_frame
    ):
        raise RuntimeError(
            "Prediction row conservation "
            "failed."
        )


    if not np.all(
        np.isfinite(final_prediction)
    ):
        raise RuntimeError(
            "Final model produced non-finite "
            "predictions."
        )


    if np.any(
        final_prediction < 0
    ):
        raise RuntimeError(
            "Final model produced negative "
            "demand forecasts."
        )


    predicted_positive_rows = int(
        predicted_occurrence.sum()
    )

    exact_zero_rows = int(
        np.sum(
            final_prediction == 0
        )
    )


    print(
        f"prediction rows            : "
        f"{len(final_prediction):,}"
    )

    print(
        f"predicted positive rows    : "
        f"{predicted_positive_rows:,}"
    )

    print(
        f"exact-zero forecasts       : "
        f"{exact_zero_rows:,}"
    )

    print(
        "negative forecasts         : 0 ✓"
    )

    print(
        "non-finite forecasts       : 0 ✓"
    )

    print()

    print(
        "NOTE: these are fitting-set "
        "integrity diagnostics only."
    )

    print(
        "They are NOT reported as final "
        "forecast performance."
    )


    # =========================================================================
    # Persist final model bundle
    # =========================================================================

    header(
        "PERSISTING PHASE 8.15 FINAL MODEL"
    )


    final_contract = {
        "phase": "8.15",
        "architecture": "hurdle",
        "target": TARGET_COLUMN,
        "date_column": DATE_COLUMN,
        "threshold": threshold,
        "threshold_source": (
            "Phase 8.12 pre-January "
            "historical backtest"
        ),
        "threshold_retuned": False,
        "safe_predictors": (
            safe_predictors
        ),
        "safe_predictor_count": (
            len(safe_predictors)
        ),
        "training_partitions": [
            "train",
            "validation",
        ],
        "test_partition_used": False,
        "preprocessor_fit_scope": (
            "train_plus_validation"
        ),
        "occurrence_model_fit_scope": (
            "train_plus_validation"
        ),
        "magnitude_model_fit_scope": (
            "train_plus_validation_"
            "positive_demand_only"
        ),
        "original_phase_8_13_contract": (
            frozen_contract
        ),
    }


    final_bundle = {
        "artifact_version": 1,
        "phase": "8.15",
        "created_at_utc": utc_now(),
        "target": TARGET_COLUMN,
        "threshold": threshold,
        "safe_predictors": (
            safe_predictors
        ),
        "preprocessor": (
            final_preprocessor
        ),
        "occurrence_model": (
            final_occurrence_model
        ),
        "magnitude_model": (
            final_magnitude_model
        ),
        "contract": (
            final_contract
        ),
    }


    FINAL_MODEL_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    FINAL_METADATA_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    FINAL_CONTRACT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )


    joblib.dump(
        final_bundle,
        FINAL_MODEL_PATH,
    )


    metadata = {
        "artifact_version": 1,
        "phase": "8.15",
        "generated_at_utc": utc_now(),
        "purpose": (
            "final production refit "
            "before one-time test evaluation"
        ),
        "source_model": str(
            PHASE_8_13_MODEL_PATH
            .relative_to(
                PROJECT_ROOT
            )
        ),
        "final_model": str(
            FINAL_MODEL_PATH
            .relative_to(
                PROJECT_ROOT
            )
        ),
        "training": {
            "train_rows": int(
                len(train)
            ),
            "validation_rows": int(
                len(validation)
            ),
            "final_rows": int(
                len(final_frame)
            ),
            "positive_rows": (
                positive_rows
            ),
            "zero_rows": (
                zero_rows
            ),
            "minimum_date": (
                final_frame[
                    DATE_COLUMN
                ]
                .min()
                .date()
                .isoformat()
            ),
            "maximum_date": (
                final_frame[
                    DATE_COLUMN
                ]
                .max()
                .date()
                .isoformat()
            ),
        },
        "feature_contract": {
            "source_predictor_count": (
                len(safe_predictors)
            ),
            "encoded_feature_count": int(
                X_encoded.shape[1]
            ),
            "predictors": (
                safe_predictors
            ),
        },
        "frozen_decisions": {
            "architecture": (
                "hurdle"
            ),
            "threshold": (
                threshold
            ),
            "threshold_retuned": False,
            "hyperparameters_retuned": False,
            "feature_selection_changed": False,
            "primary_metric": "wape",
        },
        "fit_seconds": {
            "preprocessing": (
                preprocessing_seconds
            ),
            "occurrence_model": (
                occurrence_seconds
            ),
            "magnitude_model": (
                magnitude_seconds
            ),
            "total": (
                preprocessing_seconds
                + occurrence_seconds
                + magnitude_seconds
            ),
        },
        "training_integrity": {
            "prediction_rows": int(
                len(final_prediction)
            ),
            "predicted_positive_rows": (
                predicted_positive_rows
            ),
            "exact_zero_forecasts": (
                exact_zero_rows
            ),
            "negative_forecasts": 0,
            "non_finite_forecasts": 0,
        },
        "evaluation": {
            "validation_performance_recomputed": False,
            "test_performance_computed": False,
            "test_partition_used": False,
        },
        "software": {
            "python": (
                sys.version.split()[0]
            ),
            "pandas": (
                pd.__version__
            ),
            "numpy": (
                np.__version__
            ),
            "scikit_learn": (
                sklearn.__version__
            ),
            "joblib": (
                joblib.__version__
            ),
            "platform": (
                platform.platform()
            ),
        },
    }


    with FINAL_METADATA_PATH.open(
        "w",
        encoding="utf-8",
    ) as handle:
        json.dump(
            metadata,
            handle,
            indent=2,
            default=json_default,
        )

        handle.write("\n")


    with FINAL_CONTRACT_PATH.open(
        "w",
        encoding="utf-8",
    ) as handle:
        json.dump(
            final_contract,
            handle,
            indent=2,
            default=json_default,
        )

        handle.write("\n")


    print(
        f"model artifact             : "
        f"{FINAL_MODEL_PATH}"
    )

    print(
        f"training metadata          : "
        f"{FINAL_METADATA_PATH}"
    )

    print(
        f"model contract             : "
        f"{FINAL_CONTRACT_PATH}"
    )


    # =========================================================================
    # Artifact round-trip
    # =========================================================================

    header(
        "ARTIFACT ROUND-TRIP VERIFICATION"
    )


    reloaded = joblib.load(
        FINAL_MODEL_PATH
    )


    reload_required_keys = {
        "threshold",
        "safe_predictors",
        "preprocessor",
        "occurrence_model",
        "magnitude_model",
        "contract",
    }


    reload_missing = sorted(
        reload_required_keys
        - set(reloaded)
    )

    if reload_missing:
        raise RuntimeError(
            "Reloaded model bundle is missing: "
            f"{reload_missing}"
        )


    reloaded_threshold = float(
        reloaded[
            "threshold"
        ]
    )


    if not np.isclose(
        reloaded_threshold,
        threshold,
    ):
        raise RuntimeError(
            "Threshold changed during "
            "artifact round-trip."
        )


    if list(
        reloaded[
            "safe_predictors"
        ]
    ) != safe_predictors:
        raise RuntimeError(
            "Predictor contract changed during "
            "artifact round-trip."
        )


    # Use a small fitting-data sample solely to make sure the serialized
    # preprocessing + estimator stack is executable after reload.
    #
    # No validation/test scoring is performed here.

    sample_rows = min(
        512,
        len(X_final),
    )

    sample_X = X_final.iloc[
        :sample_rows
    ].copy()


    sample_encoded = (
        reloaded[
            "preprocessor"
        ]
        .transform(
            sample_X
        )
    )


    if hasattr(
        sample_encoded,
        "toarray",
    ):
        sample_encoded = (
            sample_encoded.toarray()
        )


    sample_encoded = np.asarray(
        sample_encoded,
        dtype=np.float32,
    )


    sample_occurrence_probability = (
        reloaded[
            "occurrence_model"
        ]
        .predict_proba(
            sample_encoded
        )[:, 1]
    )


    sample_magnitude = np.asarray(
        reloaded[
            "magnitude_model"
        ]
        .predict(
            sample_encoded
        ),
        dtype=float,
    )


    if not np.all(
        np.isfinite(
            sample_occurrence_probability
        )
    ):
        raise RuntimeError(
            "Reloaded occurrence model produced "
            "non-finite probabilities."
        )


    if not np.all(
        np.isfinite(
            sample_magnitude
        )
    ):
        raise RuntimeError(
            "Reloaded magnitude model produced "
            "non-finite predictions."
        )


    print(
        "model bundle reload        : PASSED ✓"
    )

    print(
        "threshold round-trip       : PASSED ✓"
    )

    print(
        "predictor contract         : PASSED ✓"
    )

    print(
        "preprocessor transform     : PASSED ✓"
    )

    print(
        "occurrence inference       : PASSED ✓"
    )

    print(
        "magnitude inference        : PASSED ✓"
    )


    # =========================================================================
    # Final audit
    # =========================================================================

    header(
        "PHASE 8.15 AUDIT"
    )


    print(
        f"TRAIN rows used            : "
        f"{len(train):,}"
    )

    print(
        f"VALIDATION rows used       : "
        f"{len(validation):,}"
    )

    print(
        f"final fitting rows         : "
        f"{len(final_frame):,}"
    )

    print(
        "TRAIN used for fitting     : YES ✓"
    )

    print(
        "VALIDATION used for fitting: YES ✓"
    )

    print(
        "TEST read                  : NO 🔒"
    )

    print(
        "TEST used for fitting      : NO 🔒"
    )

    print(
        "TEST metric produced       : NO 🔒"
    )

    print(
        "architecture changed       : NO"
    )

    print(
        "hyperparameters changed    : NO"
    )

    print(
        "feature contract changed   : NO"
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

    print(
        "final model artifact       : YES ✓"
    )

    print(
        "artifact verification      : PASSED ✓"
    )


    print()
    print("=" * 100)

    print(
        "PHASE 8.15 FINAL REFIT PASSED ✓"
    )

    print(
        "FINAL MODEL IS READY FOR "
        "ONE-TIME TEST EVALUATION"
    )

    print(
        "TEST PARTITION REMAINS LOCKED 🔒"
    )

    print("=" * 100)


if __name__ == "__main__":
    main()
