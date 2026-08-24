"""
FulfillAI machine-learning dataset loading utilities.

This module is the boundary between Phase 7 feature materialization and
Phase 8 model training.

Responsibilities
----------------
- load train / validation / test Parquet datasets
- load Phase 7 metadata contracts
- verify expected columns
- verify row counts
- protect against target leakage
- expose predictor/target matrices consistently
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import pandas as pd

from .config import (
    MLTaskConfig,
    get_task_config,
    metadata_path,
    split_path,
)


SplitName = Literal[
    "train",
    "validation",
    "test",
]


VALID_SPLITS: tuple[SplitName, ...] = (
    "train",
    "validation",
    "test",
)


# ======================================================================
# Exceptions
# ======================================================================


class MLDataError(RuntimeError):
    """Raised when a Phase 7 ML dataset violates its contract."""


# ======================================================================
# Containers
# ======================================================================


@dataclass(frozen=True)
class LoadedSplit:
    """
    One loaded ML dataset partition.
    """

    name: SplitName

    frame: pd.DataFrame

    predictors: tuple[str, ...]

    target_column: str

    @property
    def X(self) -> pd.DataFrame:
        """Return model predictors."""

        return self.frame.loc[
            :,
            list(self.predictors),
        ].copy()

    @property
    def y(self) -> pd.Series:
        """Return model target."""

        return (
            self.frame[
                self.target_column
            ]
            .copy()
            .rename(
                self.target_column
            )
        )

    @property
    def rows(self) -> int:
        """Return row count."""

        return len(self.frame)

    @property
    def columns(self) -> int:
        """Return column count."""

        return len(
            self.frame.columns
        )


@dataclass(frozen=True)
class TaskDataset:
    """
    Complete train/validation/test dataset for one ML task.
    """

    task: MLTaskConfig

    predictors: tuple[str, ...]

    metadata: dict

    train: LoadedSplit

    validation: LoadedSplit

    test: LoadedSplit

    def split(
        self,
        name: SplitName,
    ) -> LoadedSplit:
        """Return a named partition."""

        if name == "train":
            return self.train

        if name == "validation":
            return self.validation

        if name == "test":
            return self.test

        raise ValueError(
            f"Unsupported split: {name!r}"
        )


# ======================================================================
# Metadata
# ======================================================================


def load_metadata(
    task: MLTaskConfig,
) -> dict:
    """
    Load Phase 7 reproducibility metadata.
    """

    path = metadata_path(
        task
    )

    if not path.exists():

        raise MLDataError(
            f"{task.name}: metadata file "
            f"does not exist: {path}"
        )

    try:

        with path.open(
            "r",
            encoding="utf-8",
        ) as handle:

            metadata = json.load(
                handle
            )

    except json.JSONDecodeError as exc:

        raise MLDataError(
            f"{task.name}: invalid JSON "
            f"metadata: {path}"
        ) from exc

    if not isinstance(
        metadata,
        dict,
    ):

        raise MLDataError(
            f"{task.name}: metadata root "
            "must be a JSON object."
        )

    return metadata


def _metadata_contract(
    metadata: dict,
    task: MLTaskConfig,
) -> dict:
    """Return metadata contract."""

    contract = metadata.get(
        "contract"
    )

    if not isinstance(
        contract,
        dict,
    ):

        raise MLDataError(
            f"{task.name}: metadata does "
            "not contain a valid contract."
        )

    return contract


# ======================================================================
# Predictor contract
# ======================================================================


def predictor_columns(
    task: MLTaskConfig,
    metadata: dict,
) -> tuple[str, ...]:
    """
    Return predictor columns for a task.

    Predictor selection comes from the Phase 7 metadata contract rather
    than from ad-hoc dtype inspection.
    """

    contract = _metadata_contract(
        metadata,
        task,
    )

    predictors = contract.get(
        "predictor_columns"
    )

    if not isinstance(
        predictors,
        list,
    ):

        raise MLDataError(
            f"{task.name}: predictor_columns "
            "is missing or malformed."
        )

    predictors = tuple(
        str(column)
        for column in predictors
    )

    if not predictors:

        raise MLDataError(
            f"{task.name}: no predictor "
            "columns were configured."
        )

    if (
        task.target_column
        in predictors
    ):

        raise MLDataError(
            f"{task.name}: target leakage "
            f"detected. Target "
            f"{task.target_column!r} appears "
            "inside predictor_columns."
        )

    if (
        task.split_column
        in predictors
    ):

        raise MLDataError(
            f"{task.name}: split column "
            f"{task.split_column!r} appears "
            "inside predictor_columns."
        )

    if len(
        set(predictors)
    ) != len(
        predictors
    ):

        raise MLDataError(
            f"{task.name}: duplicate "
            "predictor columns detected."
        )

    return predictors


# ======================================================================
# Split loading
# ======================================================================


def _expected_split_rows(
    metadata: dict,
    split_name: SplitName,
) -> int | None:
    """
    Return expected Phase 7 row count when available.
    """

    splits = metadata.get(
        "splits"
    )

    if not isinstance(
        splits,
        dict,
    ):

        return None

    split_metadata = splits.get(
        split_name
    )

    if not isinstance(
        split_metadata,
        dict,
    ):

        return None

    rows = split_metadata.get(
        "rows"
    )

    if rows is None:

        return None

    return int(
        rows
    )


def _validate_split_frame(
    frame: pd.DataFrame,
    *,
    task: MLTaskConfig,
    metadata: dict,
    predictors: tuple[str, ...],
    split_name: SplitName,
) -> None:
    """
    Validate one loaded Parquet split against the feature contract.
    """

    if frame.empty:

        raise MLDataError(
            f"{task.name}/{split_name}: "
            "dataset is empty."
        )

    if frame.columns.duplicated().any():

        duplicates = (
            frame.columns[
                frame.columns.duplicated()
            ]
            .tolist()
        )

        raise MLDataError(
            f"{task.name}/{split_name}: "
            "duplicate columns detected: "
            f"{duplicates}"
        )

    required = set(
        predictors
    )

    required.add(
        task.target_column
    )

    required.add(
        task.split_column
    )

    missing = sorted(
        required
        - set(
            frame.columns
        )
    )

    if missing:

        raise MLDataError(
            f"{task.name}/{split_name}: "
            "required columns are missing: "
            f"{missing}"
        )

    target_nulls = int(
        frame[
            task.target_column
        ]
        .isna()
        .sum()
    )

    if target_nulls:

        raise MLDataError(
            f"{task.name}/{split_name}: "
            f"target {task.target_column!r} "
            f"contains {target_nulls:,} "
            "null values."
        )

    split_nulls = int(
        frame[
            task.split_column
        ]
        .isna()
        .sum()
    )

    if split_nulls:

        raise MLDataError(
            f"{task.name}/{split_name}: "
            f"split column "
            f"{task.split_column!r} "
            f"contains {split_nulls:,} "
            "null values."
        )

    expected_rows = (
        _expected_split_rows(
            metadata,
            split_name,
        )
    )

    if (
        expected_rows is not None
        and len(frame)
        != expected_rows
    ):

        raise MLDataError(
            f"{task.name}/{split_name}: "
            "row count differs from "
            "Phase 7 metadata. "
            f"Expected {expected_rows:,}, "
            f"found {len(frame):,}."
        )


def load_split(
    task: MLTaskConfig,
    split_name: SplitName,
    *,
    metadata: dict | None = None,
    predictors: tuple[str, ...] | None = None,
) -> LoadedSplit:
    """
    Load and validate one Parquet split.
    """

    if (
        split_name
        not in VALID_SPLITS
    ):

        raise ValueError(
            f"Invalid split: "
            f"{split_name!r}"
        )

    if metadata is None:

        metadata = load_metadata(
            task
        )

    if predictors is None:

        predictors = predictor_columns(
            task,
            metadata,
        )

    path = split_path(
        task,
        split_name,
    )

    if not path.exists():

        raise MLDataError(
            f"{task.name}/{split_name}: "
            f"Parquet file does not exist: "
            f"{path}"
        )

    try:

        frame = pd.read_parquet(
            path
        )

    except Exception as exc:

        raise MLDataError(
            f"{task.name}/{split_name}: "
            f"failed to read {path}: "
            f"{exc}"
        ) from exc

    _validate_split_frame(
        frame,
        task=task,
        metadata=metadata,
        predictors=predictors,
        split_name=split_name,
    )

    # Phase 9 task-level population eligibility.
    #
    # Apply this only AFTER validating the original Phase 7 artifact so
    # metadata row-count integrity remains independently verified.
    if task.eligibility_column is not None:
        column = task.eligibility_column

        if column not in frame.columns:
            raise MLDataError(
                f"{task.name}/{split_name}: "
                f"eligibility column {column!r} is missing."
            )

        eligibility = (
            pd.to_numeric(
                frame[column],
                errors="coerce",
            )
            .fillna(0)
            .eq(1)
        )

        frame = frame.loc[eligibility].copy()

        if frame.empty:
            raise MLDataError(
                f"{task.name}/{split_name}: "
                "eligibility filtering removed every row."
            )

    return LoadedSplit(
        name=split_name,
        frame=frame,
        predictors=predictors,
        target_column=(
            task.target_column
        ),
    )


# ======================================================================
# Chronology validation
# ======================================================================


def _date_bounds(
    split: LoadedSplit,
    column: str,
) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Return split minimum and maximum timestamps."""

    values = pd.to_datetime(
        split.frame[column],
        errors="raise",
        utc=True,
    )

    return (
        values.min(),
        values.max(),
    )


def validate_chronology(
    dataset: TaskDataset,
) -> None:
    """
    Ensure train < validation < test chronologically.
    """

    column = (
        dataset.task.split_column
    )

    train_min, train_max = (
        _date_bounds(
            dataset.train,
            column,
        )
    )

    validation_min, validation_max = (
        _date_bounds(
            dataset.validation,
            column,
        )
    )

    test_min, test_max = (
        _date_bounds(
            dataset.test,
            column,
        )
    )

    if not (
        train_max
        < validation_min
    ):

        raise MLDataError(
            f"{dataset.task.name}: "
            "train/validation chronology "
            "overlaps. "
            f"train max={train_max}, "
            f"validation min="
            f"{validation_min}"
        )

    if not (
        validation_max
        < test_min
    ):

        raise MLDataError(
            f"{dataset.task.name}: "
            "validation/test chronology "
            "overlaps. "
            f"validation max="
            f"{validation_max}, "
            f"test min={test_min}"
        )

    if not (
        train_min
        <= train_max
        < validation_min
        <= validation_max
        < test_min
        <= test_max
    ):

        raise MLDataError(
            f"{dataset.task.name}: "
            "invalid chronological split "
            "ordering."
        )


# ======================================================================
# Full task loader
# ======================================================================


def load_task_dataset(
    task_name: str,
) -> TaskDataset:
    """
    Load all three partitions for one ML task.
    """

    task = get_task_config(
        task_name
    )

    metadata = load_metadata(
        task
    )

    predictors = predictor_columns(
        task,
        metadata,
    )

    dataset = TaskDataset(
        task=task,
        predictors=predictors,
        metadata=metadata,

        train=load_split(
            task,
            "train",
            metadata=metadata,
            predictors=predictors,
        ),

        validation=load_split(
            task,
            "validation",
            metadata=metadata,
            predictors=predictors,
        ),

        test=load_split(
            task,
            "test",
            metadata=metadata,
            predictors=predictors,
        ),
    )

    validate_chronology(
        dataset
    )

    return dataset


# ======================================================================
# Diagnostics
# ======================================================================


def print_dataset_summary(
    dataset: TaskDataset,
) -> None:
    """
    Print a concise task dataset summary.
    """

    print()
    print(
        "=" * 78
    )

    print(
        f"FulfillAI ML dataset: "
        f"{dataset.task.name}"
    )

    print(
        "=" * 78
    )

    print(
        f"dataset        : "
        f"{dataset.task.dataset_name}"
    )

    print(
        f"target         : "
        f"{dataset.task.target_column}"
    )

    print(
        f"split column   : "
        f"{dataset.task.split_column}"
    )

    print(
        f"predictors     : "
        f"{len(dataset.predictors):,}"
    )

    print()

    for split in (
        dataset.train,
        dataset.validation,
        dataset.test,
    ):

        minimum, maximum = (
            _date_bounds(
                split,
                dataset.task.split_column,
            )
        )

        print(
            f"{split.name:<10} "
            f"rows={split.rows:>9,}  "
            f"{minimum.date()} "
            f"→ {maximum.date()}"
        )

    print()

    print(
        "DATA CONTRACT VALIDATED ✓"
    )

    print(
        "TARGET LEAKAGE CHECK PASSED ✓"
    )

    print(
        "CHRONOLOGICAL SPLIT CHECK PASSED ✓"
    )


# ======================================================================
# CLI
# ======================================================================


def main() -> None:
    """
    Validate every registered ML task.
    """

    from .config import task_names

    for task_name in task_names():

        dataset = load_task_dataset(
            task_name
        )

        print_dataset_summary(
            dataset
        )

    print()
    print(
        "=" * 78
    )

    print(
        "ALL ML DATA CONTRACTS PASSED ✓"
    )

    print(
        "=" * 78
    )


if __name__ == "__main__":
    main()