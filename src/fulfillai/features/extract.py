"""
FulfillAI PostgreSQL feature extraction layer.

Responsibilities
----------------
- Load PostgreSQL connection settings.
- Connect safely to the FulfillAI database.
- Read configured analytical views.
- Validate that required columns exist.
- Return deterministic pandas DataFrames.
- Provide lightweight extraction summaries.

This module does NOT:
- create train/validation/test splits
- remove leakage columns
- write Parquet files
- train ML models

Those responsibilities belong to later feature-pipeline stages.
"""

from __future__ import annotations

import argparse
import os
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import pandas as pd
import psycopg
from psycopg import sql

from .config import (
    DATASET_CONFIGS,
    PROJECT_ROOT,
    DatasetConfig,
    dataset_names,
    get_dataset_config,
)


# ======================================================================
# Constants
# ======================================================================

DEFAULT_FETCH_SIZE = 50_000


# ======================================================================
# Exceptions
# ======================================================================


class FeatureExtractionError(RuntimeError):
    """Raised when feature extraction cannot be completed safely."""


# ======================================================================
# Environment loading
# ======================================================================


def _load_env_file(path: Path) -> None:
    """
    Load simple KEY=VALUE entries from an environment file.

    Existing environment variables are never overwritten.

    This intentionally handles only the conventional environment-file
    syntax needed by FulfillAI and avoids introducing an additional
    dependency solely for configuration loading.
    """

    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()

        if not line:
            continue

        if line.startswith("#"):
            continue

        if "=" not in line:
            continue

        key, value = line.split("=", 1)

        key = key.strip()
        value = value.strip()

        if not key:
            continue

        # Remove simple matching quotes.
        if (
            len(value) >= 2
            and value[0] == value[-1]
            and value[0] in {"'", '"'}
        ):
            value = value[1:-1]

        os.environ.setdefault(key, value)


def load_project_environment() -> None:
    """
    Load the project's .env file when present.

    Environment variables already exported in the shell take precedence.
    """

    _load_env_file(PROJECT_ROOT / ".env")


# ======================================================================
# PostgreSQL configuration
# ======================================================================


@dataclass(frozen=True)
class PostgresConfig:
    """PostgreSQL connection parameters."""

    host: str
    port: int
    database: str
    user: str
    password: str
    connect_timeout: int = 10


def get_postgres_config() -> PostgresConfig:
    """
    Build PostgreSQL configuration from environment variables.

    Expected variables
    ------------------
    POSTGRES_HOST
    POSTGRES_PORT
    POSTGRES_DB
    POSTGRES_USER
    POSTGRES_PASSWORD
    """

    load_project_environment()

    host = os.getenv("POSTGRES_HOST", "localhost")
    port_raw = os.getenv("POSTGRES_PORT", "5432")
    database = os.getenv("POSTGRES_DB", "fulfillai")
    user = os.getenv("POSTGRES_USER", "fulfillai")
    password = os.getenv("POSTGRES_PASSWORD")

    try:
        port = int(port_raw)

    except ValueError as exc:
        raise FeatureExtractionError(
            f"POSTGRES_PORT must be an integer, got {port_raw!r}."
        ) from exc

    if not password:
        raise FeatureExtractionError(
            "POSTGRES_PASSWORD is not configured. "
            "Set it in the environment or project .env file."
        )

    return PostgresConfig(
        host=host,
        port=port,
        database=database,
        user=user,
        password=password,
    )


# ======================================================================
# Database connection
# ======================================================================


@contextmanager
def postgres_connection() -> Iterator[psycopg.Connection]:
    """
    Open a PostgreSQL connection for feature extraction.

    The connection is configured as read-only because feature extraction
    must never modify the operational/analytical database.
    """

    config = get_postgres_config()

    try:
        connection = psycopg.connect(
            host=config.host,
            port=config.port,
            dbname=config.database,
            user=config.user,
            password=config.password,
            connect_timeout=config.connect_timeout,
            application_name="fulfillai_feature_extractor",
        )

    except psycopg.Error as exc:
        raise FeatureExtractionError(
            "Unable to connect to the FulfillAI PostgreSQL database."
        ) from exc

    try:
        # Prevent accidental writes from this extraction layer.
        connection.execute(
            "SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY"
        )

        yield connection

    finally:
        connection.close()


# ======================================================================
# View/schema inspection
# ======================================================================


def get_view_columns(
    connection: psycopg.Connection,
    view_name: str,
) -> tuple[str, ...]:
    """
    Return columns for a configured PostgreSQL view.

    Only views already registered in DATASET_CONFIGS are accepted.
    """

    allowed_views = {
        config.source_view
        for config in DATASET_CONFIGS.values()
    }

    if view_name not in allowed_views:
        raise FeatureExtractionError(
            f"View {view_name!r} is not registered as a FulfillAI "
            "feature source."
        )

    query = """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = %s
        ORDER BY ordinal_position
    """

    with connection.cursor() as cursor:
        cursor.execute(query, (view_name,))
        rows = cursor.fetchall()

    if not rows:
        raise FeatureExtractionError(
            f"PostgreSQL view {view_name!r} does not exist "
            "or contains no visible columns."
        )

    return tuple(row[0] for row in rows)


def validate_source_schema(
    connection: psycopg.Connection,
    config: DatasetConfig,
) -> tuple[str, ...]:
    """
    Validate a PostgreSQL analytical view against its DatasetConfig.

    Returns the complete ordered source-column list.
    """

    columns = get_view_columns(
        connection,
        config.source_view,
    )

    available = set(columns)

    required = set(config.required_columns)
    required.add(config.split_column)
    required.update(config.primary_key)
    required.update(config.target_columns)

    missing = sorted(required - available)

    if missing:
        raise FeatureExtractionError(
            f"{config.name}: source view {config.source_view!r} "
            f"is missing required columns: {missing}"
        )

    return columns


# ======================================================================
# Query construction
# ======================================================================


def _deterministic_order_columns(
    config: DatasetConfig,
) -> tuple[str, ...]:
    """
    Return deterministic SQL ordering columns.

    The split column comes first followed by primary-key columns.
    Duplicate names are removed while retaining order.
    """

    candidates = (
        config.split_column,
        *config.primary_key,
    )

    seen: set[str] = set()
    ordered: list[str] = []

    for column in candidates:
        if column not in seen:
            seen.add(column)
            ordered.append(column)

    return tuple(ordered)


def build_select_query(
    config: DatasetConfig,
) -> sql.Composed:
    """
    Build a safe deterministic SELECT query.

    PostgreSQL identifiers are quoted with psycopg.sql.Identifier rather
    than interpolated directly into SQL strings.
    """

    registered_views = {
        dataset.source_view
        for dataset in DATASET_CONFIGS.values()
    }

    if config.source_view not in registered_views:
        raise FeatureExtractionError(
            f"Unregistered source view: {config.source_view!r}"
        )

    order_columns = _deterministic_order_columns(config)

    order_sql = sql.SQL(", ").join(
        sql.Identifier(column)
        for column in order_columns
    )

    return sql.SQL(
        "SELECT * FROM {} ORDER BY {}"
    ).format(
        sql.Identifier(config.source_view),
        order_sql,
    )


# ======================================================================
# Data extraction
# ======================================================================


def _cursor_to_dataframe(
    cursor: psycopg.Cursor,
    *,
    fetch_size: int = DEFAULT_FETCH_SIZE,
) -> pd.DataFrame:
    """
    Convert a PostgreSQL cursor into a DataFrame in batches.

    Batch fetching avoids holding both the complete database result list
    and the final DataFrame in memory simultaneously.
    """

    if fetch_size <= 0:
        raise ValueError(
            "fetch_size must be greater than zero."
        )

    if cursor.description is None:
        raise FeatureExtractionError(
            "Database query returned no column description."
        )

    columns = tuple(
        description.name
        for description in cursor.description
    )

    frames: list[pd.DataFrame] = []

    while True:
        rows = cursor.fetchmany(fetch_size)

        if not rows:
            break

        frames.append(
            pd.DataFrame.from_records(
                rows,
                columns=columns,
            )
        )

    if not frames:
        return pd.DataFrame(columns=columns)

    if len(frames) == 1:
        return frames[0]

    return pd.concat(
    frames,
    ignore_index=True,
)

def extract_dataset(
    dataset: str | DatasetConfig,
    *,
    fetch_size: int = DEFAULT_FETCH_SIZE,
) -> pd.DataFrame:
    """
    Extract one configured ML source dataset from PostgreSQL.

    Parameters
    ----------
    dataset:
        Dataset name or DatasetConfig object.

    fetch_size:
        Number of PostgreSQL records fetched per batch.

    Returns
    -------
    pandas.DataFrame
        Deterministically ordered raw feature-source dataset.
    """

    if isinstance(dataset, str):
        config = get_dataset_config(dataset)

    elif isinstance(dataset, DatasetConfig):
        config = dataset

    else:
        raise TypeError(
            "dataset must be a dataset name or DatasetConfig."
        )

    with postgres_connection() as connection:

        validate_source_schema(
            connection,
            config,
        )

        query = build_select_query(config)

        try:
            with connection.cursor() as cursor:
                cursor.execute(query)

                frame = _cursor_to_dataframe(
                    cursor,
                    fetch_size=fetch_size,
                )

        except psycopg.Error as exc:
            raise FeatureExtractionError(
                f"Failed extracting {config.name!r} "
                f"from {config.source_view!r}."
            ) from exc

    if frame.empty:
        raise FeatureExtractionError(
            f"{config.name}: extraction returned zero rows."
        )

    missing_after_extract = (
        set(config.required_columns)
        - set(frame.columns)
    )

    if missing_after_extract:
        raise FeatureExtractionError(
            f"{config.name}: extracted DataFrame is missing columns: "
            f"{sorted(missing_after_extract)}"
        )

    return frame


def extract_all_datasets(
    *,
    fetch_size: int = DEFAULT_FETCH_SIZE,
) -> dict[str, pd.DataFrame]:
    """
    Extract every configured ML source dataset.

    Returns
    -------
    dict[str, pandas.DataFrame]
        Mapping of dataset name to DataFrame.
    """

    extracted: dict[str, pd.DataFrame] = {}

    for name in dataset_names():
        extracted[name] = extract_dataset(
            name,
            fetch_size=fetch_size,
        )

    return extracted


# ======================================================================
# Extraction summaries
# ======================================================================


@dataclass(frozen=True)
class ExtractionSummary:
    """Compact extraction metadata."""

    dataset: str
    source_view: str
    rows: int
    columns: int
    split_column: str
    split_min: str
    split_max: str


def summarize_extraction(
    frame: pd.DataFrame,
    config: DatasetConfig,
) -> ExtractionSummary:
    """Build a compact summary for an extracted dataset."""

    split_series = pd.to_datetime(
        frame[config.split_column],
        errors="raise",
        utc=True,
    )

    return ExtractionSummary(
        dataset=config.name,
        source_view=config.source_view,
        rows=len(frame),
        columns=len(frame.columns),
        split_column=config.split_column,
        split_min=str(split_series.min()),
        split_max=str(split_series.max()),
    )


def print_extraction_summary(
    frame: pd.DataFrame,
    config: DatasetConfig,
) -> None:
    """Print a human-readable extraction summary."""

    summary = summarize_extraction(
        frame,
        config,
    )

    print()
    print("=" * 68)
    print(f"FulfillAI feature extraction: {summary.dataset}")
    print("=" * 68)
    print(f"source view    : {summary.source_view}")
    print(f"rows           : {summary.rows:,}")
    print(f"columns        : {summary.columns:,}")
    print(f"split column   : {summary.split_column}")
    print(f"minimum date   : {summary.split_min}")
    print(f"maximum date   : {summary.split_max}")
    print("=" * 68)


# ======================================================================
# CLI
# ======================================================================


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(
        description=(
            "Extract FulfillAI ML feature sources from PostgreSQL."
        )
    )

    parser.add_argument(
        "--dataset",
        choices=dataset_names(),
        default=None,
        help=(
            "Extract one dataset. "
            "If omitted, all configured datasets are checked."
        ),
    )

    parser.add_argument(
        "--fetch-size",
        type=int,
        default=DEFAULT_FETCH_SIZE,
        help=(
            "Rows fetched from PostgreSQL per batch. "
            f"Default: {DEFAULT_FETCH_SIZE:,}."
        ),
    )

    return parser.parse_args()


def main() -> None:
    """CLI entrypoint."""

    args = parse_args()

    if args.fetch_size <= 0:
        raise SystemExit(
            "--fetch-size must be greater than zero."
        )

    if args.dataset is not None:

        config = get_dataset_config(
            args.dataset
        )

        frame = extract_dataset(
            config,
            fetch_size=args.fetch_size,
        )

        print_extraction_summary(
            frame,
            config,
        )

        return

    print("Checking all FulfillAI feature sources...")
    print()

    for name in dataset_names():

        config = get_dataset_config(name)

        frame = extract_dataset(
            config,
            fetch_size=args.fetch_size,
        )

        print_extraction_summary(
            frame,
            config,
        )


if __name__ == "__main__":
    main()