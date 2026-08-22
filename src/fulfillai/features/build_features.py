"""
FulfillAI ML feature materialization.

This module turns validated PostgreSQL analytical views into deterministic,
chronologically split Parquet datasets for downstream machine learning.

Pipeline
--------
PostgreSQL analytical view
    -> extraction
    -> source validation
    -> eligibility filtering
    -> chronological train/validation/test split
    -> Parquet materialization
    -> round-trip verification
    -> reproducibility metadata

Generated Parquet and metadata files live under:

    data/processed/features/<dataset>/

They are build artifacts and should remain ignored by Git.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import pandas as pd

from .config import (
    DatasetConfig,
    dataset_names,
    get_dataset_config,
)
from .extract import extract_dataset
from .split import (
    DatasetSplits,
    split_dataset,
)
from .validate import (
    ValidationResult,
    predictor_columns,
    validate_dataset,
)


DEFAULT_OUTPUT_DIR = Path("data/processed/features")

PARQUET_FILES = {
    "train": "train.parquet",
    "validation": "validation.parquet",
    "test": "test.parquet",
}


# ======================================================================
# Exceptions
# ======================================================================


class FeatureBuildError(RuntimeError):
    """Raised when ML feature materialization fails."""


# ======================================================================
# Result containers
# ======================================================================


@dataclass(frozen=True)
class ArtifactInfo:
    """Metadata describing one materialized Parquet artifact."""

    split: str
    path: str
    rows: int
    columns: int
    bytes: int
    sha256: str
    minimum_date: str
    maximum_date: str


@dataclass(frozen=True)
class DatasetBuildResult:
    """Summary of one fully materialized ML dataset."""

    dataset: str
    output_dir: str

    source_rows: int
    eligible_rows: int

    train_rows: int
    validation_rows: int
    test_rows: int

    metadata_path: str

    artifacts: tuple[ArtifactInfo, ...]


# ======================================================================
# General helpers
# ======================================================================


def _utc_now_iso() -> str:
    """Return a timezone-aware UTC build timestamp."""

    return datetime.now(
        timezone.utc
    ).isoformat()


def _sha256_file(
    path: Path,
) -> str:
    """Return the SHA-256 digest of a file."""

    digest = hashlib.sha256()

    with path.open("rb") as handle:

        for chunk in iter(
            lambda: handle.read(
                1024 * 1024
            ),
            b"",
        ):
            digest.update(
                chunk
            )

    return digest.hexdigest()


def _date_range(
    frame: pd.DataFrame,
    config: DatasetConfig,
) -> tuple[str, str]:
    """Return minimum and maximum split dates."""

    if frame.empty:

        raise FeatureBuildError(
            f"{config.name}: cannot compute "
            "date range for an empty split."
        )

    values = pd.to_datetime(
        frame[
            config.split_column
        ],
        errors="raise",
        utc=True,
    )

    minimum = (
        values
        .min()
        .strftime("%Y-%m-%d")
    )

    maximum = (
        values
        .max()
        .strftime("%Y-%m-%d")
    )

    return (
        minimum,
        maximum,
    )


# ======================================================================
# Parquet writing
# ======================================================================


def _verify_round_trip(
    original: pd.DataFrame,
    restored: pd.DataFrame,
    *,
    dataset_name: str,
    split_name: str,
) -> None:
    """
    Verify structural integrity after Parquet serialization.
    """

    if len(original) != len(restored):

        raise FeatureBuildError(
            f"{dataset_name}/{split_name}: "
            "Parquet round-trip row mismatch. "
            f"Expected {len(original):,}, "
            f"got {len(restored):,}."
        )

    if (
        list(original.columns)
        != list(restored.columns)
    ):

        raise FeatureBuildError(
            f"{dataset_name}/{split_name}: "
            "Parquet round-trip column names "
            "or ordering changed."
        )

    if (
        len(original.columns)
        != len(restored.columns)
    ):

        raise FeatureBuildError(
            f"{dataset_name}/{split_name}: "
            "Parquet round-trip column "
            "count changed."
        )


def _write_parquet_atomic(
    frame: pd.DataFrame,
    destination: Path,
    *,
    dataset_name: str,
    split_name: str,
) -> None:
    """
    Write one Parquet file atomically.

    The old destination is kept intact until the newly written
    temporary Parquet file has successfully been read back.
    """

    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary = destination.with_name(
        f".{destination.name}."
        f"{uuid4().hex}.tmp"
    )

    try:

        try:

            frame.to_parquet(
                temporary,
                index=False,
            )

            restored = pd.read_parquet(
                temporary
            )

        except ImportError as exc:

            raise FeatureBuildError(
                "Parquet support is unavailable.\n"
                "Install pyarrow inside the active "
                "virtual environment with:\n\n"
                "    pip install pyarrow"
            ) from exc

        _verify_round_trip(
            frame,
            restored,
            dataset_name=dataset_name,
            split_name=split_name,
        )

        os.replace(
            temporary,
            destination,
        )

    finally:

        if temporary.exists():

            temporary.unlink()


# ======================================================================
# Artifact metadata
# ======================================================================


def _artifact_info(
    *,
    split_name: str,
    path: Path,
    frame: pd.DataFrame,
    config: DatasetConfig,
    project_root: Path,
) -> ArtifactInfo:
    """Build metadata for one Parquet split."""

    minimum, maximum = _date_range(
        frame,
        config,
    )

    try:

        display_path = path.relative_to(
            project_root
        )

    except ValueError:

        display_path = path

    return ArtifactInfo(
        split=split_name,
        path=str(
            display_path
        ),
        rows=len(frame),
        columns=len(
            frame.columns
        ),
        bytes=path.stat().st_size,
        sha256=_sha256_file(
            path
        ),
        minimum_date=minimum,
        maximum_date=maximum,
    )


# ======================================================================
# Atomic JSON writing
# ======================================================================


def _write_json_atomic(
    payload: dict[str, Any],
    destination: Path,
) -> None:
    """Write JSON metadata atomically."""

    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary = destination.with_name(
        f".{destination.name}."
        f"{uuid4().hex}.tmp"
    )

    try:

        with temporary.open(
            "w",
            encoding="utf-8",
        ) as handle:

            json.dump(
                payload,
                handle,
                indent=2,
                sort_keys=True,
            )

            handle.write(
                "\n"
            )

        os.replace(
            temporary,
            destination,
        )

    finally:

        if temporary.exists():

            temporary.unlink()


# ======================================================================
# Validation metadata
# ======================================================================


def _validation_metadata(
    result: ValidationResult,
) -> dict[str, Any]:
    """
    Convert validation output into JSON-safe metadata.
    """

    return {
        "rows": result.rows,
        "columns": result.columns,
        "eligible_rows": (
            result.eligible_rows
        ),
        "duplicate_primary_keys": (
            result.duplicate_primary_keys
        ),
        "null_primary_keys": (
            result.null_primary_keys
        ),
        "null_targets": (
            result.null_targets
        ),
        "predictor_columns": (
            result.predictor_columns
        ),
        "constant_predictors": (
            result.constant_predictors
        ),
        "split_min": (
            result.split_min
        ),
        "split_max": (
            result.split_max
        ),
    }


# ======================================================================
# Dataset metadata
# ======================================================================


def _dataset_metadata(
    *,
    config: DatasetConfig,
    validation: ValidationResult,
    source_frame: pd.DataFrame,
    splits: DatasetSplits,
    artifacts: tuple[
        ArtifactInfo,
        ...,
    ],
) -> dict[str, Any]:
    """
    Create reproducibility metadata for one ML dataset.
    """

    predictors = predictor_columns(
        source_frame,
        config,
    )

    return {
        "metadata_version": 1,

        "generated_at_utc": (
            _utc_now_iso()
        ),

        "dataset": config.name,

        "task_type": (
            config.task_type
        ),

        "source": {
            "view": (
                config.source_view
            ),
            "rows": (
                len(source_frame)
            ),
            "columns": (
                len(
                    source_frame.columns
                )
            ),
        },

        "contract": {
            "primary_key": list(
                config.primary_key
            ),
            "split_column": (
                config.split_column
            ),
            "target_columns": list(
                config.target_columns
            ),
            "required_columns": list(
                config.required_columns
            ),
            "excluded_feature_columns": list(
                config.excluded_feature_columns
            ),
            "eligibility_filter": (
                config.eligibility_filter
            ),
            "predictor_columns": list(
                predictors
            ),
        },

        "validation": (
            _validation_metadata(
                validation
            )
        ),

        "splits": {
            artifact.split: {
                "path": (
                    artifact.path
                ),
                "rows": (
                    artifact.rows
                ),
                "columns": (
                    artifact.columns
                ),
                "bytes": (
                    artifact.bytes
                ),
                "sha256": (
                    artifact.sha256
                ),
                "minimum_date": (
                    artifact.minimum_date
                ),
                "maximum_date": (
                    artifact.maximum_date
                ),
            }
            for artifact
            in artifacts
        },

        "row_conservation": {
            "eligible_rows": (
                validation.eligible_rows
            ),
            "materialized_rows": (
                splits.total_rows
            ),
            "difference": (
                splits.total_rows
                - validation.eligible_rows
            ),
        },

        "software": {
            "python": (
                platform.python_version()
            ),
            "pandas": (
                pd.__version__
            ),
            "platform": (
                platform.platform()
            ),
        },
    }


# ======================================================================
# Split mapping
# ======================================================================


def _partition_map(
    splits: DatasetSplits,
) -> dict[
    str,
    pd.DataFrame,
]:
    """Return split names mapped to DataFrames."""

    return {
        "train": (
            splits.train
        ),
        "validation": (
            splits.validation
        ),
        "test": (
            splits.test
        ),
    }


# ======================================================================
# Build one dataset
# ======================================================================


def build_dataset(
    dataset_name: str,
    *,
    output_root: Path = (
        DEFAULT_OUTPUT_DIR
    ),
    project_root: Path | None = None,
) -> DatasetBuildResult:
    """
    Extract, validate, split and materialize one dataset.
    """

    if project_root is None:

        project_root = Path.cwd()

    config = get_dataset_config(
        dataset_name
    )

    print()
    print(
        "=" * 78
    )

    print(
        f"FulfillAI feature build: "
        f"{dataset_name}"
    )

    print(
        "=" * 78
    )

    # --------------------------------------------------------------
    # Extract
    # --------------------------------------------------------------

    print(
        f"Extracting PostgreSQL view "
        f"{config.source_view}..."
    )

    source_frame = extract_dataset(
        config
    )

    # --------------------------------------------------------------
    # Validate
    # --------------------------------------------------------------

    print(
        f"Validating {dataset_name}..."
    )

    validation = validate_dataset(
        source_frame,
        config,
    )

    # --------------------------------------------------------------
    # Split
    # --------------------------------------------------------------

    print(
        "Creating chronological splits..."
    )

    splits = split_dataset(
        source_frame,
        config,
        validate_source=False,
    )

    if (
        splits.total_rows
        != validation.eligible_rows
    ):

        raise FeatureBuildError(
            f"{dataset_name}: split total "
            f"{splits.total_rows:,} does not "
            "match validated eligible rows "
            f"{validation.eligible_rows:,}."
        )

    # --------------------------------------------------------------
    # Output directory
    # --------------------------------------------------------------

    dataset_dir = (
        output_root
        / dataset_name
    )

    dataset_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    artifact_records: list[
        ArtifactInfo
    ] = []

    # --------------------------------------------------------------
    # Materialize each partition
    # --------------------------------------------------------------

    for (
        split_name,
        frame,
    ) in _partition_map(
        splits
    ).items():

        destination = (
            dataset_dir
            / PARQUET_FILES[
                split_name
            ]
        )

        print(
            f"Writing "
            f"{split_name:<10} "
            f"{len(frame):>10,} rows "
            f"-> {destination}"
        )

        _write_parquet_atomic(
            frame,
            destination,
            dataset_name=dataset_name,
            split_name=split_name,
        )

        artifact_records.append(
            _artifact_info(
                split_name=(
                    split_name
                ),
                path=destination,
                frame=frame,
                config=config,
                project_root=(
                    project_root
                ),
            )
        )

    artifacts = tuple(
        artifact_records
    )

    # --------------------------------------------------------------
    # Metadata
    # --------------------------------------------------------------

    metadata = _dataset_metadata(
        config=config,
        validation=validation,
        source_frame=source_frame,
        splits=splits,
        artifacts=artifacts,
    )

    metadata_path = (
        dataset_dir
        / "metadata.json"
    )

    _write_json_atomic(
        metadata,
        metadata_path,
    )

    try:

        display_metadata_path = (
            metadata_path.relative_to(
                project_root
            )
        )

    except ValueError:

        display_metadata_path = (
            metadata_path
        )

    # --------------------------------------------------------------
    # Summary
    # --------------------------------------------------------------

    print(
        "-" * 78
    )

    print(
        f"source rows        : "
        f"{len(source_frame):,}"
    )

    print(
        f"eligible rows      : "
        f"{validation.eligible_rows:,}"
    )

    print(
        f"train rows         : "
        f"{len(splits.train):,}"
    )

    print(
        f"validation rows    : "
        f"{len(splits.validation):,}"
    )

    print(
        f"test rows          : "
        f"{len(splits.test):,}"
    )

    print(
        f"materialized total : "
        f"{splits.total_rows:,}"
    )

    print(
        f"metadata           : "
        f"{display_metadata_path}"
    )

    print(
        "-" * 78
    )

    print(
        "PARQUET ROUND-TRIP "
        "VERIFICATION PASSED ✓"
    )

    print(
        "ROW CONSERVATION PASSED ✓"
    )

    print(
        "FEATURE DATASET BUILD PASSED ✓"
    )

    print(
        "=" * 78
    )

    return DatasetBuildResult(
        dataset=dataset_name,
        output_dir=str(
            dataset_dir
        ),
        source_rows=len(
            source_frame
        ),
        eligible_rows=(
            validation.eligible_rows
        ),
        train_rows=len(
            splits.train
        ),
        validation_rows=len(
            splits.validation
        ),
        test_rows=len(
            splits.test
        ),
        metadata_path=str(
            metadata_path
        ),
        artifacts=artifacts,
    )


# ======================================================================
# Manifest
# ======================================================================


def _manifest_payload(
    results: list[
        DatasetBuildResult
    ],
) -> dict[str, Any]:
    """
    Create manifest metadata for this build execution.
    """

    return {
        "manifest_version": 1,

        "generated_at_utc": (
            _utc_now_iso()
        ),

        "datasets": {
            result.dataset: {
                "output_dir": (
                    result.output_dir
                ),
                "source_rows": (
                    result.source_rows
                ),
                "eligible_rows": (
                    result.eligible_rows
                ),
                "train_rows": (
                    result.train_rows
                ),
                "validation_rows": (
                    result.validation_rows
                ),
                "test_rows": (
                    result.test_rows
                ),
                "metadata_path": (
                    result.metadata_path
                ),
                "artifacts": [
                    asdict(
                        artifact
                    )
                    for artifact
                    in result.artifacts
                ],
            }
            for result
            in results
        },

        "software": {
            "python": (
                platform.python_version()
            ),
            "pandas": (
                pd.__version__
            ),
        },
    }


def write_manifest(
    results: list[
        DatasetBuildResult
    ],
    *,
    output_root: Path,
) -> Path:
    """Write manifest for this execution."""

    manifest_path = (
        output_root
        / "manifest.json"
    )

    _write_json_atomic(
        _manifest_payload(
            results
        ),
        manifest_path,
    )

    return manifest_path


# ======================================================================
# CLI
# ======================================================================


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""

    parser = argparse.ArgumentParser(
        description=(
            "Materialize validated FulfillAI ML "
            "feature datasets as chronological "
            "Parquet splits."
        )
    )

    parser.add_argument(
        "--dataset",
        choices=dataset_names(),
        default=None,
        help=(
            "Build one dataset. "
            "If omitted, all configured ML "
            "datasets are built."
        ),
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=(
            "Directory for generated feature "
            "artifacts. "
            "Default: data/processed/features"
        ),
    )

    return parser.parse_args()


# ======================================================================
# Main
# ======================================================================


def main() -> None:
    """CLI entrypoint."""

    args = parse_args()

    output_root = (
        args.output_dir
    )

    output_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    if args.dataset is not None:

        names = (
            args.dataset,
        )

    else:

        names = dataset_names()

    results: list[
        DatasetBuildResult
    ] = []

    try:

        for name in names:

            results.append(
                build_dataset(
                    name,
                    output_root=(
                        output_root
                    ),
                )
            )

        manifest_path = (
            write_manifest(
                results,
                output_root=(
                    output_root
                ),
            )
        )

    except Exception as exc:

        print(
            f"\nFEATURE BUILD FAILED: "
            f"{exc}",
            file=sys.stderr,
        )

        raise SystemExit(
            1
        ) from exc

    print()
    print(
        "=" * 78
    )

    print(
        "ALL REQUESTED FEATURE DATASETS "
        "BUILT SUCCESSFULLY ✓"
    )

    print(
        "=" * 78
    )

    for result in results:

        print(
            f"{result.dataset:<24} "
            f"train="
            f"{result.train_rows:>9,}  "
            f"validation="
            f"{result.validation_rows:>8,}  "
            f"test="
            f"{result.test_rows:>8,}"
        )

    print()

    print(
        f"manifest: "
        f"{manifest_path}"
    )


if __name__ == "__main__":
    main()