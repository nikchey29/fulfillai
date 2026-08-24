"""
FulfillAI — Phase 8.16
One-time final test evaluation of the frozen Phase 8.15 hurdle model.

Protocol:
- source tree must be committed/clean before test access;
- Phase 8.15 model/threshold/feature contract are frozen;
- test.parquet is read once for the final unbiased estimate;
- transform/predict only: no fit, tuning, threshold search, or model selection;
- final metrics are persisted once and the script refuses a second run.
"""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn

from src.fulfillai.ml.config import get_task_config
from src.fulfillai.ml.data import load_metadata, load_split, predictor_columns
from src.fulfillai.ml.metrics import (
    binary_classification_metrics,
    forecasting_metrics,
)


PROJECT_ROOT = Path(__file__).resolve().parents[4]
TASK_NAME = "demand_forecasting"
TARGET_COLUMN = "units_sold"
DATE_COLUMN = "demand_date"
ROLLING_28_COLUMN = "rolling_28d_avg_units"
EXPECTED_PHASE = "8.15"
EXPECTED_ARCHITECTURE = "hurdle"
EXPECTED_THRESHOLD = 0.925

FINAL_MODEL_PATH = (
    PROJECT_ROOT
    / "artifacts/models/demand/hurdle_phase_8_15_final.joblib"
)
FINAL_REFIT_METADATA_PATH = (
    PROJECT_ROOT
    / "artifacts/metrics/demand/hurdle_phase_8_15_final_refit.json"
)
FINAL_TEST_METRICS_PATH = (
    PROJECT_ROOT
    / "artifacts/metrics/demand/hurdle_phase_8_16_test.json"
)


def header(title: str) -> None:
    print()
    print("=" * 100)
    print(title)
    print("=" * 100)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


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
    raise TypeError(f"Cannot serialize {type(value)!r}")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def require_clean_git() -> str:
    try:
        status = run_git("status", "--porcelain", "--untracked-files=all")
        commit = run_git("rev-parse", "HEAD")
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        raise RuntimeError(
            "Cannot verify Git freeze state; final test evaluation blocked."
        ) from exc

    if status:
        raise RuntimeError(
            "Refusing to read test.parquet because the Git working tree is "
            "not clean. Commit the frozen Phase 8 source first.\n\n"
            f"Current status:\n{status}"
        )
    return commit


def require_first_run() -> None:
    if FINAL_TEST_METRICS_PATH.exists():
        raise RuntimeError(
            "Phase 8.16 final-test artifact already exists. Refusing to "
            "evaluate the test partition again:\n"
            f"{FINAL_TEST_METRICS_PATH}"
        )


def load_frozen_bundle() -> dict:
    if not FINAL_MODEL_PATH.exists():
        raise FileNotFoundError(f"Missing Phase 8.15 model: {FINAL_MODEL_PATH}")

    bundle = joblib.load(FINAL_MODEL_PATH)
    required = {
        "artifact_version",
        "phase",
        "target",
        "threshold",
        "safe_predictors",
        "preprocessor",
        "occurrence_model",
        "magnitude_model",
        "contract",
    }
    if not isinstance(bundle, dict):
        raise RuntimeError("Phase 8.15 model artifact is not a dict bundle.")

    missing = sorted(required - set(bundle))
    if missing:
        raise RuntimeError(f"Phase 8.15 bundle missing keys: {missing}")

    if str(bundle["phase"]) != EXPECTED_PHASE:
        raise RuntimeError(f"Expected model phase {EXPECTED_PHASE}, found {bundle['phase']!r}.")
    if str(bundle["target"]) != TARGET_COLUMN:
        raise RuntimeError(f"Expected target {TARGET_COLUMN!r}, found {bundle['target']!r}.")

    threshold = float(bundle["threshold"])
    if not np.isclose(threshold, EXPECTED_THRESHOLD):
        raise RuntimeError(
            f"Frozen threshold changed: expected {EXPECTED_THRESHOLD}, found {threshold}."
        )

    predictors = list(bundle["safe_predictors"])
    if not predictors or len(predictors) != len(set(predictors)):
        raise RuntimeError("Frozen predictor contract is empty or contains duplicates.")
    if TARGET_COLUMN in predictors or DATE_COLUMN in predictors:
        raise RuntimeError("Target/date leakage found in frozen predictor contract.")

    contract = bundle["contract"]
    if not isinstance(contract, dict):
        raise RuntimeError("Frozen contract is malformed.")
    if contract.get("architecture") != EXPECTED_ARCHITECTURE:
        raise RuntimeError("Frozen architecture changed unexpectedly.")
    if not np.isclose(float(contract.get("threshold", np.nan)), EXPECTED_THRESHOLD):
        raise RuntimeError("Contract threshold does not match the frozen threshold.")
    if contract.get("threshold_retuned") is not False:
        raise RuntimeError("Contract indicates threshold retuning.")
    if contract.get("test_partition_used") is not False:
        raise RuntimeError("Contract indicates prior test-set use.")
    if list(contract.get("safe_predictors", [])) != predictors:
        raise RuntimeError("Bundle and contract predictor lists differ.")

    return bundle


def load_refit_metadata() -> dict:
    if not FINAL_REFIT_METADATA_PATH.exists():
        raise FileNotFoundError(
            f"Missing Phase 8.15 refit metadata: {FINAL_REFIT_METADATA_PATH}"
        )
    with FINAL_REFIT_METADATA_PATH.open("r", encoding="utf-8") as handle:
        metadata = json.load(handle)

    frozen = metadata.get("frozen_decisions", {})
    evaluation = metadata.get("evaluation", {})
    checks = {
        "phase": metadata.get("phase") == EXPECTED_PHASE,
        "architecture": frozen.get("architecture") == EXPECTED_ARCHITECTURE,
        "threshold": np.isclose(float(frozen.get("threshold", np.nan)), EXPECTED_THRESHOLD),
        "threshold_retuned": frozen.get("threshold_retuned") is False,
        "hyperparameters_retuned": frozen.get("hyperparameters_retuned") is False,
        "feature_selection_changed": frozen.get("feature_selection_changed") is False,
        "test_partition_used": evaluation.get("test_partition_used") is False,
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise RuntimeError(f"Phase 8.15 refit metadata failed freeze checks: {failed}")
    return metadata


def finite_1d(values, *, name: str) -> np.ndarray:
    array = np.asarray(values, dtype=float)
    if array.ndim != 1 or len(array) == 0:
        raise RuntimeError(f"{name} must be a non-empty one-dimensional array.")
    if not np.isfinite(array).all():
        raise RuntimeError(f"{name} contains NaN or infinite values.")
    return array


def error_decomposition(
    y_true: np.ndarray,
    hurdle: np.ndarray,
    rolling: np.ndarray,
) -> dict:
    zero = y_true == 0
    positive = y_true > 0
    h_abs = np.abs(y_true - hurdle)
    r_abs = np.abs(y_true - rolling)
    return {
        "rows": int(len(y_true)),
        "zero_demand_rows": int(zero.sum()),
        "positive_demand_rows": int(positive.sum()),
        "zero_demand_share": float(zero.mean()),
        "positive_demand_share": float(positive.mean()),
        "hurdle_zero_demand_absolute_error": float(h_abs[zero].sum()),
        "rolling_28_zero_demand_absolute_error": float(r_abs[zero].sum()),
        "hurdle_positive_demand_absolute_error": float(h_abs[positive].sum()),
        "rolling_28_positive_demand_absolute_error": float(r_abs[positive].sum()),
        "hurdle_total_absolute_error": float(h_abs.sum()),
        "rolling_28_total_absolute_error": float(r_abs.sum()),
    }


def main() -> None:
    header("FULFILLAI PHASE 8.16 — ONE-TIME FINAL TEST EVALUATION")
    print("architecture               : FROZEN")
    print("hyperparameters             : FROZEN")
    print("feature contract            : FROZEN")
    print(f"hurdle threshold            : {EXPECTED_THRESHOLD:.3f} 🔒")
    print("test evaluation             : ONE TIME ONLY")

    # No test data is touched before every gate below passes.
    header("PRE-TEST FREEZE GATES")
    require_first_run()
    git_commit = require_clean_git()
    bundle = load_frozen_bundle()
    refit_metadata = load_refit_metadata()
    model_sha256 = sha256_file(FINAL_MODEL_PATH)
    threshold = float(bundle["threshold"])
    safe_predictors = list(bundle["safe_predictors"])

    print(f"git commit                 : {git_commit}")
    print("git working tree           : CLEAN ✓")
    print("prior Phase 8.16 artifact  : NONE ✓")
    print(f"model SHA-256              : {model_sha256}")
    print(f"safe predictor count       : {len(safe_predictors)}")
    print(f"threshold                  : {threshold:.3f} ✓")
    print("Phase 8.15 freeze contract : PASSED ✓")
    print("test.parquet read          : NO 🔒")

    # One-time test read. Deliberately do NOT use load_task_dataset(), because
    # that helper loads train/validation/test together. load_split reads only test.
    header("OPENING FINAL TEST PARTITION — ONE TIME")
    task = get_task_config(TASK_NAME)
    metadata = load_metadata(task)
    phase7_predictors = predictor_columns(task, metadata)
    test = load_split(
        task,
        "test",
        metadata=metadata,
        predictors=phase7_predictors,
    )
    frame = test.frame

    if task.target_column != TARGET_COLUMN or task.split_column != DATE_COLUMN:
        raise RuntimeError("Task target/date contract changed after model freeze.")

    missing = sorted(set(safe_predictors) - set(frame.columns))
    if missing:
        raise RuntimeError(f"Test set missing frozen predictors: {missing}")
    if ROLLING_28_COLUMN not in frame.columns:
        raise RuntimeError(f"Test set missing baseline column {ROLLING_28_COLUMN!r}.")

    dates = pd.to_datetime(frame[DATE_COLUMN], errors="raise").dt.normalize()
    train_max_raw = refit_metadata.get("training", {}).get("maximum_date")
    if train_max_raw is not None:
        train_max = pd.Timestamp(train_max_raw).normalize()
        if train_max >= dates.min():
            raise RuntimeError("Final fitting period overlaps the test period.")

    print(f"test rows                  : {test.rows:,}")
    print(f"test range                 : {dates.min().date()} -> {dates.max().date()}")
    print("Phase 7 row contract       : PASSED ✓")
    print("frozen feature contract    : PASSED ✓")
    print("test partition read        : YES — ONE-TIME EVALUATION STARTED 🔓")

    # Frozen inference only: transform/predict. No .fit() calls exist below.
    header("FROZEN PHASE 8.15 INFERENCE")
    y_true = finite_1d(
        pd.to_numeric(frame[TARGET_COLUMN], errors="raise").to_numpy(),
        name="test target",
    )
    if np.any(y_true < 0):
        raise RuntimeError("Test target contains negative demand.")

    X_test = frame[safe_predictors].copy()
    X_encoded = bundle["preprocessor"].transform(X_test)
    if hasattr(X_encoded, "toarray"):
        X_encoded = X_encoded.toarray()
    X_encoded = np.asarray(X_encoded, dtype=np.float32)
    if X_encoded.ndim != 2 or X_encoded.shape[0] != len(frame):
        raise RuntimeError("Preprocessing changed the test row count.")
    if not np.isfinite(X_encoded).all():
        raise RuntimeError("Preprocessing produced non-finite test predictors.")

    occurrence_probability = finite_1d(
        bundle["occurrence_model"].predict_proba(X_encoded)[:, 1],
        name="occurrence probability",
    )
    if ((occurrence_probability < 0) | (occurrence_probability > 1)).any():
        raise RuntimeError("Occurrence model produced invalid probabilities.")

    predicted_occurrence = (occurrence_probability >= threshold).astype(np.int8)
    magnitude = finite_1d(
        bundle["magnitude_model"].predict(X_encoded),
        name="magnitude prediction",
    )
    magnitude = np.clip(magnitude, 0.0, None)
    hurdle_prediction = finite_1d(
        np.where(predicted_occurrence == 1, magnitude, 0.0),
        name="final hurdle forecast",
    )
    rolling_prediction = finite_1d(
        pd.to_numeric(frame[ROLLING_28_COLUMN], errors="raise").to_numpy(),
        name="rolling_28 forecast",
    )
    if np.any(hurdle_prediction < 0) or np.any(rolling_prediction < 0):
        raise RuntimeError("Negative forecast detected.")

    print(f"raw predictor count        : {X_test.shape[1]:,}")
    print(f"encoded feature count      : {X_encoded.shape[1]:,}")
    print(f"predicted positive rows    : {int(predicted_occurrence.sum()):,}")
    print(f"exact-zero forecasts       : {int(np.sum(hurdle_prediction == 0)):,}")
    print("preprocessor fit           : NO ✓")
    print("occurrence model fit       : NO ✓")
    print("magnitude model fit        : NO ✓")
    print("threshold retuned          : NO ✓")

    # Final metrics.
    hurdle_metrics = forecasting_metrics(y_true, hurdle_prediction)
    rolling_metrics = forecasting_metrics(y_true, rolling_prediction)
    occurrence_target = (y_true > 0).astype(np.int8)
    occurrence_metrics = binary_classification_metrics(
        occurrence_target,
        occurrence_probability,
        threshold=threshold,
        k_fraction=0.01,
    )
    errors = error_decomposition(y_true, hurdle_prediction, rolling_prediction)

    header("PHASE 8.16 FINAL TEST FORECAST METRICS")
    print(f"{'MODEL':<18}{'MAE':>14}{'RMSE':>14}{'WAPE':>14}{'sMAPE':>14}")
    print("-" * 74)
    for name, values in (("hurdle_0.925", hurdle_metrics), ("rolling_28", rolling_metrics)):
        print(
            f"{name:<18}"
            f"{values['mae']:>14.6f}"
            f"{values['rmse']:>14.6f}"
            f"{values['wape']:>13.6f}%"
            f"{values['smape']:>13.6f}%"
        )

    hurdle_wape = float(hurdle_metrics["wape"])
    rolling_wape = float(rolling_metrics["wape"])
    improvement_points = rolling_wape - hurdle_wape
    relative_improvement = (
        improvement_points / rolling_wape * 100.0
        if rolling_wape != 0 else float("nan")
    )
    print()
    print(f"WAPE improvement over rolling_28 : {improvement_points:+.6f} points")
    print(f"relative WAPE improvement        : {relative_improvement:+.2f}%")

    header("PHASE 8.16 OCCURRENCE CLASSIFIER DIAGNOSTICS")
    for key in ("pr_auc", "roc_auc", "precision", "recall", "f1", "f2", "brier_score"):
        print(f"{key:<24}: {float(occurrence_metrics[key]):.6f}")
    print()
    print(f"TP : {int(occurrence_metrics['true_positives']):,}")
    print(f"FP : {int(occurrence_metrics['false_positives']):,}")
    print(f"TN : {int(occurrence_metrics['true_negatives']):,}")
    print(f"FN : {int(occurrence_metrics['false_negatives']):,}")

    header("PHASE 8.16 TEST ERROR DECOMPOSITION")
    print(
        f"zero-demand rows        : {errors['zero_demand_rows']:,} "
        f"({errors['zero_demand_share'] * 100:.2f}%)"
    )
    print(
        f"positive-demand rows    : {errors['positive_demand_rows']:,} "
        f"({errors['positive_demand_share'] * 100:.2f}%)"
    )
    print(f"hurdle zero-row abs err : {errors['hurdle_zero_demand_absolute_error']:,.2f}")
    print(f"roll28 zero-row abs err : {errors['rolling_28_zero_demand_absolute_error']:,.2f}")
    print(f"hurdle +row abs err     : {errors['hurdle_positive_demand_absolute_error']:,.2f}")
    print(f"roll28 +row abs err     : {errors['rolling_28_positive_demand_absolute_error']:,.2f}")

    if hurdle_wape < rolling_wape:
        winner = "hurdle_phase_8_15_final"
        statement = "HURDLE MODEL BEATS ROLLING_28 ON THE UNTOUCHED TEST SET"
    elif hurdle_wape > rolling_wape:
        winner = "rolling_28"
        statement = "ROLLING_28 BEATS THE HURDLE MODEL ON THE UNTOUCHED TEST SET"
    else:
        winner = "tie"
        statement = "HURDLE MODEL AND ROLLING_28 TIE ON TEST WAPE"

    header("PHASE 8.16 FINAL MODEL RESULT")
    print(f"rolling_28 WAPE            : {rolling_wape:.6f}%")
    print(f"hurdle WAPE                : {hurdle_wape:.6f}%")
    print(f"hurdle improvement         : {improvement_points:+.6f} WAPE points")
    print(f"relative improvement       : {relative_improvement:+.2f}%")
    print(f"winner                     : {winner}")
    print(f"result                     : {statement}")
    print()
    print("NO FURTHER MODEL/TUNING/THRESHOLD/FEATURE CHANGES ARE ALLOWED FROM THIS TEST RESULT.")

    payload = {
        "artifact_version": 1,
        "phase": "8.16",
        "generated_at_utc": utc_now(),
        "purpose": "one-time final unbiased test evaluation",
        "task": TASK_NAME,
        "target": TARGET_COLUMN,
        "evaluation_split": "test",
        "test_set_used": True,
        "one_time_evaluation": True,
        "source_git_commit": git_commit,
        "frozen_model": {
            "path": str(FINAL_MODEL_PATH.relative_to(PROJECT_ROOT)),
            "sha256": model_sha256,
            "phase": EXPECTED_PHASE,
            "architecture": EXPECTED_ARCHITECTURE,
            "threshold": threshold,
            "safe_predictor_count": len(safe_predictors),
            "safe_predictors": safe_predictors,
        },
        "test_partition": {
            "rows": int(len(frame)),
            "minimum_date": dates.min().date().isoformat(),
            "maximum_date": dates.max().date().isoformat(),
            "actual_positive_rows": int(occurrence_target.sum()),
            "actual_zero_rows": int((occurrence_target == 0).sum()),
        },
        "forecast_metrics": {
            "hurdle": {k: float(v) for k, v in hurdle_metrics.items()},
            "rolling_28": {k: float(v) for k, v in rolling_metrics.items()},
            "hurdle_improvement": {
                "wape_points": improvement_points,
                "relative_wape_improvement_pct": relative_improvement,
            },
        },
        "occurrence_classifier": {
            k: (v.item() if isinstance(v, np.generic) else v)
            for k, v in occurrence_metrics.items()
        },
        "error_decomposition": errors,
        "decision": {
            "winner_by_wape": winner,
            "statement": statement,
            "post_test_model_changes_allowed": False,
        },
        "protocol": {
            "git_working_tree_clean_before_test": True,
            "model_loaded_from_frozen_artifact": True,
            "preprocessor_refit_on_test": False,
            "occurrence_model_refit_on_test": False,
            "magnitude_model_refit_on_test": False,
            "threshold_retuned_on_test": False,
            "model_selection_on_test": False,
        },
        "software": {
            "python": sys.version.split()[0],
            "pandas": pd.__version__,
            "numpy": np.__version__,
            "scikit_learn": sklearn.__version__,
            "joblib": joblib.__version__,
            "platform": platform.platform(),
        },
    }

    FINAL_TEST_METRICS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with FINAL_TEST_METRICS_PATH.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, default=json_default)
        handle.write("\n")

    header("PHASE 8.16 AUDIT")
    print("frozen model loaded        : YES ✓")
    print("Git clean before test      : YES ✓")
    print("test.parquet read          : YES — ONE TIME ✓")
    print("preprocessor refit         : NO ✓")
    print("occurrence model refit     : NO ✓")
    print("magnitude model refit      : NO ✓")
    print("threshold retuned          : NO ✓")
    print("model selection performed  : NO ✓")
    print(f"metrics artifact           : {FINAL_TEST_METRICS_PATH}")
    print()
    print("PHASE 8.16 ONE-TIME FINAL TEST EVALUATION COMPLETE ✓")
    print("PHASE 8 MODELING IS NOW FROZEN.")


if __name__ == "__main__":
    main()
