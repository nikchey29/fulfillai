"""
FulfillAI chronological dataset splitting.

This module converts validated PostgreSQL analytical datasets into
chronological train / validation / test partitions.

Important principles
--------------------
- No random train/test splitting.
- Inventory eligibility is applied before splitting.
- Every eligible row must belong to exactly one partition.
- Split boundaries may not overlap.
- Rows may not disappear during splitting.
- Chronological ordering must be preserved.
- Train dates must precede validation dates.
- Validation dates must precede test dates.

This module does NOT write Parquet files. Materialization belongs to
build_features.py.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass

import pandas as pd

from .config import (
    TEST_END_DATE,
    TEST_START_DATE,
    TRAIN_END_DATE,
    VALIDATION_END_DATE,
    VALIDATION_START_DATE,
    DatasetConfig,
    dataset_names,
    get_dataset_config,
)
from .extract import extract_dataset
from .validate import (
    FeatureValidationError,
    eligible_frame,
    validate_dataset,
)


# ======================================================================
# Exceptions
# ======================================================================


class FeatureSplitError(RuntimeError):
    """Raised when chronological dataset splitting is invalid."""


# ======================================================================
# Split container
# ======================================================================


@dataclass(frozen=True)
class DatasetSplits:
    """Train, validation and test partitions for one dataset."""

    dataset: str
    train: pd.DataFrame
    validation: pd.DataFrame
    test: pd.DataFrame

    @property
    def total_rows(self) -> int:
        """Total rows across all partitions."""

        return (
            len(self.train)
            + len(self.validation)
            + len(self.test)
        )


@dataclass(frozen=True)
class SplitSummary:
    """Human-readable statistics for a completed split."""

    dataset: str
    source_rows: int
    eligible_rows: int

    train_rows: int
    validation_rows: int
    test_rows: int

    train_min: str
    train_max: str

    validation_min: str
    validation_max: str

    test_min: str
    test_max: str


# ======================================================================
# Boundary helpers
# ======================================================================


def _utc_date(value: str) -> pd.Timestamp:
    """Convert a YYYY-MM-DD configuration value to UTC midnight."""

    return pd.Timestamp(
        value,
        tz="UTC",
    )


def validate_split_configuration() -> None:
    """
    Validate chronological split boundaries.

    Current intended layout:

        TRAIN
            <= 2026-04-30

        VALIDATION
            2026-05-01 through 2026-05-31

        TEST
            2026-06-01 through 2026-07-31
    """

    train_end = _utc_date(TRAIN_END_DATE)

    validation_start = _utc_date(
        VALIDATION_START_DATE
    )

    validation_end = _utc_date(
        VALIDATION_END_DATE
    )

    test_start = _utc_date(
        TEST_START_DATE
    )

    test_end = _utc_date(
        TEST_END_DATE
    )

    if not (
        train_end
        < validation_start
        <= validation_end
        < test_start
        <= test_end
    ):
        raise FeatureSplitError(
            "Invalid chronological split configuration."
        )

    # We intentionally require contiguous calendar boundaries.
    # This prevents silent date gaps between partitions.

    if (
        train_end + pd.Timedelta(days=1)
        != validation_start
    ):
        raise FeatureSplitError(
            "Train and validation boundaries are not contiguous."
        )

    if (
        validation_end + pd.Timedelta(days=1)
        != test_start
    ):
        raise FeatureSplitError(
            "Validation and test boundaries are not contiguous."
        )


# Validate static split configuration during import.
validate_split_configuration()


# ======================================================================
# Date preparation
# ======================================================================


def _normalized_split_dates(
    frame: pd.DataFrame,
    config: DatasetConfig,
) -> pd.Series:
    """
    Return the dataset split column as normalized UTC calendar dates.
    """

    if config.split_column not in frame.columns:
        raise FeatureSplitError(
            f"{config.name}: split column "
            f"{config.split_column!r} is missing."
        )

    try:
        dates = pd.to_datetime(
            frame[config.split_column],
            errors="raise",
            utc=True,
        )

    except Exception as exc:
        raise FeatureSplitError(
            f"{config.name}: unable to parse split column "
            f"{config.split_column!r}."
        ) from exc

    if dates.isna().any():
        count = int(
            dates.isna().sum()
        )

        raise FeatureSplitError(
            f"{config.name}: split column contains "
            f"{count:,} null date(s)."
        )

    return dates.dt.normalize()


# ======================================================================
# Deterministic ordering
# ======================================================================


def _sort_columns(
    config: DatasetConfig,
) -> list[str]:
    """
    Return deterministic row ordering for a dataset.

    Split date is first, followed by the configured primary key.
    """

    candidates = (
        config.split_column,
        *config.primary_key,
    )

    seen: set[str] = set()
    columns: list[str] = []

    for column in candidates:
        if column not in seen:
            seen.add(column)
            columns.append(column)

    return columns


def _sort_partition(
    frame: pd.DataFrame,
    config: DatasetConfig,
) -> pd.DataFrame:
    """Sort one partition deterministically and reset its row index."""

    return (
        frame
        .sort_values(
            by=_sort_columns(config),
            kind="stable",
        )
        .reset_index(drop=True)
    )


# ======================================================================
# Split integrity
# ======================================================================


def _validate_partition_non_empty(
    partition: pd.DataFrame,
    *,
    dataset_name: str,
    partition_name: str,
) -> None:
    """Reject an unexpectedly empty ML partition."""

    if partition.empty:
        raise FeatureSplitError(
            f"{dataset_name}: {partition_name} partition "
            "contains zero rows."
        )


def _partition_date_range(
    frame: pd.DataFrame,
    config: DatasetConfig,
) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Return minimum and maximum normalized dates."""

    dates = _normalized_split_dates(
        frame,
        config,
    )

    return (
        dates.min(),
        dates.max(),
    )


def validate_split_integrity(
    splits: DatasetSplits,
    config: DatasetConfig,
    *,
    expected_rows: int,
) -> None:
    """
    Prove that train / validation / test partitions are safe.

    Checks
    ------
    1. Every partition contains rows.
    2. No rows disappeared.
    3. Train occurs strictly before validation.
    4. Validation occurs strictly before test.
    5. Every partition respects its configured boundary.
    6. Each partition remains chronologically ordered.
    """

    _validate_partition_non_empty(
        splits.train,
        dataset_name=config.name,
        partition_name="train",
    )

    _validate_partition_non_empty(
        splits.validation,
        dataset_name=config.name,
        partition_name="validation",
    )

    _validate_partition_non_empty(
        splits.test,
        dataset_name=config.name,
        partition_name="test",
    )

    # --------------------------------------------------------------
    # Row conservation
    # --------------------------------------------------------------

    if splits.total_rows != expected_rows:
        raise FeatureSplitError(
            f"{config.name}: row conservation failed. "
            f"Expected {expected_rows:,} eligible rows but "
            f"partitions contain {splits.total_rows:,}."
        )

    # --------------------------------------------------------------
    # Date ranges
    # --------------------------------------------------------------

    train_min, train_max = _partition_date_range(
        splits.train,
        config,
    )

    validation_min, validation_max = (
        _partition_date_range(
            splits.validation,
            config,
        )
    )

    test_min, test_max = _partition_date_range(
        splits.test,
        config,
    )

    # --------------------------------------------------------------
    # Strict temporal separation
    # --------------------------------------------------------------

    if not train_max < validation_min:
        raise FeatureSplitError(
            f"{config.name}: train/validation chronology failed: "
            f"{train_max} !< {validation_min}"
        )

    if not validation_max < test_min:
        raise FeatureSplitError(
            f"{config.name}: validation/test chronology failed: "
            f"{validation_max} !< {test_min}"
        )

    # --------------------------------------------------------------
    # Configured boundary enforcement
    # --------------------------------------------------------------

    train_end = _utc_date(
        TRAIN_END_DATE
    )

    validation_start = _utc_date(
        VALIDATION_START_DATE
    )

    validation_end = _utc_date(
        VALIDATION_END_DATE
    )

    test_start = _utc_date(
        TEST_START_DATE
    )

    test_end = _utc_date(
        TEST_END_DATE
    )

    if train_max > train_end:
        raise FeatureSplitError(
            f"{config.name}: train partition contains dates "
            f"after {TRAIN_END_DATE}."
        )

    if validation_min < validation_start:
        raise FeatureSplitError(
            f"{config.name}: validation contains dates "
            f"before {VALIDATION_START_DATE}."
        )

    if validation_max > validation_end:
        raise FeatureSplitError(
            f"{config.name}: validation contains dates "
            f"after {VALIDATION_END_DATE}."
        )

    if test_min < test_start:
        raise FeatureSplitError(
            f"{config.name}: test contains dates "
            f"before {TEST_START_DATE}."
        )

    if test_max > test_end:
        raise FeatureSplitError(
            f"{config.name}: test contains dates "
            f"after {TEST_END_DATE}."
        )

    # --------------------------------------------------------------
    # Ordering inside partitions
    # --------------------------------------------------------------

    for partition_name, partition in (
        ("train", splits.train),
        ("validation", splits.validation),
        ("test", splits.test),
    ):

        dates = _normalized_split_dates(
            partition,
            config,
        )

        if not dates.is_monotonic_increasing:
            raise FeatureSplitError(
                f"{config.name}: {partition_name} partition "
                "is not chronologically ordered."
            )


# ======================================================================
# Main splitting logic
# ======================================================================


def split_dataset(
    frame: pd.DataFrame,
    config: DatasetConfig,
    *,
    validate_source: bool = True,
) -> DatasetSplits:
    """
    Split one source DataFrame chronologically.

    Validation occurs before eligibility filtering so structural errors
    in the source view cannot be silently hidden.

    Inventory-risk rows are filtered using ml_feature_eligible = 1 before
    splitting.
    """

    validate_split_configuration()

    if validate_source:
        try:
            validate_dataset(
                frame,
                config,
            )

        except FeatureValidationError as exc:
            raise FeatureSplitError(
                f"{config.name}: source validation failed before split."
            ) from exc

    eligible = eligible_frame(
        frame,
        config,
    )

    dates = _normalized_split_dates(
        eligible,
        config,
    )

    train_end = _utc_date(
        TRAIN_END_DATE
    )

    validation_start = _utc_date(
        VALIDATION_START_DATE
    )

    validation_end = _utc_date(
        VALIDATION_END_DATE
    )

    test_start = _utc_date(
        TEST_START_DATE
    )

    test_end = _utc_date(
        TEST_END_DATE
    )

    # --------------------------------------------------------------
    # Partition masks
    # --------------------------------------------------------------

    train_mask = (
        dates <= train_end
    )

    validation_mask = (
        (dates >= validation_start)
        & (dates <= validation_end)
    )

    test_mask = (
        (dates >= test_start)
        & (dates <= test_end)
    )

    # --------------------------------------------------------------
    # Every row must belong to exactly one split.
    # --------------------------------------------------------------

    membership_count = (
        train_mask.astype("int8")
        + validation_mask.astype("int8")
        + test_mask.astype("int8")
    )

    invalid_membership = (
        membership_count != 1
    )

    if invalid_membership.any():

        examples = (
            eligible.loc[
                invalid_membership,
                [config.split_column],
            ]
            .head(10)
            .to_dict("records")
        )

        raise FeatureSplitError(
            f"{config.name}: "
            f"{int(invalid_membership.sum()):,} eligible row(s) "
            "do not belong to exactly one chronological partition. "
            f"Examples: {examples}"
        )

    # --------------------------------------------------------------
    # Materialize in-memory partitions.
    # --------------------------------------------------------------

    train = _sort_partition(
        eligible.loc[train_mask].copy(),
        config,
    )

    validation = _sort_partition(
        eligible.loc[validation_mask].copy(),
        config,
    )

    test = _sort_partition(
        eligible.loc[test_mask].copy(),
        config,
    )

    splits = DatasetSplits(
        dataset=config.name,
        train=train,
        validation=validation,
        test=test,
    )

    validate_split_integrity(
        splits,
        config,
        expected_rows=len(eligible),
    )

    return splits


# ======================================================================
# Multi-dataset helper
# ======================================================================


def split_all_datasets() -> dict[str, DatasetSplits]:
    """
    Extract, validate and split every configured ML dataset.
    """

    results: dict[str, DatasetSplits] = {}

    for name in dataset_names():

        config = get_dataset_config(
            name
        )

        frame = extract_dataset(
            config
        )

        results[name] = split_dataset(
            frame,
            config,
        )

    return results


# ======================================================================
# Summary helpers
# ======================================================================


def _format_date(
    value: pd.Timestamp,
) -> str:
    """Format a split date for CLI output."""

    return value.strftime(
        "%Y-%m-%d"
    )


def summarize_splits(
    source_frame: pd.DataFrame,
    splits: DatasetSplits,
    config: DatasetConfig,
) -> SplitSummary:
    """Build summary metadata for one split operation."""

    eligible = eligible_frame(
        source_frame,
        config,
    )

    train_min, train_max = _partition_date_range(
        splits.train,
        config,
    )

    validation_min, validation_max = (
        _partition_date_range(
            splits.validation,
            config,
        )
    )

    test_min, test_max = _partition_date_range(
        splits.test,
        config,
    )

    return SplitSummary(
        dataset=config.name,
        source_rows=len(source_frame),
        eligible_rows=len(eligible),

        train_rows=len(splits.train),
        validation_rows=len(splits.validation),
        test_rows=len(splits.test),

        train_min=_format_date(train_min),
        train_max=_format_date(train_max),

        validation_min=_format_date(validation_min),
        validation_max=_format_date(validation_max),

        test_min=_format_date(test_min),
        test_max=_format_date(test_max),
    )


def print_split_summary(
    summary: SplitSummary,
) -> None:
    """Print chronological split statistics."""

    print()
    print("=" * 76)
    print(
        f"FulfillAI chronological split: {summary.dataset}"
    )
    print("=" * 76)

    print(
        f"source rows        : {summary.source_rows:,}"
    )

    print(
        f"ML-eligible rows   : {summary.eligible_rows:,}"
    )

    print()

    print(
        f"train rows         : {summary.train_rows:,}"
    )
    print(
        f"train range        : "
        f"{summary.train_min} -> {summary.train_max}"
    )

    print()

    print(
        f"validation rows    : {summary.validation_rows:,}"
    )
    print(
        f"validation range   : "
        f"{summary.validation_min} -> "
        f"{summary.validation_max}"
    )

    print()

    print(
        f"test rows          : {summary.test_rows:,}"
    )
    print(
        f"test range         : "
        f"{summary.test_min} -> {summary.test_max}"
    )

    print()

    print(
        f"partition total    : "
        f"{summary.train_rows + summary.validation_rows + summary.test_rows:,}"
    )

    print("-" * 76)
    print("ROW CONSERVATION PASSED ✓")
    print("CHRONOLOGICAL SEPARATION PASSED ✓")
    print("SPLIT BOUNDARIES PASSED ✓")
    print("=" * 76)


# ======================================================================
# CLI
# ======================================================================


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(
        description=(
            "Create chronological FulfillAI ML dataset splits."
        )
    )

    parser.add_argument(
        "--dataset",
        choices=dataset_names(),
        default=None,
        help=(
            "Split one configured dataset. "
            "If omitted, all datasets are processed."
        ),
    )

    return parser.parse_args()


def _run_one(
    dataset_name: str,
) -> DatasetSplits:
    """Extract, validate and split one dataset."""

    config = get_dataset_config(
        dataset_name
    )

    print(
        f"\nExtracting {dataset_name}..."
    )

    frame = extract_dataset(
        config
    )

    print(
        f"Validating {dataset_name}..."
    )

    # split_dataset performs the complete source validation internally.
    splits = split_dataset(
        frame,
        config,
        validate_source=True,
    )

    summary = summarize_splits(
        frame,
        splits,
        config,
    )

    print_split_summary(
        summary
    )

    return splits


def main() -> None:
    """CLI entrypoint."""

    args = parse_args()

    if args.dataset is not None:

        _run_one(
            args.dataset
        )

        return

    print(
        "Creating chronological splits for all FulfillAI ML datasets..."
    )

    results: list[
        tuple[str, DatasetSplits]
    ] = []

    for name in dataset_names():

        splits = _run_one(
            name
        )

        results.append(
            (name, splits)
        )

    print()
    print("=" * 76)
    print("ALL CHRONOLOGICAL DATASET SPLITS PASSED ✓")
    print("=" * 76)

    for name, splits in results:

        print(
            f"{name:<24} "
            f"train={len(splits.train):>9,}  "
            f"validation={len(splits.validation):>8,}  "
            f"test={len(splits.test):>8,}"
        )


if __name__ == "__main__":
    main()