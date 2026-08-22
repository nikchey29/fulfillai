"""
FulfillAI PostgreSQL data loader.

Loads the deterministic synthetic FulfillAI datasets into PostgreSQL
in dependency order using PostgreSQL COPY inside one atomic transaction.

Default behavior:
    python -m src.fulfillai.data.load

Performs a PRE-FLIGHT check only. The database is not modified.

Actual load:
    python -m src.fulfillai.data.load --load

Replace existing FulfillAI data:
    python -m src.fulfillai.data.load --load --replace
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from pathlib import Path
from typing import Final

import psycopg
from dotenv import load_dotenv
from psycopg import sql


# ---------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------

PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[3]
DATA_DIR: Final[Path] = PROJECT_ROOT / "data" / "raw" / "synthetic"
ENV_FILE: Final[Path] = PROJECT_ROOT / ".env"


# ---------------------------------------------------------------------
# Dataset specification
#
# Order is important because of PostgreSQL foreign-key dependencies.
# ---------------------------------------------------------------------

TABLES: Final[tuple[dict[str, object], ...]] = (
    {
        "table": "product_categories",
        "file": "product_categories.csv",
        "columns": (
            "category_id",
            "category_name",
        ),
        "serial_column": "category_id",
    },
    {
        "table": "products",
        "file": "products.csv",
        "columns": (
            "product_id",
            "sku",
            "product_name",
            "category_id",
            "unit_price",
            "unit_cost",
            "weight_kg",
            "active",
            "created_at",
        ),
        "serial_column": "product_id",
    },
    {
        "table": "warehouses",
        "file": "warehouses.csv",
        "columns": (
            "warehouse_id",
            "warehouse_code",
            "warehouse_name",
            "city",
            "country_code",
            "capacity_units",
            "created_at",
        ),
        "serial_column": "warehouse_id",
    },
    {
        "table": "customers",
        "file": "customers.csv",
        "columns": (
            "customer_id",
            "customer_external_id",
            "country_code",
            "region",
            "created_at",
        ),
        "serial_column": "customer_id",
    },
    {
        "table": "inventory",
        "file": "inventory.csv",
        "columns": (
            "warehouse_id",
            "product_id",
            "on_hand_qty",
            "reserved_qty",
            "reorder_point",
            "updated_at",
        ),
        "serial_column": None,
    },
    {
        "table": "orders",
        "file": "orders.csv",
        "columns": (
            "order_id",
            "order_external_id",
            "customer_id",
            "warehouse_id",
            "order_status",
            "shipping_method",
            "payment_method",
            "destination_country",
            "destination_region",
            "order_ts",
            "promised_delivery_ts",
            "total_amount",
            "created_at",
        ),
        "serial_column": "order_id",
    },
    {
        "table": "order_items",
        "file": "order_items.csv",
        "columns": (
            "order_item_id",
            "order_id",
            "product_id",
            "quantity",
            "unit_price",
        ),
        "serial_column": "order_item_id",
    },
    {
        "table": "shipments",
        "file": "shipments.csv",
        "columns": (
            "shipment_id",
            "shipment_external_id",
            "order_id",
            "warehouse_id",
            "carrier",
            "shipment_status",
            "shipped_at",
            "expected_delivery_at",
            "delivered_at",
            "shipping_cost",
            "created_at",
        ),
        "serial_column": "shipment_id",
    },
    {
        "table": "inventory_movements",
        "file": "inventory_movements.csv",
        "columns": (
            "movement_id",
            "warehouse_id",
            "product_id",
            "order_id",
            "movement_type",
            "quantity_change",
            "event_ts",
            "created_at",
        ),
        "serial_column": "movement_id",
    },
    {
        "table": "order_events",
        "file": "order_events.csv",
        "columns": (
            "event_id",
            "event_key",
            "order_id",
            "warehouse_id",
            "event_type",
            "event_ts",
            "source",
            "payload",
            "ingested_at",
        ),
        "serial_column": "event_id",
    },
)


# ---------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Load FulfillAI synthetic datasets into PostgreSQL."
    )

    parser.add_argument(
        "--load",
        action="store_true",
        help="Perform the real PostgreSQL load.",
    )

    parser.add_argument(
        "--replace",
        action="store_true",
        help=(
            "Replace existing FulfillAI table contents before loading. "
            "Requires --load."
        ),
    )

    return parser.parse_args()


def load_environment() -> None:
    if ENV_FILE.exists():
        load_dotenv(ENV_FILE)
    else:
        load_dotenv()


def database_config() -> dict[str, object]:
    required = (
        "POSTGRES_HOST",
        "POSTGRES_PORT",
        "POSTGRES_DB",
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
    )

    missing = [
        key
        for key in required
        if not os.getenv(key)
    ]

    if missing:
        raise RuntimeError(
            "Missing required database environment variables: "
            + ", ".join(missing)
        )

    return {
        "host": os.environ["POSTGRES_HOST"],
        "port": int(os.environ["POSTGRES_PORT"]),
        "dbname": os.environ["POSTGRES_DB"],
        "user": os.environ["POSTGRES_USER"],
        "password": os.environ["POSTGRES_PASSWORD"],
        "connect_timeout": 5,
    }


def count_csv_rows(path: Path) -> int:
    """
    Count logical CSV records rather than physical file lines.
    This remains safe if quoted fields ever contain line breaks.
    """

    with path.open(
        "r",
        encoding="utf-8",
        newline="",
    ) as handle:
        reader = csv.reader(handle)

        try:
            next(reader)
        except StopIteration:
            raise RuntimeError(
                f"CSV file is empty: {path}"
            )

        return sum(1 for _ in reader)


def read_csv_header(path: Path) -> tuple[str, ...]:
    with path.open(
        "r",
        encoding="utf-8",
        newline="",
    ) as handle:
        reader = csv.reader(handle)

        try:
            return tuple(next(reader))
        except StopIteration:
            raise RuntimeError(
                f"CSV file is empty: {path}"
            )


# ---------------------------------------------------------------------
# CSV validation
# ---------------------------------------------------------------------

def validate_source_files() -> dict[str, int]:
    print()
    print("FulfillAI PostgreSQL loader")
    print("=" * 64)
    print()
    print("SOURCE DATA PRE-FLIGHT")
    print("-" * 64)

    source_counts: dict[str, int] = {}

    for spec in TABLES:
        table = str(spec["table"])
        filename = str(spec["file"])
        expected_columns = tuple(spec["columns"])

        path = DATA_DIR / filename

        if not path.exists():
            raise RuntimeError(
                f"Required dataset does not exist: {path}"
            )

        actual_columns = read_csv_header(path)

        if actual_columns != expected_columns:
            print()
            print(f"HEADER MISMATCH: {filename}")
            print()
            print("Expected:")
            print(",".join(expected_columns))
            print()
            print("Found:")
            print(",".join(actual_columns))

            raise RuntimeError(
                f"CSV schema mismatch for {filename}"
            )

        row_count = count_csv_rows(path)

        if row_count <= 0:
            raise RuntimeError(
                f"Dataset contains no records: {filename}"
            )

        source_counts[table] = row_count

        print(
            f"  {table:<24} "
            f"{row_count:>10,} rows  ✓"
        )

    total_rows = sum(source_counts.values())

    print("-" * 64)
    print(
        f"  {'TOTAL':<24} "
        f"{total_rows:>10,} rows"
    )

    return source_counts


# ---------------------------------------------------------------------
# PostgreSQL inspection
# ---------------------------------------------------------------------

def ensure_tables_exist(
    cursor: psycopg.Cursor,
) -> None:
    missing: list[str] = []

    for spec in TABLES:
        table = str(spec["table"])

        cursor.execute(
            "SELECT to_regclass(%s)",
            (f"public.{table}",),
        )

        result = cursor.fetchone()

        if result is None or result[0] is None:
            missing.append(table)

    if missing:
        raise RuntimeError(
            "Required PostgreSQL tables are missing: "
            + ", ".join(missing)
        )


def database_row_counts(
    cursor: psycopg.Cursor,
) -> dict[str, int]:
    counts: dict[str, int] = {}

    for spec in TABLES:
        table = str(spec["table"])

        statement = sql.SQL(
            "SELECT COUNT(*) FROM {}"
        ).format(
            sql.Identifier(table)
        )

        cursor.execute(statement)

        row = cursor.fetchone()

        if row is None:
            raise RuntimeError(
                f"Could not count PostgreSQL table: {table}"
            )

        counts[table] = int(row[0])

    return counts


def run_database_preflight(
    db_config: dict[str, object],
) -> dict[str, int]:
    print()
    print("POSTGRESQL PRE-FLIGHT")
    print("-" * 64)

    try:
        with psycopg.connect(**db_config) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT current_database(), "
                    "current_user, version()"
                )

                database_name, username, version = cursor.fetchone()

                print(f"  database : {database_name}")
                print(f"  user     : {username}")
                print(
                    "  server   : "
                    + version.split(",")[0]
                )

                ensure_tables_exist(cursor)

                counts = database_row_counts(cursor)

    except psycopg.Error as exc:
        raise RuntimeError(
            f"PostgreSQL connection/pre-flight failed: {exc}"
        ) from exc

    print()
    print("CURRENT DATABASE ROW COUNTS")
    print("-" * 64)

    for spec in TABLES:
        table = str(spec["table"])

        print(
            f"  {table:<24} "
            f"{counts[table]:>10,}"
        )

    print("-" * 64)

    return counts


# ---------------------------------------------------------------------
# PostgreSQL COPY loading
# ---------------------------------------------------------------------

def copy_dataset(
    cursor: psycopg.Cursor,
    table: str,
    columns: tuple[str, ...],
    path: Path,
) -> None:
    statement = sql.SQL(
        "COPY {} ({}) "
        "FROM STDIN "
        "WITH (FORMAT CSV, HEADER TRUE)"
    ).format(
        sql.Identifier(table),
        sql.SQL(", ").join(
            sql.Identifier(column)
            for column in columns
        ),
    )

    with cursor.copy(statement) as copy:
        with path.open(
            "r",
            encoding="utf-8",
            newline="",
        ) as handle:

            while True:
                chunk = handle.read(1024 * 1024)

                if not chunk:
                    break

                copy.write(chunk)


# ---------------------------------------------------------------------
# Sequence synchronization
# ---------------------------------------------------------------------

def reset_serial_sequences(
    cursor: psycopg.Cursor,
) -> None:
    """
    COPY inserts explicit primary-key values.

    PostgreSQL sequences therefore need to be moved to the current
    maximum ID so that future INSERT statements cannot reuse IDs.
    """

    print()
    print("Synchronizing PostgreSQL sequences...")

    for spec in TABLES:
        table = str(spec["table"])
        serial_column = spec["serial_column"]

        if serial_column is None:
            continue

        serial_column = str(serial_column)

        cursor.execute(
            "SELECT pg_get_serial_sequence(%s, %s)",
            (table, serial_column),
        )

        result = cursor.fetchone()

        if result is None:
            continue

        sequence_name = result[0]

        if sequence_name is None:
            continue

        max_statement = sql.SQL(
            "SELECT MAX({}) FROM {}"
        ).format(
            sql.Identifier(serial_column),
            sql.Identifier(table),
        )

        cursor.execute(max_statement)

        max_result = cursor.fetchone()

        if max_result is None:
            continue

        maximum_id = max_result[0]

        if maximum_id is None:
            continue

        cursor.execute(
            "SELECT setval(%s::regclass, %s, true)",
            (
                sequence_name,
                int(maximum_id),
            ),
        )

        print(
            f"  {table:<24} "
            f"next ID after {int(maximum_id):,}  ✓"
        )


# ---------------------------------------------------------------------
# Database replacement
# ---------------------------------------------------------------------

def truncate_target_tables(
    cursor: psycopg.Cursor,
) -> None:
    identifiers = sql.SQL(", ").join(
        sql.Identifier(str(spec["table"]))
        for spec in TABLES
    )

    statement = sql.SQL(
        "TRUNCATE TABLE {} RESTART IDENTITY"
    ).format(identifiers)

    cursor.execute(statement)


# ---------------------------------------------------------------------
# Transactional loader
# ---------------------------------------------------------------------

def perform_load(
    db_config: dict[str, object],
    source_counts: dict[str, int],
    replace: bool,
) -> None:
    print()
    print("=" * 64)
    print("STARTING ATOMIC POSTGRESQL LOAD")
    print("=" * 64)

    connection = psycopg.connect(**db_config)

    try:
        with connection.cursor() as cursor:

            # Prevent two FulfillAI loaders from modifying the database
            # at the same time.
            cursor.execute(
                "SELECT pg_advisory_xact_lock("
                "hashtext('fulfillai_data_loader'))"
            )

            ensure_tables_exist(cursor)

            existing_counts = database_row_counts(cursor)

            database_not_empty = any(
                count > 0
                for count in existing_counts.values()
            )

            if database_not_empty:
                if not replace:
                    raise RuntimeError(
                        "Target database already contains FulfillAI data. "
                        "No changes were made. "
                        "Use --load --replace only when you explicitly "
                        "want to replace the existing dataset."
                    )

                print()
                print(
                    "Existing data detected. "
                    "Replacing all FulfillAI table contents..."
                )

                truncate_target_tables(cursor)

                print("Existing dataset cleared inside transaction. ✓")

            print()
            print("Loading datasets...")
            print("-" * 64)

            for spec in TABLES:
                table = str(spec["table"])
                filename = str(spec["file"])
                columns = tuple(spec["columns"])

                path = DATA_DIR / filename

                print(
                    f"  {table:<24}",
                    end="",
                    flush=True,
                )

                copy_dataset(
                    cursor=cursor,
                    table=table,
                    columns=columns,
                    path=path,
                )

                statement = sql.SQL(
                    "SELECT COUNT(*) FROM {}"
                ).format(
                    sql.Identifier(table)
                )

                cursor.execute(statement)

                result = cursor.fetchone()

                if result is None:
                    raise RuntimeError(
                        f"Could not verify loaded table: {table}"
                    )

                loaded_count = int(result[0])
                expected_count = source_counts[table]

                if loaded_count != expected_count:
                    raise RuntimeError(
                        f"Row-count mismatch for {table}: "
                        f"expected {expected_count:,}, "
                        f"found {loaded_count:,}"
                    )

                print(
                    f"{loaded_count:>10,} rows  ✓"
                )

            reset_serial_sequences(cursor)

            final_counts = database_row_counts(cursor)

            print()
            print("POST-LOAD VERIFICATION")
            print("-" * 64)

            failures: list[str] = []

            for spec in TABLES:
                table = str(spec["table"])

                expected = source_counts[table]
                actual = final_counts[table]

                passed = expected == actual

                marker = "✓" if passed else "✗"

                print(
                    f"  {marker} "
                    f"{table:<22} "
                    f"{actual:>10,}"
                )

                if not passed:
                    failures.append(
                        f"{table}: expected "
                        f"{expected:,}, got {actual:,}"
                    )

            if failures:
                raise RuntimeError(
                    "Post-load verification failed:\n"
                    + "\n".join(failures)
                )

            total = sum(final_counts.values())

            print("-" * 64)
            print(
                f"  {'TOTAL':<24} "
                f"{total:>10,}"
            )

        # Nothing reaches PostgreSQL permanently until this line.
        connection.commit()

        print()
        print("=" * 64)
        print("POSTGRESQL LOAD COMMITTED SUCCESSFULLY ✓")
        print("=" * 64)
        print()
        print(
            f"{sum(source_counts.values()):,} "
            "interconnected FulfillAI records are now "
            "stored in PostgreSQL."
        )

    except Exception:
        connection.rollback()

        print()
        print("=" * 64)
        print("LOAD FAILED — TRANSACTION ROLLED BACK")
        print("=" * 64)
        print(
            "PostgreSQL was returned to its state "
            "before this load attempt."
        )

        raise

    finally:
        connection.close()


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------

def main() -> None:
    args = parse_args()

    if args.replace and not args.load:
        raise SystemExit(
            "--replace can only be used together with --load"
        )

    load_environment()

    try:
        source_counts = validate_source_files()
        db_config = database_config()
        database_counts = run_database_preflight(db_config)

        print()
        print("=" * 64)
        print("PRE-FLIGHT CHECK PASSED ✓")
        print("=" * 64)

        database_is_empty = all(
            count == 0
            for count in database_counts.values()
        )

        if database_is_empty:
            print("Target FulfillAI tables are empty.")
        else:
            print("Target FulfillAI tables currently contain data.")

        if not args.load:
            print()
            print("No database data was modified.")
            print(
                "Run again with --load when ready "
                "to perform the transactional load."
            )
            return

        perform_load(
            db_config=db_config,
            source_counts=source_counts,
            replace=args.replace,
        )

    except Exception as exc:
        print()
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
