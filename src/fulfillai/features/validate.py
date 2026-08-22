"""
FulfillAI ML feature-source validation.

This module validates analytical datasets after PostgreSQL extraction
and before train/validation/test materialization.

Validation covers:

- required schema
- empty datasets
- primary-key uniqueness
- null primary-key values
- chronological ordering
- simulation date boundaries
- target validity
- binary classification labels
- non-negative forecasting targets
- inventory ML eligibility
- predictor leakage protection
- non-finite numeric values
- constant/degenerate feature diagnostics

Validation does not write files or train models.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd

from .config import (
    DATASET_CONFIGS,
    TEST_END_DATE,
    DatasetConfig,
    dataset_names,
    get_dataset_config,
)
from .extract import extract_dataset


# ======================================================================
# Exceptions
# ======================================================================


class FeatureValidationError(RuntimeError):
    """Raised when a feature dataset violates its data contract."""


# ======================================================================
# Validation result
# ======================================================================


@dataclass(frozen=True)
class ValidationResult:
    """Summary of a completed dataset validation."""

    dataset: str
    source_view: str
    rows: int
    columns: int
    eligible_rows: int
    duplicate_primary_keys: int
    null_primary_keys: int
    null_targets: int
    predictor_columns: int
    constant_predictors: int
    split_min: str
    split_max: str


# ======================================================================
# Generic helpers
# ======================================================================


def _require_columns(
    frame: pd.DataFrame,
    columns: Iterable[str],
    *,
    dataset_name: str,
) -> None:
    """Ensure all requested columns exist."""

    required = set(columns)
    available = set(frame.columns)

    missing = sorted(required - available)

    if missing:
        raise FeatureValidationError(
            f"{dataset_name}: required columns are missing: {missing}"
        )


def _duplicate_primary_key_count(
    frame: pd.DataFrame,
    config: DatasetConfig,
) -> int:
    """Count rows participating in duplicated primary-key grains."""

    return int(
        frame.duplicated(
            subset=list(config.primary_key),
            keep=False,
        ).sum()
    )


def _null_primary_key_count(
    frame: pd.DataFrame,
    config: DatasetConfig,
) -> int:
    """Count rows containing any null primary-key value."""

    return int(
        frame[list(config.primary_key)]
        .isna()
        .any(axis=1)
        .sum()
    )


def _parse_split_column(
    frame: pd.DataFrame,
    config: DatasetConfig,
) -> pd.Series:
    """Parse the configured chronological split column."""

    try:
        parsed = pd.to_datetime(
            frame[config.split_column],
            errors="raise",
            utc=True,
        )

    except Exception as exc:
        raise FeatureValidationError(
            f"{config.name}: split column "
            f"{config.split_column!r} cannot be parsed as datetime."
        ) from exc

    if parsed.isna().any():
        count = int(parsed.isna().sum())

        raise FeatureValidationError(
            f"{config.name}: split column "
            f"{config.split_column!r} contains {count:,} null value(s)."
        )

    return parsed


# ======================================================================
# Eligibility
# ======================================================================


def eligible_mask(
    frame: pd.DataFrame,
    config: DatasetConfig,
) -> pd.Series:
    """
    Return rows eligible for ML validation/materialization.

    Currently FulfillAI has one filtered feature source:

        inventory_risk -> ml_feature_eligible = 1

    Other datasets use every extracted row.
    """

    if config.eligibility_filter is None:
        return pd.Series(
            True,
            index=frame.index,
            dtype=bool,
        )

    if (
        config.name == "inventory_risk"
        and config.eligibility_filter == "ml_feature_eligible = 1"
    ):
        _require_columns(
            frame,
            ("ml_feature_eligible",),
            dataset_name=config.name,
        )

        values = pd.to_numeric(
            frame["ml_feature_eligible"],
            errors="coerce",
        )

        invalid = ~values.isin([0, 1])

        if invalid.any():
            examples = (
                frame.loc[
                    invalid,
                    "ml_feature_eligible",
                ]
                .drop_duplicates()
                .head(10)
                .tolist()
            )

            raise FeatureValidationError(
                f"{config.name}: ml_feature_eligible contains "
                f"values outside {{0, 1}}: {examples}"
            )

        return values.eq(1)

    raise FeatureValidationError(
        f"{config.name}: unsupported eligibility filter "
        f"{config.eligibility_filter!r}."
    )


def eligible_frame(
    frame: pd.DataFrame,
    config: DatasetConfig,
) -> pd.DataFrame:
    """
    Return ML-eligible rows.

    The returned DataFrame is a defensive copy so later feature-pipeline
    operations cannot mutate the raw extraction frame accidentally.
    """

    mask = eligible_mask(
        frame,
        config,
    )

    result = frame.loc[mask].copy()

    if result.empty:
        raise FeatureValidationError(
            f"{config.name}: eligibility filtering produced zero rows."
        )

    return result


# ======================================================================
# Predictor selection / leakage protection
# ======================================================================


def predictor_columns(
    frame: pd.DataFrame,
    config: DatasetConfig,
) -> tuple[str, ...]:
    """
    Return columns permitted to enter the predictor matrix.

    Automatically excludes:

    - configured targets
    - explicitly forbidden leakage/outcome columns
    - raw primary-key columns
    - raw chronological split column

    Calendar-derived features already present in the SQL model remain
    available.
    """

    protected = set(config.excluded_feature_columns)

    protected.update(config.target_columns)
    protected.update(config.primary_key)
    protected.add(config.split_column)

    predictors = tuple(
        column
        for column in frame.columns
        if column not in protected
    )

    if not predictors:
        raise FeatureValidationError(
            f"{config.name}: no predictor columns remain after "
            "leakage protection."
        )

    return predictors


def validate_leakage_contract(
    frame: pd.DataFrame,
    config: DatasetConfig,
) -> tuple[str, ...]:
    """
    Prove that known outcome/future columns cannot enter predictors.
    """

    predictors = predictor_columns(
        frame,
        config,
    )

    predictor_set = set(predictors)

    prohibited = (
        set(config.excluded_feature_columns)
        | set(config.target_columns)
    )

    leaked = sorted(
        predictor_set & prohibited
    )

    if leaked:
        raise FeatureValidationError(
            f"{config.name}: prohibited columns entered predictor set: "
            f"{leaked}"
        )

    # Additional defense for future-derived ML columns.
    suspicious_future_columns = sorted(
        column
        for column in predictors
        if (
            column.startswith("target_")
            or column.startswith("future_")
        )
    )

    if suspicious_future_columns:
        raise FeatureValidationError(
            f"{config.name}: future/target columns are present in the "
            f"predictor set: {suspicious_future_columns}"
        )

    return predictors


# ======================================================================
# Primary-key / grain validation
# ======================================================================


def validate_primary_key(
    frame: pd.DataFrame,
    config: DatasetConfig,
) -> tuple[int, int]:
    """Validate uniqueness and completeness of the configured grain."""

    _require_columns(
        frame,
        config.primary_key,
        dataset_name=config.name,
    )

    null_keys = _null_primary_key_count(
        frame,
        config,
    )

    if null_keys:
        raise FeatureValidationError(
            f"{config.name}: {null_keys:,} row(s) contain null values "
            f"in primary key {config.primary_key}."
        )

    duplicate_keys = _duplicate_primary_key_count(
        frame,
        config,
    )

    if duplicate_keys:
        sample = (
            frame.loc[
                frame.duplicated(
                    subset=list(config.primary_key),
                    keep=False,
                ),
                list(config.primary_key),
            ]
            .head(10)
            .to_dict("records")
        )

        raise FeatureValidationError(
            f"{config.name}: {duplicate_keys:,} row(s) participate "
            f"in duplicate dataset grains. Example(s): {sample}"
        )

    return duplicate_keys, null_keys


# ======================================================================
# Chronology validation
# ======================================================================


def validate_chronology(
    frame: pd.DataFrame,
    config: DatasetConfig,
) -> tuple[pd.Series, str, str]:
    """Validate chronological ordering and date boundaries."""

    split_values = _parse_split_column(
        frame,
        config,
    )

    if not split_values.is_monotonic_increasing:
        raise FeatureValidationError(
            f"{config.name}: extracted rows are not ordered "
            f"chronologically by {config.split_column!r}."
        )

    minimum = split_values.min()
    maximum = split_values.max()

    allowed_max = pd.Timestamp(
        TEST_END_DATE,
        tz="UTC",
    )

    if maximum > allowed_max:
        raise FeatureValidationError(
            f"{config.name}: maximum split date {maximum} exceeds "
            f"configured simulation/test boundary {allowed_max}."
        )

    return (
        split_values,
        str(minimum),
        str(maximum),
    )


# ======================================================================
# Target validation
# ======================================================================


def _validate_binary_target(
    series: pd.Series,
    *,
    dataset_name: str,
    target_name: str,
) -> None:
    """Validate a binary classification target."""

    numeric = pd.to_numeric(
        series,
        errors="coerce",
    )

    invalid_numeric = numeric.isna()

    if invalid_numeric.any():
        count = int(
            invalid_numeric.sum()
        )

        raise FeatureValidationError(
            f"{dataset_name}: target {target_name!r} has "
            f"{count:,} null/non-numeric value(s) among eligible rows."
        )

    invalid_values = ~numeric.isin([0, 1])

    if invalid_values.any():
        examples = (
            numeric.loc[invalid_values]
            .drop_duplicates()
            .head(10)
            .tolist()
        )

        raise FeatureValidationError(
            f"{dataset_name}: target {target_name!r} must be binary "
            f"0/1. Invalid values: {examples}"
        )


def _validate_forecasting_target(
    series: pd.Series,
    *,
    dataset_name: str,
    target_name: str,
) -> None:
    """Validate a non-negative forecasting target."""

    numeric = pd.to_numeric(
        series,
        errors="coerce",
    )

    if numeric.isna().any():
        count = int(
            numeric.isna().sum()
        )

        raise FeatureValidationError(
            f"{dataset_name}: forecasting target {target_name!r} "
            f"contains {count:,} null/non-numeric value(s)."
        )

    negative = numeric < 0

    if negative.any():
        count = int(
            negative.sum()
        )

        raise FeatureValidationError(
            f"{dataset_name}: forecasting target {target_name!r} "
            f"contains {count:,} negative value(s)."
        )

    array = numeric.to_numpy(
        dtype=float,
        na_value=np.nan,
    )

    if not np.isfinite(array).all():
        raise FeatureValidationError(
            f"{dataset_name}: forecasting target {target_name!r} "
            "contains infinite values."
        )


def validate_targets(
    frame: pd.DataFrame,
    config: DatasetConfig,
) -> int:
    """
    Validate targets on ML-eligible rows.

    This distinction is critical for inventory risk: boundary rows that
    lack sufficient historical/future observations may legitimately
    contain null target values, but they have ml_feature_eligible = 0
    and will never enter model training.
    """

    _require_columns(
        frame,
        config.target_columns,
        dataset_name=config.name,
    )

    eligible = eligible_frame(
        frame,
        config,
    )

    null_targets = int(
        eligible[
            list(config.target_columns)
        ]
        .isna()
        .sum()
        .sum()
    )

    if null_targets:
        raise FeatureValidationError(
            f"{config.name}: eligible rows contain "
            f"{null_targets:,} null target value(s)."
        )

    for target in config.target_columns:

        if config.task_type == "classification":
            _validate_binary_target(
                eligible[target],
                dataset_name=config.name,
                target_name=target,
            )

        elif config.task_type == "forecasting":
            _validate_forecasting_target(
                eligible[target],
                dataset_name=config.name,
                target_name=target,
            )

        else:
            raise FeatureValidationError(
                f"{config.name}: unsupported task type "
                f"{config.task_type!r}."
            )

    return null_targets


# ======================================================================
# Numeric quality validation
# ======================================================================


def validate_numeric_finiteness(
    frame: pd.DataFrame,
    config: DatasetConfig,
    predictors: tuple[str, ...],
) -> None:
    """
    Reject positive/negative infinity in numeric predictors.

    Missing predictor values are not globally rejected here because lag
    features may legitimately contain null values near historical
    boundaries. Handling/imputation belongs to the later ML preprocessing
    layer.
    """

    numeric_predictors = [
        column
        for column in predictors
        if pd.api.types.is_numeric_dtype(
            frame[column]
        )
    ]

    failures: list[str] = []

    for column in numeric_predictors:

        numeric = pd.to_numeric(
            frame[column],
            errors="coerce",
        )

        non_null = numeric.dropna()

        if non_null.empty:
            continue

        values = non_null.to_numpy(
            dtype=float,
        )

        if not np.isfinite(values).all():
            failures.append(column)

    if failures:
        raise FeatureValidationError(
            f"{config.name}: non-finite numeric values detected in "
            f"predictor column(s): {sorted(failures)}"
        )


# ======================================================================
# Inventory-specific validation
# ======================================================================


def validate_inventory_eligibility(
    frame: pd.DataFrame,
    config: DatasetConfig,
) -> None:
    """Validate inventory-risk temporal eligibility rules."""

    if config.name != "inventory_risk":
        return

    required = (
        "ml_feature_eligible",
        "historical_observation_days_28d",
        "future_observation_days",
        "target_stockout_next_7d",
        "target_reorder_breach_next_7d",
    )

    _require_columns(
        frame,
        required,
        dataset_name=config.name,
    )

    eligible = eligible_frame(
        frame,
        config,
    )

    historical_days = pd.to_numeric(
        eligible["historical_observation_days_28d"],
        errors="coerce",
    )

    future_days = pd.to_numeric(
        eligible["future_observation_days"],
        errors="coerce",
    )

    invalid_history = (
        historical_days.ne(28)
        | historical_days.isna()
    )

    invalid_future = (
        future_days.ne(7)
        | future_days.isna()
    )

    if invalid_history.any():
        raise FeatureValidationError(
            f"{config.name}: "
            f"{int(invalid_history.sum()):,} ML-eligible row(s) "
            "do not contain a complete 28-day historical window."
        )

    if invalid_future.any():
        raise FeatureValidationError(
            f"{config.name}: "
            f"{int(invalid_future.sum()):,} ML-eligible row(s) "
            "do not contain a complete seven-day future target window."
        )


# ======================================================================
# Diagnostics
# ======================================================================


def constant_predictor_columns(
    frame: pd.DataFrame,
    predictors: Iterable[str],
) -> tuple[str, ...]:
    """
    Return predictor columns having at most one distinct non-null value.

    Constant features are diagnostic rather than fatal at this stage.
    """

    constants: list[str] = []

    for column in predictors:

        unique_count = frame[column].nunique(
            dropna=True,
        )

        if unique_count <= 1:
            constants.append(column)

    return tuple(constants)


# ======================================================================
# Complete validation
# ======================================================================


def validate_dataset(
    frame: pd.DataFrame,
    config: DatasetConfig,
) -> ValidationResult:
    """
    Run the complete source validation suite for one ML dataset.

    Raises FeatureValidationError immediately when a critical data
    contract is violated.
    """

    if frame.empty:
        raise FeatureValidationError(
            f"{config.name}: extracted DataFrame is empty."
        )

    _require_columns(
        frame,
        config.required_columns,
        dataset_name=config.name,
    )

    duplicate_keys, null_keys = validate_primary_key(
        frame,
        config,
    )

    _, split_min, split_max = validate_chronology(
        frame,
        config,
    )

    null_targets = validate_targets(
        frame,
        config,
    )

    validate_inventory_eligibility(
        frame,
        config,
    )

    predictors = validate_leakage_contract(
        frame,
        config,
    )

    eligible = eligible_frame(
        frame,
        config,
    )

    validate_numeric_finiteness(
        eligible,
        config,
        predictors,
    )

    constants = constant_predictor_columns(
        eligible,
        predictors,
    )

    return ValidationResult(
        dataset=config.name,
        source_view=config.source_view,
        rows=len(frame),
        columns=len(frame.columns),
        eligible_rows=len(eligible),
        duplicate_primary_keys=duplicate_keys,
        null_primary_keys=null_keys,
        null_targets=null_targets,
        predictor_columns=len(predictors),
        constant_predictors=len(constants),
        split_min=split_min,
        split_max=split_max,
    )


# ======================================================================
# Output
# ======================================================================


def print_validation_result(
    result: ValidationResult,
) -> None:
    """Print a concise validation summary."""

    print()
    print("=" * 72)
    print(
        f"FulfillAI feature validation: {result.dataset}"
    )
    print("=" * 72)
    print(
        f"source view             : {result.source_view}"
    )
    print(
        f"source rows             : {result.rows:,}"
    )
    print(
        f"columns                 : {result.columns:,}"
    )
    print(
        f"ML-eligible rows        : {result.eligible_rows:,}"
    )
    print(
        f"predictor columns       : {result.predictor_columns:,}"
    )
    print(
        f"duplicate grains        : "
        f"{result.duplicate_primary_keys:,}"
    )
    print(
        f"null primary keys       : "
        f"{result.null_primary_keys:,}"
    )
    print(
        f"null eligible targets   : "
        f"{result.null_targets:,}"
    )
    print(
        f"constant predictors     : "
        f"{result.constant_predictors:,}"
    )
    print(
        f"minimum date            : {result.split_min}"
    )
    print(
        f"maximum date            : {result.split_max}"
    )
    print("-" * 72)
    print("VALIDATION PASSED ✓")
    print("=" * 72)


# ======================================================================
# CLI
# ======================================================================


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""

    parser = argparse.ArgumentParser(
        description=(
            "Validate FulfillAI PostgreSQL ML feature sources."
        )
    )

    parser.add_argument(
        "--dataset",
        choices=dataset_names(),
        default=None,
        help=(
            "Validate one dataset. "
            "If omitted, every configured dataset is validated."
        ),
    )

    return parser.parse_args()


def _validate_one(
    dataset_name: str,
) -> ValidationResult:
    """Extract and validate one configured dataset."""

    config = get_dataset_config(
        dataset_name
    )

    print(
        f"\nExtracting {dataset_name}..."
    )

    frame = extract_dataset(
        config
    )

    result = validate_dataset(
        frame,
        config,
    )

    print_validation_result(
        result
    )

    return result


def main() -> None:
    """CLI entrypoint."""

    args = parse_args()

    if args.dataset is not None:
        _validate_one(
            args.dataset
        )
        return

    print(
        "Validating all FulfillAI ML feature sources..."
    )

    results: list[ValidationResult] = []

    for name in dataset_names():
        results.append(
            _validate_one(name)
        )

    print()
    print("=" * 72)
    print("ALL FEATURE SOURCE VALIDATIONS PASSED ✓")
    print("=" * 72)

    for result in results:
        print(
            f"{result.dataset:<24} "
            f"{result.eligible_rows:>10,} eligible rows"
        )


if __name__ == "__main__":
    main()