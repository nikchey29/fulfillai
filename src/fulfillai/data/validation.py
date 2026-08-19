from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import yaml


# ---------------------------------------------------------------------------
# Project paths
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = PROJECT_ROOT / "configs" / "data_generation.yaml"
DATA_DIR = PROJECT_ROOT / "data" / "raw" / "synthetic"


# ---------------------------------------------------------------------------
# Custom validation exception
# ---------------------------------------------------------------------------

class DataValidationError(Exception):
    """Raised when generated synthetic data fails validation."""


# ---------------------------------------------------------------------------
# Configuration and dataset loading
# ---------------------------------------------------------------------------

def load_config() -> dict[str, Any]:
    """Load synthetic-data generation configuration."""

    with CONFIG_PATH.open(
        "r",
        encoding="utf-8",
    ) as file:
        return yaml.safe_load(file)


def load_datasets() -> dict[str, pd.DataFrame]:
    """Load all generated master and inventory datasets."""

    files = {
        "categories": "product_categories.csv",
        "products": "products.csv",
        "warehouses": "warehouses.csv",
        "customers": "customers.csv",
        "inventory": "inventory.csv",
    }

    datasets: dict[str, pd.DataFrame] = {}

    for name, filename in files.items():

        path = DATA_DIR / filename

        if not path.exists():
            raise DataValidationError(
                f"Required dataset does not exist: {path}"
            )

        datasets[name] = pd.read_csv(path)

    return datasets


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------

def require(
    condition: bool,
    message: str,
) -> None:
    """Raise a validation error when a condition is false."""

    if not condition:
        raise DataValidationError(message)


def require_columns(
    dataframe: pd.DataFrame,
    expected_columns: set[str],
    dataset_name: str,
) -> None:
    """Ensure a dataset contains all required columns."""

    actual_columns = set(dataframe.columns)

    missing_columns = (
        expected_columns - actual_columns
    )

    require(
        not missing_columns,
        (
            f"{dataset_name} is missing required columns: "
            f"{sorted(missing_columns)}"
        ),
    )


# ---------------------------------------------------------------------------
# Product-category validation
# ---------------------------------------------------------------------------

def validate_categories(
    categories: pd.DataFrame,
    expected_count: int,
) -> None:
    """Validate product-category master data."""

    require_columns(
        categories,
        {
            "category_id",
            "category_name",
        },
        "product_categories",
    )

    require(
        len(categories) == expected_count,
        (
            f"Expected {expected_count} categories, "
            f"found {len(categories)}."
        ),
    )

    require(
        categories["category_id"].is_unique,
        "category_id contains duplicates.",
    )

    require(
        categories["category_name"].is_unique,
        "category_name contains duplicates.",
    )

    require(
        not categories.isnull().any().any(),
        "Product categories contain missing values.",
    )

    require(
        (categories["category_id"] > 0).all(),
        "category_id must always be positive.",
    )

    require(
        categories["category_name"]
        .astype(str)
        .str.strip()
        .ne("")
        .all(),
        "Product categories contain blank names.",
    )


# ---------------------------------------------------------------------------
# Product validation
# ---------------------------------------------------------------------------

def validate_products(
    products: pd.DataFrame,
    categories: pd.DataFrame,
    expected_count: int,
) -> None:
    """Validate generated product master data."""

    require_columns(
        products,
        {
            "product_id",
            "sku",
            "product_name",
            "category_id",
            "unit_price",
            "unit_cost",
            "weight_kg",
            "active",
            "created_at",
        },
        "products",
    )

    require(
        len(products) == expected_count,
        (
            f"Expected {expected_count} products, "
            f"found {len(products)}."
        ),
    )

    require(
        products["product_id"].is_unique,
        "product_id contains duplicates.",
    )

    require(
        products["sku"].is_unique,
        "sku contains duplicates.",
    )

    require(
        not products.isnull().any().any(),
        "Products contain missing values.",
    )

    require(
        (products["product_id"] > 0).all(),
        "product_id must always be positive.",
    )

    require(
        products["sku"]
        .astype(str)
        .str.strip()
        .ne("")
        .all(),
        "Products contain blank SKUs.",
    )

    require(
        products["product_name"]
        .astype(str)
        .str.strip()
        .ne("")
        .all(),
        "Products contain blank product names.",
    )

    require(
        (products["unit_price"] >= 0).all(),
        "Products contain negative unit prices.",
    )

    require(
        (products["unit_cost"] >= 0).all(),
        "Products contain negative unit costs.",
    )

    require(
        (
            products["unit_price"]
            >= products["unit_cost"]
        ).all(),
        "A product has unit_price below unit_cost.",
    )

    require(
        (products["weight_kg"] > 0).all(),
        "Products contain non-positive weights.",
    )

    valid_categories = set(
        categories["category_id"]
    )

    require(
        products["category_id"]
        .isin(valid_categories)
        .all(),
        "Products contain invalid category foreign keys.",
    )

    parsed_dates = pd.to_datetime(
        products["created_at"],
        utc=True,
        errors="coerce",
    )

    require(
        parsed_dates.notna().all(),
        "Products contain invalid created_at timestamps.",
    )


# ---------------------------------------------------------------------------
# Warehouse validation
# ---------------------------------------------------------------------------

def validate_warehouses(
    warehouses: pd.DataFrame,
    expected_count: int,
    valid_countries: set[str],
) -> None:
    """Validate generated warehouse master data."""

    require_columns(
        warehouses,
        {
            "warehouse_id",
            "warehouse_code",
            "warehouse_name",
            "city",
            "country_code",
            "capacity_units",
            "created_at",
        },
        "warehouses",
    )

    require(
        len(warehouses) == expected_count,
        (
            f"Expected {expected_count} warehouses, "
            f"found {len(warehouses)}."
        ),
    )

    require(
        warehouses["warehouse_id"].is_unique,
        "warehouse_id contains duplicates.",
    )

    require(
        warehouses["warehouse_code"].is_unique,
        "warehouse_code contains duplicates.",
    )

    require(
        not warehouses.isnull().any().any(),
        "Warehouses contain missing values.",
    )

    require(
        (warehouses["warehouse_id"] > 0).all(),
        "warehouse_id must always be positive.",
    )

    require(
        warehouses["country_code"]
        .isin(valid_countries)
        .all(),
        "Warehouses contain unsupported country codes.",
    )

    require(
        (warehouses["capacity_units"] > 0).all(),
        "Warehouse capacity must be positive.",
    )

    parsed_dates = pd.to_datetime(
        warehouses["created_at"],
        utc=True,
        errors="coerce",
    )

    require(
        parsed_dates.notna().all(),
        "Warehouses contain invalid created_at timestamps.",
    )


# ---------------------------------------------------------------------------
# Customer validation
# ---------------------------------------------------------------------------

def validate_customers(
    customers: pd.DataFrame,
    expected_count: int,
    valid_countries: set[str],
) -> None:
    """Validate generated customer master data."""

    require_columns(
        customers,
        {
            "customer_id",
            "customer_external_id",
            "country_code",
            "region",
            "created_at",
        },
        "customers",
    )

    require(
        len(customers) == expected_count,
        (
            f"Expected {expected_count} customers, "
            f"found {len(customers)}."
        ),
    )

    require(
        customers["customer_id"].is_unique,
        "customer_id contains duplicates.",
    )

    require(
        customers["customer_external_id"].is_unique,
        "customer_external_id contains duplicates.",
    )

    require(
        not customers.isnull().any().any(),
        "Customers contain missing values.",
    )

    require(
        (customers["customer_id"] > 0).all(),
        "customer_id must always be positive.",
    )

    require(
        customers["country_code"]
        .isin(valid_countries)
        .all(),
        "Customers contain unsupported country codes.",
    )

    require(
        customers["region"]
        .astype(str)
        .str.strip()
        .ne("")
        .all(),
        "Customers contain blank regions.",
    )

    parsed_dates = pd.to_datetime(
        customers["created_at"],
        utc=True,
        errors="coerce",
    )

    require(
        parsed_dates.notna().all(),
        "Customers contain invalid created_at timestamps.",
    )


# ---------------------------------------------------------------------------
# Inventory validation
# ---------------------------------------------------------------------------

def validate_inventory(
    inventory: pd.DataFrame,
    products: pd.DataFrame,
    warehouses: pd.DataFrame,
    config: dict[str, Any],
) -> None:
    """
    Validate initial warehouse inventory.

    Checks include:
    - valid product and warehouse foreign keys
    - unique warehouse/product combinations
    - non-negative stock
    - valid reservation quantities
    - reorder-point configuration
    - product coverage
    - warehouse coverage
    - meaningful low-stock examples
    """

    require_columns(
        inventory,
        {
            "warehouse_id",
            "product_id",
            "on_hand_qty",
            "reserved_qty",
            "reorder_point",
            "updated_at",
        },
        "inventory",
    )

    require(
        len(inventory) > 0,
        "Inventory dataset is empty.",
    )

    require(
        not inventory.isnull().any().any(),
        "Inventory contains missing values.",
    )

    # ------------------------------------------------------------------
    # Composite primary-key equivalent
    # ------------------------------------------------------------------

    duplicate_pairs = inventory.duplicated(
        subset=[
            "warehouse_id",
            "product_id",
        ]
    )

    require(
        not duplicate_pairs.any(),
        (
            "Inventory contains duplicate "
            "(warehouse_id, product_id) combinations."
        ),
    )

    # ------------------------------------------------------------------
    # Foreign-key integrity
    # ------------------------------------------------------------------

    valid_product_ids = set(
        products["product_id"]
    )

    valid_warehouse_ids = set(
        warehouses["warehouse_id"]
    )

    require(
        inventory["product_id"]
        .isin(valid_product_ids)
        .all(),
        "Inventory contains invalid product foreign keys.",
    )

    require(
        inventory["warehouse_id"]
        .isin(valid_warehouse_ids)
        .all(),
        "Inventory contains invalid warehouse foreign keys.",
    )

    # ------------------------------------------------------------------
    # Quantity checks
    # ------------------------------------------------------------------

    require(
        (inventory["on_hand_qty"] >= 0).all(),
        "Inventory contains negative on_hand_qty values.",
    )

    require(
        (inventory["reserved_qty"] >= 0).all(),
        "Inventory contains negative reserved_qty values.",
    )

    require(
        (
            inventory["reserved_qty"]
            <= inventory["on_hand_qty"]
        ).all(),
        (
            "Inventory contains reserved quantities "
            "greater than stock on hand."
        ),
    )

    # Initial inventory should not yet have reservations.
    require(
        (inventory["reserved_qty"] == 0).all(),
        (
            "Initial inventory should begin with "
            "reserved_qty equal to zero."
        ),
    )

    # ------------------------------------------------------------------
    # Inventory configuration checks
    # ------------------------------------------------------------------

    inventory_config = config["inventory"]

    stock_max = int(
        inventory_config["initial_stock_max"]
    )

    reorder_min = int(
        inventory_config["reorder_point_min"]
    )

    reorder_max = int(
        inventory_config["reorder_point_max"]
    )

    require(
        (inventory["on_hand_qty"] <= stock_max).all(),
        (
            "Inventory contains stock greater than "
            "configured initial_stock_max."
        ),
    )

    require(
        (
            inventory["reorder_point"]
            >= reorder_min
        ).all(),
        (
            "Inventory contains reorder points below "
            "configured reorder_point_min."
        ),
    )

    require(
        (
            inventory["reorder_point"]
            <= reorder_max
        ).all(),
        (
            "Inventory contains reorder points above "
            "configured reorder_point_max."
        ),
    )

    # ------------------------------------------------------------------
    # Product coverage
    # ------------------------------------------------------------------

    represented_products = set(
        inventory["product_id"]
    )

    require(
        represented_products == valid_product_ids,
        (
            "Not every product is represented "
            "in the inventory dataset."
        ),
    )

    product_warehouse_counts = (
        inventory
        .groupby("product_id")["warehouse_id"]
        .nunique()
    )

    require(
        (product_warehouse_counts >= 2).all(),
        (
            "Every product must initially be stocked "
            "in at least two warehouses."
        ),
    )

    require(
        (
            product_warehouse_counts
            <= len(valid_warehouse_ids)
        ).all(),
        (
            "A product is associated with more warehouses "
            "than actually exist."
        ),
    )

    # ------------------------------------------------------------------
    # Warehouse coverage
    # ------------------------------------------------------------------

    represented_warehouses = set(
        inventory["warehouse_id"]
    )

    require(
        represented_warehouses == valid_warehouse_ids,
        (
            "Not every warehouse is represented "
            "in the inventory dataset."
        ),
    )

    # ------------------------------------------------------------------
    # Dataset-size sanity bounds
    # ------------------------------------------------------------------

    minimum_expected_rows = (
        len(valid_product_ids) * 2
    )

    maximum_expected_rows = (
        len(valid_product_ids)
        * len(valid_warehouse_ids)
    )

    require(
        len(inventory) >= minimum_expected_rows,
        (
            f"Inventory has only {len(inventory)} rows; "
            f"expected at least {minimum_expected_rows}."
        ),
    )

    require(
        len(inventory) <= maximum_expected_rows,
        (
            f"Inventory has {len(inventory)} rows; "
            f"maximum possible is {maximum_expected_rows}."
        ),
    )

    # ------------------------------------------------------------------
    # Low-stock scenarios
    # ------------------------------------------------------------------

    low_stock_mask = (
        inventory["on_hand_qty"]
        <= inventory["reorder_point"]
    )

    low_stock_count = int(
        low_stock_mask.sum()
    )

    require(
        low_stock_count > 0,
        (
            "Inventory contains no low-stock positions. "
            "Synthetic data should contain replenishment scenarios."
        ),
    )

    require(
        low_stock_count < len(inventory),
        (
            "Every inventory position is low stock; "
            "expected a mixture of healthy and low-stock positions."
        ),
    )

    # ------------------------------------------------------------------
    # Timestamp validation
    # ------------------------------------------------------------------

    parsed_dates = pd.to_datetime(
        inventory["updated_at"],
        utc=True,
        errors="coerce",
    )

    require(
        parsed_dates.notna().all(),
        "Inventory contains invalid updated_at timestamps.",
    )


# ---------------------------------------------------------------------------
# Main validation pipeline
# ---------------------------------------------------------------------------

def main() -> None:
    """Validate all generated FulfillAI master datasets."""

    config = load_config()

    datasets = load_datasets()

    scale = config["scale"]

    valid_countries = set(
        config["geography"]["countries"]
    )

    print(
        "Validating FulfillAI synthetic master data..."
    )

    print()

    # ------------------------------------------------------------------
    # Categories
    # ------------------------------------------------------------------

    validate_categories(
        datasets["categories"],
        expected_count=int(
            scale["categories"]
        ),
    )

    print("✓ product_categories")

    # ------------------------------------------------------------------
    # Products
    # ------------------------------------------------------------------

    validate_products(
        datasets["products"],
        datasets["categories"],
        expected_count=int(
            scale["products"]
        ),
    )

    print("✓ products")

    # ------------------------------------------------------------------
    # Warehouses
    # ------------------------------------------------------------------

    validate_warehouses(
        datasets["warehouses"],
        expected_count=int(
            scale["warehouses"]
        ),
        valid_countries=valid_countries,
    )

    print("✓ warehouses")

    # ------------------------------------------------------------------
    # Customers
    # ------------------------------------------------------------------

    validate_customers(
        datasets["customers"],
        expected_count=int(
            scale["customers"]
        ),
        valid_countries=valid_countries,
    )

    print("✓ customers")

    # ------------------------------------------------------------------
    # Inventory
    # ------------------------------------------------------------------

    validate_inventory(
        datasets["inventory"],
        datasets["products"],
        datasets["warehouses"],
        config=config,
    )

    print("✓ inventory")

    # ------------------------------------------------------------------
    # Validation summary
    # ------------------------------------------------------------------

    inventory = datasets["inventory"]

    low_stock_count = int(
        (
            inventory["on_hand_qty"]
            <= inventory["reorder_point"]
        ).sum()
    )

    low_stock_rate = (
        low_stock_count
        / len(inventory)
        * 100
    )

    print()
    print("Inventory validation summary:")

    print(
        f"  inventory positions : "
        f"{len(inventory):,}"
    )

    print(
        f"  products represented: "
        f"{inventory['product_id'].nunique():,}"
    )

    print(
        f"  warehouses          : "
        f"{inventory['warehouse_id'].nunique():,}"
    )

    print(
        f"  low-stock positions : "
        f"{low_stock_count:,}"
    )

    print(
        f"  low-stock rate      : "
        f"{low_stock_rate:.2f}%"
    )

    print()

    print(
        "All master-data and inventory validation checks passed."
    )


if __name__ == "__main__":
    main()