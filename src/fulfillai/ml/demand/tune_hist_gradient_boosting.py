"""
FulfillAI Phase 8.9 validation-only tuning for the Phase 8.8
leakage-safe HistGradientBoosting demand model.

Purpose
-------
Tune a compact, deliberately bounded set of HistGradientBoostingRegressor
hyperparameters after Phase 8.8 feature engineering has been proven useful.

Experimental discipline
-----------------------
TRAIN      -> fit preprocessing and every candidate model
VALIDATION -> compare/rank candidates by WAPE
TEST       -> completely untouched

The Phase 8.8 feature contract is imported from
train_hist_gradient_boosting.py so tuning cannot silently drift to a
different predictor set.

Important
---------
This is model selection on one validation period, not a final generalization
estimate. The test partition remains locked. A later temporal/backtesting
phase should confirm the selected configuration before the one-time test run.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np

from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer

from ..config import METRIC_ROOT, MODEL_ROOT, ensure_artifact_directories
from ..data import load_task_dataset
from ..metrics import forecasting_metrics
from .train_hist_gradient_boosting import (
    EXPECTED_PHASE_8_8_PREDICTORS,
    INTENTIONALLY_UNUSED_PREDICTORS,
    PHASE_8_8_ADDED_SAFE_COLUMNS,
    PRE_PHASE_8_8_HGB_VALIDATION_WAPE,
    ROLLING_28_VALIDATION_WAPE,
    SAFE_CATEGORICAL_COLUMNS,
    SAFE_COLUMNS,
    SAFE_NUMERIC_COLUMNS,
    build_preprocessor,
    select_safe_features,
    validate_target,
)

TASK_NAME = "demand_forecasting"
PHASE = "8.9"
PRIMARY_METRIC = "wape"

PHASE_8_8_REFERENCE_WAPE = 87.066218

BEST_MODEL_PATH = (
    MODEL_ROOT
    / "demand"
    / "hist_gradient_boosting_poisson_phase_8_9_best_validation.joblib"
)

TUNING_RESULTS_PATH = (
    METRIC_ROOT
    / "demand_hist_gradient_boosting_phase_8_9_tuning.json"
)

CANDIDATES: tuple[dict[str, Any], ...] = (
    {
        "name": "hgb_01_phase_8_8_reference",
        "learning_rate": 0.06,
        "max_iter": 200,
        "max_leaf_nodes": 31,
        "min_samples_leaf": 100,
        "l2_regularization": 1.0,
    },
    {
        "name": "hgb_02_lower_lr_longer",
        "learning_rate": 0.04,
        "max_iter": 300,
        "max_leaf_nodes": 31,
        "min_samples_leaf": 100,
        "l2_regularization": 1.0,
    },
    {
        "name": "hgb_03_higher_lr_shorter",
        "learning_rate": 0.08,
        "max_iter": 150,
        "max_leaf_nodes": 31,
        "min_samples_leaf": 100,
        "l2_regularization": 1.0,
    },
    {
        "name": "hgb_04_deeper",
        "learning_rate": 0.06,
        "max_iter": 200,
        "max_leaf_nodes": 63,
        "min_samples_leaf": 100,
        "l2_regularization": 1.0,
    },
    {
        "name": "hgb_05_shallower",
        "learning_rate": 0.06,
        "max_iter": 200,
        "max_leaf_nodes": 15,
        "min_samples_leaf": 100,
        "l2_regularization": 1.0,
    },
    {
        "name": "hgb_06_smaller_leaf",
        "learning_rate": 0.06,
        "max_iter": 200,
        "max_leaf_nodes": 31,
        "min_samples_leaf": 50,
        "l2_regularization": 1.0,
    },
    {
        "name": "hgb_07_larger_leaf",
        "learning_rate": 0.06,
        "max_iter": 200,
        "max_leaf_nodes": 31,
        "min_samples_leaf": 150,
        "l2_regularization": 1.0,
    },
    {
        "name": "hgb_08_lower_regularization",
        "learning_rate": 0.06,
        "max_iter": 200,
        "max_leaf_nodes": 31,
        "min_samples_leaf": 100,
        "l2_regularization": 0.25,
    },
    {
        "name": "hgb_09_higher_regularization",
        "learning_rate": 0.06,
        "max_iter": 200,
        "max_leaf_nodes": 31,
        "min_samples_leaf": 100,
        "l2_regularization": 3.0,
    },
    {
        "name": "hgb_10_deep_regularized",
        "learning_rate": 0.04,
        "max_iter": 300,
        "max_leaf_nodes": 63,
        "min_samples_leaf": 100,
        "l2_regularization": 2.0,
    },
    {
        "name": "hgb_11_deep_smaller_leaf",
        "learning_rate": 0.05,
        "max_iter": 250,
        "max_leaf_nodes": 63,
        "min_samples_leaf": 50,
        "l2_regularization": 1.0,
    },
    {
        "name": "hgb_12_conservative",
        "learning_rate": 0.04,
        "max_iter": 300,
        "max_leaf_nodes": 15,
        "min_samples_leaf": 150,
        "l2_regularization": 2.0,
    },
)


class DemandTuningError(RuntimeError):
    """Raised when Phase 8.9 tuning cannot continue safely."""


def _as_float32(matrix: Any) -> np.ndarray:
    return np.asarray(matrix, dtype=np.float32)


def _candidate_model(candidate: dict[str, Any]) -> HistGradientBoostingRegressor:
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


def _validate_candidate_definitions() -> None:
    if len(CANDIDATES) != 12:
        raise DemandTuningError(
            f"Expected exactly 12 bounded candidates; found {len(CANDIDATES)}."
        )

    names = [str(candidate["name"]) for candidate in CANDIDATES]
    if len(names) != len(set(names)):
        raise DemandTuningError("Candidate names must be unique.")

    required = {
        "name",
        "learning_rate",
        "max_iter",
        "max_leaf_nodes",
        "min_samples_leaf",
        "l2_regularization",
    }

    signatures: set[tuple[Any, ...]] = set()

    for candidate in CANDIDATES:
        missing = required - set(candidate)
        extra = set(candidate) - required

        if missing:
            raise DemandTuningError(
                f"{candidate.get('name', '<unnamed>')}: missing keys {sorted(missing)}"
            )
        if extra:
            raise DemandTuningError(
                f"{candidate['name']}: unexpected keys {sorted(extra)}"
            )

        if float(candidate["learning_rate"]) <= 0:
            raise DemandTuningError(
                f"{candidate['name']}: learning_rate must be > 0."
            )
        if int(candidate["max_iter"]) <= 0:
            raise DemandTuningError(
                f"{candidate['name']}: max_iter must be > 0."
            )
        if int(candidate["max_leaf_nodes"]) < 2:
            raise DemandTuningError(
                f"{candidate['name']}: max_leaf_nodes must be >= 2."
            )
        if int(candidate["min_samples_leaf"]) < 1:
            raise DemandTuningError(
                f"{candidate['name']}: min_samples_leaf must be >= 1."
            )
        if float(candidate["l2_regularization"]) < 0:
            raise DemandTuningError(
                f"{candidate['name']}: l2_regularization must be >= 0."
            )

        signature = (
            float(candidate["learning_rate"]),
            int(candidate["max_iter"]),
            int(candidate["max_leaf_nodes"]),
            int(candidate["min_samples_leaf"]),
            float(candidate["l2_regularization"]),
        )
        if signature in signatures:
            raise DemandTuningError(
                f"{candidate['name']}: duplicates another candidate configuration."
            )
        signatures.add(signature)

    reference = CANDIDATES[0]
    expected_reference = {
        "learning_rate": 0.06,
        "max_iter": 200,
        "max_leaf_nodes": 31,
        "min_samples_leaf": 100,
        "l2_regularization": 1.0,
    }
    for key, expected_value in expected_reference.items():
        if reference[key] != expected_value:
            raise DemandTuningError(
                "Candidate 01 must exactly reproduce Phase 8.8. "
                f"{key}={reference[key]!r}, expected {expected_value!r}."
            )


def _validate_phase_8_8_contract() -> None:
    if len(EXPECTED_PHASE_8_8_PREDICTORS) != 60:
        raise DemandTuningError(
            "Expected 60 Phase 8.8 source predictors; "
            f"found {len(EXPECTED_PHASE_8_8_PREDICTORS)}."
        )
    if len(SAFE_COLUMNS) != 52:
        raise DemandTuningError(
            "Expected 52 Phase 8.8 safe predictors; "
            f"found {len(SAFE_COLUMNS)}."
        )
    if len(PHASE_8_8_ADDED_SAFE_COLUMNS) != 29:
        raise DemandTuningError(
            "Expected 29 Phase 8.8 added safe predictors; "
            f"found {len(PHASE_8_8_ADDED_SAFE_COLUMNS)}."
        )
    if len(INTENTIONALLY_UNUSED_PREDICTORS) != 8:
        raise DemandTuningError(
            "Expected 8 intentionally unused predictors; "
            f"found {len(INTENTIONALLY_UNUSED_PREDICTORS)}."
        )


def _prediction_checks(prediction: np.ndarray, *, candidate_name: str) -> None:
    if not np.isfinite(prediction).all():
        raise DemandTuningError(
            f"{candidate_name}: validation predictions contain NaN/Inf."
        )
    negative = int(np.sum(prediction < 0))
    if negative:
        raise DemandTuningError(
            f"{candidate_name}: Poisson model produced "
            f"{negative:,} negative validation predictions."
        )


def _round_metrics(metrics: dict[str, float]) -> dict[str, float]:
    return {key: float(value) for key, value in metrics.items()}


def save_tuning_artifacts(
    *,
    preprocessor: Any,
    best_model: HistGradientBoostingRegressor,
    best_result: dict[str, Any],
    ranked_results: list[dict[str, Any]],
    training_rows: int,
    validation_rows: int,
    source_predictor_count: int,
    encoded_feature_count: int,
    preprocessing_seconds: float,
    total_tuning_seconds: float,
) -> tuple[Path, Path]:
    ensure_artifact_directories()

    BEST_MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    TUNING_RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)

    champion_pipeline = Pipeline(
        steps=[
            ("preprocessing", preprocessor),
            (
                "float32",
                FunctionTransformer(_as_float32, validate=False),
            ),
            ("model", best_model),
        ]
    )
    joblib.dump(champion_pipeline, BEST_MODEL_PATH)

    payload = {
        "artifact_version": 1,
        "phase": PHASE,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "task": TASK_NAME,
        "experiment": "phase_8_8_feature_set_compact_hgb_validation_tuning",
        "training_split": "train",
        "evaluation_split": "validation",
        "test_set_used": False,
        "primary_metric": PRIMARY_METRIC,
        "training_rows": int(training_rows),
        "validation_rows": int(validation_rows),
        "source_predictor_count": int(source_predictor_count),
        "safe_predictor_count": int(len(SAFE_COLUMNS)),
        "phase_8_8_added_safe_predictor_count": int(
            len(PHASE_8_8_ADDED_SAFE_COLUMNS)
        ),
        "encoded_feature_count": int(encoded_feature_count),
        "preprocessing_fit_on": "train_only",
        "preprocessing_seconds": float(preprocessing_seconds),
        "total_tuning_seconds": float(total_tuning_seconds),
        "selection_policy": {
            "metric": PRIMARY_METRIC,
            "direction": "lower_is_better",
            "candidate_count": int(len(CANDIDATES)),
            "validation_reuse_warning": (
                "The validation period is used for hyperparameter selection. "
                "This ranking is not a final generalization estimate."
            ),
            "test_partition_locked": True,
        },
        "feature_contract": {
            "safe_categorical_predictors": list(SAFE_CATEGORICAL_COLUMNS),
            "safe_numeric_predictors": list(SAFE_NUMERIC_COLUMNS),
            "safe_predictors": list(SAFE_COLUMNS),
            "phase_8_8_added_safe_predictors": list(
                PHASE_8_8_ADDED_SAFE_COLUMNS
            ),
            "intentionally_unused_predictors": list(
                INTENTIONALLY_UNUSED_PREDICTORS
            ),
        },
        "benchmarks": {
            "rolling_28_validation_wape": float(
                ROLLING_28_VALIDATION_WAPE
            ),
            "pre_phase_8_8_hgb_validation_wape": float(
                PRE_PHASE_8_8_HGB_VALIDATION_WAPE
            ),
            "phase_8_8_reference_validation_wape": float(
                PHASE_8_8_REFERENCE_WAPE
            ),
        },
        "best_validation_candidate": best_result,
        "validation_leaderboard": ranked_results,
    }

    with TUNING_RESULTS_PATH.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")

    return BEST_MODEL_PATH, TUNING_RESULTS_PATH


def main() -> None:
    print()
    print("=" * 96)
    print("FulfillAI Phase 8.9 — Phase 8.8 HGB validation tuning")
    print("=" * 96)

    _validate_candidate_definitions()
    _validate_phase_8_8_contract()

    dataset = load_task_dataset(TASK_NAME)
    train = dataset.train
    validation = dataset.validation

    # Deliberately never access dataset.test.

    print()
    print(f"training rows                     : {train.rows:,}")
    print(f"validation rows                   : {validation.rows:,}")
    print(f"source predictor count            : {len(dataset.predictors):,}")
    print(f"safe predictor count              : {len(SAFE_COLUMNS):,}")
    print(
        f"Phase 8.8 added safe predictors   : "
        f"{len(PHASE_8_8_ADDED_SAFE_COLUMNS):,}"
    )
    print(f"candidate count                   : {len(CANDIDATES):,}")
    print("selection metric                  : WAPE (lower is better)")
    print("test partition                    : LOCKED / NOT USED")

    if len(dataset.predictors) != 60:
        raise DemandTuningError(
            "Expected rebuilt Phase 8.8 demand dataset with 60 predictors; "
            f"found {len(dataset.predictors)}."
        )

    X_train = select_safe_features(train.X, split_name="train")
    X_validation = select_safe_features(
        validation.X,
        split_name="validation",
    )
    y_train = validate_target(train.y, split_name="train")
    y_validation = validate_target(
        validation.y,
        split_name="validation",
    )

    print()
    print("=" * 96)
    print("PREPROCESSING — FIT TRAIN ONLY, REUSE FOR ALL CANDIDATES")
    print("=" * 96)

    preprocessor = build_preprocessor()

    preprocessing_started = time.perf_counter()
    X_train_encoded = _as_float32(preprocessor.fit_transform(X_train))
    X_validation_encoded = _as_float32(
        preprocessor.transform(X_validation)
    )
    preprocessing_seconds = time.perf_counter() - preprocessing_started

    if X_train_encoded.ndim != 2 or X_validation_encoded.ndim != 2:
        raise DemandTuningError(
            "Encoded feature matrices must be two-dimensional."
        )
    if X_train_encoded.shape[1] != X_validation_encoded.shape[1]:
        raise DemandTuningError(
            "Train/validation encoded feature counts differ: "
            f"{X_train_encoded.shape[1]} vs {X_validation_encoded.shape[1]}."
        )
    if not np.isfinite(X_train_encoded).all():
        raise DemandTuningError("Encoded training matrix contains NaN/Inf.")
    if not np.isfinite(X_validation_encoded).all():
        raise DemandTuningError("Encoded validation matrix contains NaN/Inf.")

    encoded_feature_count = int(X_train_encoded.shape[1])

    print(f"encoded training shape            : {X_train_encoded.shape}")
    print(f"encoded validation shape          : {X_validation_encoded.shape}")
    print(f"encoded feature count             : {encoded_feature_count:,}")
    print(f"preprocessing seconds             : {preprocessing_seconds:.2f}")
    print("same preprocessing for candidates : YES ✓")
    print("preprocessing fit on validation   : NO ✓")
    print("test partition accessed           : NO ✓")

    del X_train
    del X_validation

    print()
    print("=" * 96)
    print("CANDIDATE TRAINING — VALIDATION ONLY FOR MODEL SELECTION")
    print("=" * 96)

    tuning_started = time.perf_counter()

    results: list[dict[str, Any]] = []
    fitted_models: dict[str, HistGradientBoostingRegressor] = {}

    for index, candidate in enumerate(CANDIDATES, start=1):
        name = str(candidate["name"])

        print()
        print("-" * 96)
        print(f"[{index:02d}/{len(CANDIDATES):02d}] {name}")
        print("-" * 96)
        print(
            "lr={learning_rate}  iter={max_iter}  leaves={max_leaf_nodes}  "
            "min_leaf={min_samples_leaf}  l2={l2_regularization}".format(
                **candidate
            )
        )

        model = _candidate_model(candidate)

        started = time.perf_counter()
        model.fit(X_train_encoded, y_train)
        training_seconds = time.perf_counter() - started

        prediction = np.asarray(
            model.predict(X_validation_encoded),
            dtype=float,
        )
        _prediction_checks(prediction, candidate_name=name)

        metrics = forecasting_metrics(y_validation, prediction)
        wape = float(metrics["wape"])

        result = {
            "name": name,
            "parameters": {
                "loss": "poisson",
                "learning_rate": float(candidate["learning_rate"]),
                "max_iter": int(candidate["max_iter"]),
                "max_leaf_nodes": int(candidate["max_leaf_nodes"]),
                "min_samples_leaf": int(candidate["min_samples_leaf"]),
                "l2_regularization": float(candidate["l2_regularization"]),
                "max_bins": 255,
                "early_stopping": False,
                "random_state": 42,
            },
            "metrics": _round_metrics(metrics),
            "training_seconds": float(training_seconds),
            "delta_vs_phase_8_8_reference_wape_points": float(
                PHASE_8_8_REFERENCE_WAPE - wape
            ),
            "delta_vs_rolling_28_wape_points": float(
                ROLLING_28_VALIDATION_WAPE - wape
            ),
        }

        results.append(result)
        fitted_models[name] = model

        print(f"MAE                             : {metrics['mae']:.6f}")
        print(f"RMSE                            : {metrics['rmse']:.6f}")
        print(f"WAPE                            : {wape:.6f}%")
        print(f"sMAPE                           : {metrics['smape']:.6f}%")
        print(f"training seconds                : {training_seconds:.2f}")
        print(
            "delta vs Phase 8.8 reference    : "
            f"{PHASE_8_8_REFERENCE_WAPE - wape:+.6f} points"
        )

    total_tuning_seconds = time.perf_counter() - tuning_started

    ranked = sorted(
        results,
        key=lambda item: (
            float(item["metrics"]["wape"]),
            float(item["metrics"]["mae"]),
            float(item["metrics"]["rmse"]),
            str(item["name"]),
        ),
    )

    for rank, result in enumerate(ranked, start=1):
        result["rank"] = int(rank)

    best = ranked[0]
    best_name = str(best["name"])
    best_model = fitted_models[best_name]
    best_wape = float(best["metrics"]["wape"])

    print()
    print("=" * 96)
    print("PHASE 8.9 VALIDATION LEADERBOARD")
    print("=" * 96)
    print(
        f"{'rank':<5}"
        f"{'candidate':<34}"
        f"{'WAPE':>12}"
        f"{'Δ vs P8.8':>14}"
        f"{'Δ vs roll28':>14}"
        f"{'seconds':>11}"
    )
    print("-" * 96)

    for result in ranked:
        print(
            f"{result['rank']:<5}"
            f"{result['name']:<34}"
            f"{float(result['metrics']['wape']):>11.6f}%"
            f"{float(result['delta_vs_phase_8_8_reference_wape_points']):>+14.6f}"
            f"{float(result['delta_vs_rolling_28_wape_points']):>+14.6f}"
            f"{float(result['training_seconds']):>11.2f}"
        )

    print()
    print("-" * 96)
    print(
        f"{'rolling_28 benchmark':<39}"
        f"{ROLLING_28_VALIDATION_WAPE:>11.6f}%"
    )
    print(
        f"{'Phase 8.8 reference':<39}"
        f"{PHASE_8_8_REFERENCE_WAPE:>11.6f}%"
    )

    improvement_vs_phase_8_8 = PHASE_8_8_REFERENCE_WAPE - best_wape
    improvement_vs_rolling = ROLLING_28_VALIDATION_WAPE - best_wape

    print()
    print("=" * 96)
    print("PHASE 8.9 BEST VALIDATION CANDIDATE")
    print("=" * 96)
    print(f"name                            : {best_name}")
    print(f"WAPE                            : {best_wape:.6f}%")
    print(f"MAE                             : {float(best['metrics']['mae']):.6f}")
    print(f"RMSE                            : {float(best['metrics']['rmse']):.6f}")
    print(f"sMAPE                           : {float(best['metrics']['smape']):.6f}%")
    print(
        "improvement vs Phase 8.8       : "
        f"{improvement_vs_phase_8_8:+.6f} WAPE points"
    )
    print(
        "improvement vs rolling_28      : "
        f"{improvement_vs_rolling:+.6f} WAPE points"
    )
    print()
    print("parameters")
    for key, value in best["parameters"].items():
        print(f"  {key:<24}: {value}")

    if best_wape < PHASE_8_8_REFERENCE_WAPE:
        print()
        print("RESULT: TUNING IMPROVES THE PHASE 8.8 VALIDATION MODEL ✓")
    else:
        print()
        print(
            "RESULT: NO TUNED CANDIDATE BEATS THE PHASE 8.8 REFERENCE; "
            "KEEP THE REFERENCE."
        )

    model_path, metrics_path = save_tuning_artifacts(
        preprocessor=preprocessor,
        best_model=best_model,
        best_result=best,
        ranked_results=ranked,
        training_rows=train.rows,
        validation_rows=validation.rows,
        source_predictor_count=len(dataset.predictors),
        encoded_feature_count=encoded_feature_count,
        preprocessing_seconds=preprocessing_seconds,
        total_tuning_seconds=total_tuning_seconds,
    )

    print()
    print("=" * 96)
    print("ARTIFACTS")
    print("=" * 96)
    print(f"best validation model : {model_path}")
    print(f"tuning audit          : {metrics_path}")

    print()
    print("same-day leakage columns used       : 0 ✓")
    print("current snapshot columns used       : 0 ✓")
    print("Phase 8.8 historical features used  : YES ✓")
    print("preprocessing fit on TRAIN only     : YES ✓")
    print("model selection uses VALIDATION     : YES ✓")
    print("test set used                       : FALSE ✓")

    print()
    print(
        "CAUTION: this is the validation champion, not the final test estimate. "
        "Do not evaluate the test partition yet."
    )

    print()
    print("=" * 96)
    print("PHASE 8.9 HGB VALIDATION TUNING COMPLETE ✓")
    print("=" * 96)


if __name__ == "__main__":
    main()
