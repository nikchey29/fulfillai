from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = PROJECT_ROOT / "configs" / "data_generation.yaml"
DATA_DIR = PROJECT_ROOT / "data" / "raw" / "synthetic"


class DataValidationError(Exception):
    """Raised when generated synthetic data fails validation."""


def load_config() -> dict[str, Any]:
    with CONFIG_PATH.open("r", encoding="utf-8") as file:
        return yaml.safe_load(file)


def load_datasets() -> dict[str, pd.DataFrame]:
    files = {
        "categories": "product_categories.csv",
        "products": "products.csv",
        "warehouses": "warehouses.csv",
        "customers": "customers.csv",
    }

    datasets = {}

    for name, filename in files.items():
        path = DATA_DIR / filename

        if not path.exists():
            raise DataValidationError(
                f"Required dataset does not exist: {path}"
            )

        datasets[name] = pd.read_csv(path)

    return datasets


def require(condition: bool, message: str) -> None:
    if not condition:
        raise DataValidationError(message)


def validate_categories(
    categories: pd.DataFrame,
    expected_count: int,
) -> None:
    require(
        len(categories) == expected_count,
        f"Expected {expected_count} categories, found {len(categories)}.",
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
        "Categories contain missing values.",
    )


def validate_products(
    products: pd.DataFrame,
    categories: pd.DataFrame,
    expected_count: int,
) -> None:
    require(
        len(products) == expected_count,
        f"Expected {expected_count} products, found {len(products)}.",
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
        (products["unit_price"] >= 0).all(),
        "Products contain negative unit prices.",
    )

    require(
        (products["unit_cost"] >= 0).all(),
        "Products contain negative unit costs.",
    )

    require(
        (products["unit_price"] >= products["unit_cost"]).all(),
        "A product has unit_price below unit_cost.",
    )

    require(
        (products["weight_kg"] > 0).all(),
        "Products contain non-positive weights.",
    )

    valid_categories = set(categories["category_id"])

    require(
        products["category_id"].isin(valid_categories).all(),
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


def validate_warehouses(
    warehouses: pd.DataFrame,
    expected_count: int,
    valid_countries: set[str],
) -> None:
    require(
        len(warehouses) == expected_count,
        f"Expected {expected_count} warehouses, found {len(warehouses)}.",
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
        warehouses["country_code"].isin(valid_countries).all(),
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


def validate_customers(
    customers: pd.DataFrame,
    expected_count: int,
    valid_countries: set[str],
) -> None:
    require(
        len(customers) == expected_count,
        f"Expected {expected_count} customers, found {len(customers)}.",
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
        customers["country_code"].isin(valid_countries).all(),
        "Customers contain unsupported country codes.",
    )

    require(
        customers["region"].astype(str).str.strip().ne("").all(),
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


def main() -> None:
    config = load_config()
    datasets = load_datasets()

    scale = config["scale"]
    valid_countries = set(config["geography"]["countries"])

    print("Validating FulfillAI synthetic master data...")
    print()

    validate_categories(
        datasets["categories"],
        expected_count=int(scale["categories"]),
    )
    print("✓ product_categories")

    validate_products(
        datasets["products"],
        datasets["categories"],
        expected_count=int(scale["products"]),
    )
    print("✓ products")

    validate_warehouses(
        datasets["warehouses"],
        expected_count=int(scale["warehouses"]),
        valid_countries=valid_countries,
    )
    print("✓ warehouses")

    validate_customers(
        datasets["customers"],
        expected_count=int(scale["customers"]),
        valid_countries=valid_countries,
    )
    print("✓ customers")

    print()
    print("All master-data validation checks passed.")


if __name__ == "__main__":
    main()