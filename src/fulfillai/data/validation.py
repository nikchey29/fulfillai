from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml


# ---------------------------------------------------------------------------
# Project paths
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[3]

DATA_DIR = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "synthetic"
)

CONFIG_PATH = (
    PROJECT_ROOT
    / "configs"
    / "data_generation.yaml"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_config() -> dict:
    """Load data-generation configuration."""

    with CONFIG_PATH.open(
        "r",
        encoding="utf-8",
    ) as file:
        return yaml.safe_load(file)


def load_csv(
    filename: str,
) -> pd.DataFrame:
    """Load one generated synthetic dataset."""

    path = DATA_DIR / filename

    if not path.exists():
        raise FileNotFoundError(
            f"Expected generated dataset not found: {path}"
        )

    return pd.read_csv(path)


def require_columns(
    dataframe: pd.DataFrame,
    required_columns: list[str],
    dataset_name: str,
) -> None:
    """Ensure expected columns exist."""

    missing = (
        set(required_columns)
        - set(dataframe.columns)
    )

    if missing:
        raise AssertionError(
            f"{dataset_name}: missing columns: "
            f"{sorted(missing)}"
        )


def require_no_missing(
    dataframe: pd.DataFrame,
    columns: list[str],
    dataset_name: str,
) -> None:
    """Ensure required fields do not contain null values."""

    for column in columns:

        missing_count = int(
            dataframe[column]
            .isna()
            .sum()
        )

        if missing_count:
            raise AssertionError(
                f"{dataset_name}.{column}: "
                f"{missing_count} missing values"
            )


def require_unique(
    dataframe: pd.DataFrame,
    columns: list[str],
    dataset_name: str,
) -> None:
    """Ensure one or more columns form a unique key."""

    duplicate_count = int(
        dataframe
        .duplicated(
            subset=columns
        )
        .sum()
    )

    if duplicate_count:
        raise AssertionError(
            f"{dataset_name}: "
            f"{duplicate_count} duplicate rows "
            f"for key {columns}"
        )


# ---------------------------------------------------------------------------
# Product-category validation
# ---------------------------------------------------------------------------

def validate_product_categories(
    categories: pd.DataFrame,
    config: dict,
) -> None:

    require_columns(
        categories,
        [
            "category_id",
            "category_name",
        ],
        "product_categories",
    )

    require_no_missing(
        categories,
        [
            "category_id",
            "category_name",
        ],
        "product_categories",
    )

    require_unique(
        categories,
        ["category_id"],
        "product_categories",
    )

    require_unique(
        categories,
        ["category_name"],
        "product_categories",
    )

    expected_count = int(
        config["scale"]["categories"]
    )

    if len(categories) != expected_count:
        raise AssertionError(
            "product_categories: expected "
            f"{expected_count} rows, "
            f"found {len(categories)}"
        )

    if (
        categories["category_id"]
        .astype(int)
        .le(0)
        .any()
    ):
        raise AssertionError(
            "product_categories: "
            "category_id must be positive"
        )


# ---------------------------------------------------------------------------
# Product validation
# ---------------------------------------------------------------------------

def validate_products(
    products: pd.DataFrame,
    categories: pd.DataFrame,
    config: dict,
) -> None:

    require_columns(
        products,
        [
            "product_id",
            "sku",
            "product_name",
            "category_id",
            "unit_price",
            "unit_cost",
            "weight_kg",
            "active",
            "created_at",
        ],
        "products",
    )

    require_no_missing(
        products,
        [
            "product_id",
            "sku",
            "product_name",
            "category_id",
            "unit_price",
            "unit_cost",
            "active",
            "created_at",
        ],
        "products",
    )

    require_unique(
        products,
        ["product_id"],
        "products",
    )

    require_unique(
        products,
        ["sku"],
        "products",
    )

    expected_count = int(
        config["scale"]["products"]
    )

    if len(products) != expected_count:
        raise AssertionError(
            "products: expected "
            f"{expected_count} rows, "
            f"found {len(products)}"
        )

    if (
        products["unit_price"]
        .astype(float)
        .lt(0)
        .any()
    ):
        raise AssertionError(
            "products: negative unit_price detected"
        )

    if (
        products["unit_cost"]
        .astype(float)
        .lt(0)
        .any()
    ):
        raise AssertionError(
            "products: negative unit_cost detected"
        )

    if (
        products["unit_cost"]
        .astype(float)
        .gt(
            products["unit_price"]
            .astype(float)
        )
        .any()
    ):
        raise AssertionError(
            "products: unit_cost exceeds unit_price"
        )

    weight_values = pd.to_numeric(
        products["weight_kg"],
        errors="coerce",
    )

    invalid_weight = (
        weight_values
        .dropna()
        .lt(0)
        .any()
    )

    if invalid_weight:
        raise AssertionError(
            "products: negative weight detected"
        )

    unknown_categories = (
        ~products["category_id"]
        .isin(
            categories["category_id"]
        )
    ).sum()

    if unknown_categories:
        raise AssertionError(
            "products: "
            f"{unknown_categories} invalid category references"
        )


# ---------------------------------------------------------------------------
# Warehouse validation
# ---------------------------------------------------------------------------

def validate_warehouses(
    warehouses: pd.DataFrame,
    config: dict,
) -> None:

    require_columns(
        warehouses,
        [
            "warehouse_id",
            "warehouse_code",
            "warehouse_name",
            "city",
            "country_code",
            "capacity_units",
            "created_at",
        ],
        "warehouses",
    )

    require_no_missing(
        warehouses,
        [
            "warehouse_id",
            "warehouse_code",
            "warehouse_name",
            "city",
            "country_code",
            "capacity_units",
            "created_at",
        ],
        "warehouses",
    )

    require_unique(
        warehouses,
        ["warehouse_id"],
        "warehouses",
    )

    require_unique(
        warehouses,
        ["warehouse_code"],
        "warehouses",
    )

    expected_count = int(
        config["scale"]["warehouses"]
    )

    if len(warehouses) != expected_count:
        raise AssertionError(
            "warehouses: expected "
            f"{expected_count} rows, "
            f"found {len(warehouses)}"
        )

    if (
        warehouses["capacity_units"]
        .astype(int)
        .le(0)
        .any()
    ):
        raise AssertionError(
            "warehouses: capacity must be positive"
        )

    allowed_countries = set(
        config["geography"]["countries"]
    )

    invalid_countries = (
        ~warehouses["country_code"]
        .isin(allowed_countries)
    ).sum()

    if invalid_countries:
        raise AssertionError(
            "warehouses: "
            f"{invalid_countries} invalid country codes"
        )


# ---------------------------------------------------------------------------
# Customer validation
# ---------------------------------------------------------------------------

def validate_customers(
    customers: pd.DataFrame,
    config: dict,
) -> None:

    require_columns(
        customers,
        [
            "customer_id",
            "customer_external_id",
            "country_code",
            "region",
            "created_at",
        ],
        "customers",
    )

    require_no_missing(
        customers,
        [
            "customer_id",
            "customer_external_id",
            "country_code",
            "region",
            "created_at",
        ],
        "customers",
    )

    require_unique(
        customers,
        ["customer_id"],
        "customers",
    )

    require_unique(
        customers,
        ["customer_external_id"],
        "customers",
    )

    expected_count = int(
        config["scale"]["customers"]
    )

    if len(customers) != expected_count:
        raise AssertionError(
            "customers: expected "
            f"{expected_count} rows, "
            f"found {len(customers)}"
        )

    allowed_countries = set(
        config["geography"]["countries"]
    )

    invalid_countries = (
        ~customers["country_code"]
        .isin(allowed_countries)
    ).sum()

    if invalid_countries:
        raise AssertionError(
            "customers: "
            f"{invalid_countries} invalid country codes"
        )


# ---------------------------------------------------------------------------
# Inventory validation
# ---------------------------------------------------------------------------

def validate_inventory(
    inventory: pd.DataFrame,
    products: pd.DataFrame,
    warehouses: pd.DataFrame,
) -> None:

    require_columns(
        inventory,
        [
            "warehouse_id",
            "product_id",
            "on_hand_qty",
            "reserved_qty",
            "reorder_point",
            "updated_at",
        ],
        "inventory",
    )

    require_no_missing(
        inventory,
        [
            "warehouse_id",
            "product_id",
            "on_hand_qty",
            "reserved_qty",
            "reorder_point",
            "updated_at",
        ],
        "inventory",
    )

    require_unique(
        inventory,
        [
            "warehouse_id",
            "product_id",
        ],
        "inventory",
    )

    if (
        inventory["on_hand_qty"]
        .astype(int)
        .lt(0)
        .any()
    ):
        raise AssertionError(
            "inventory: negative on_hand_qty"
        )

    if (
        inventory["reserved_qty"]
        .astype(int)
        .lt(0)
        .any()
    ):
        raise AssertionError(
            "inventory: negative reserved_qty"
        )

    if (
        inventory["reorder_point"]
        .astype(int)
        .lt(0)
        .any()
    ):
        raise AssertionError(
            "inventory: negative reorder_point"
        )

    if (
        inventory["reserved_qty"]
        .astype(int)
        .gt(
            inventory["on_hand_qty"]
            .astype(int)
        )
        .any()
    ):
        raise AssertionError(
            "inventory: reserved_qty exceeds on_hand_qty"
        )

    invalid_products = (
        ~inventory["product_id"]
        .isin(
            products["product_id"]
        )
    ).sum()

    if invalid_products:
        raise AssertionError(
            "inventory: "
            f"{invalid_products} invalid product references"
        )

    invalid_warehouses = (
        ~inventory["warehouse_id"]
        .isin(
            warehouses["warehouse_id"]
        )
    ).sum()

    if invalid_warehouses:
        raise AssertionError(
            "inventory: "
            f"{invalid_warehouses} invalid warehouse references"
        )

    represented_products = int(
        inventory[
            "product_id"
        ].nunique()
    )

    if represented_products != len(products):
        raise AssertionError(
            "inventory does not represent every product"
        )

    represented_warehouses = int(
        inventory[
            "warehouse_id"
        ].nunique()
    )

    if represented_warehouses != len(warehouses):
        raise AssertionError(
            "inventory does not represent every warehouse"
        )


# ---------------------------------------------------------------------------
# Orders validation
# ---------------------------------------------------------------------------

def validate_orders(
    orders: pd.DataFrame,
    customers: pd.DataFrame,
    warehouses: pd.DataFrame,
    config: dict,
) -> None:

    require_columns(
        orders,
        [
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
        ],
        "orders",
    )

    require_no_missing(
        orders,
        [
            "order_id",
            "order_external_id",
            "customer_id",
            "warehouse_id",
            "order_status",
            "shipping_method",
            "destination_country",
            "order_ts",
            "promised_delivery_ts",
            "total_amount",
            "created_at",
        ],
        "orders",
    )

    require_unique(
        orders,
        ["order_id"],
        "orders",
    )

    require_unique(
        orders,
        ["order_external_id"],
        "orders",
    )

    expected_count = int(
        config["scale"]["target_orders"]
    )

    if len(orders) != expected_count:
        raise AssertionError(
            "orders: expected "
            f"{expected_count:,} rows, "
            f"found {len(orders):,}"
        )

    unknown_customers = (
        ~orders["customer_id"]
        .isin(
            customers["customer_id"]
        )
    ).sum()

    if unknown_customers:
        raise AssertionError(
            "orders: "
            f"{unknown_customers} invalid customer references"
        )

    unknown_warehouses = (
        ~orders["warehouse_id"]
        .isin(
            warehouses["warehouse_id"]
        )
    ).sum()

    if unknown_warehouses:
        raise AssertionError(
            "orders: "
            f"{unknown_warehouses} invalid warehouse references"
        )

    valid_statuses = {
        "created",
        "payment_confirmed",
        "processing",
        "packed",
        "shipped",
        "delivered",
        "cancelled",
    }

    invalid_statuses = (
        ~orders["order_status"]
        .isin(valid_statuses)
    ).sum()

    if invalid_statuses:
        raise AssertionError(
            "orders: "
            f"{invalid_statuses} invalid order statuses"
        )

    valid_shipping_methods = set(
        config["shipping"]["methods"].keys()
    )

    invalid_shipping = (
        ~orders["shipping_method"]
        .isin(valid_shipping_methods)
    ).sum()

    if invalid_shipping:
        raise AssertionError(
            "orders: "
            f"{invalid_shipping} invalid shipping methods"
        )

    if (
        orders["total_amount"]
        .astype(float)
        .lt(0)
        .any()
    ):
        raise AssertionError(
            "orders: negative total_amount detected"
        )

    order_ts = pd.to_datetime(
        orders["order_ts"],
        utc=True,
        errors="raise",
    )

    promised_ts = pd.to_datetime(
        orders["promised_delivery_ts"],
        utc=True,
        errors="raise",
    )

    created_at = pd.to_datetime(
        orders["created_at"],
        utc=True,
        errors="raise",
    )

    if (
        promised_ts
        < order_ts
    ).any():
        raise AssertionError(
            "orders: promised delivery occurs before order time"
        )

    if (
        created_at
        != order_ts
    ).any():
        raise AssertionError(
            "orders: created_at does not match order_ts"
        )

    customer_country = (
        customers
        .set_index("customer_id")[
            "country_code"
        ]
    )

    expected_country = (
        orders["customer_id"]
        .map(customer_country)
    )

    country_mismatches = int(
        (
            expected_country
            != orders[
                "destination_country"
            ]
        ).sum()
    )

    if country_mismatches:
        raise AssertionError(
            "orders: "
            f"{country_mismatches} customer/destination "
            "country mismatches"
        )

    warehouse_country = (
        warehouses
        .set_index("warehouse_id")[
            "country_code"
        ]
    )

    expected_warehouse_country = (
        orders["warehouse_id"]
        .map(warehouse_country)
    )

    routing_mismatches = int(
        (
            expected_warehouse_country
            != orders[
                "destination_country"
            ]
        ).sum()
    )

    if routing_mismatches:
        raise AssertionError(
            "orders: "
            f"{routing_mismatches} cross-country "
            "warehouse-routing mismatches"
        )


# ---------------------------------------------------------------------------
# Order-item validation
# ---------------------------------------------------------------------------

def validate_order_items(
    order_items: pd.DataFrame,
    orders: pd.DataFrame,
    products: pd.DataFrame,
    inventory: pd.DataFrame,
) -> None:

    require_columns(
        order_items,
        [
            "order_item_id",
            "order_id",
            "product_id",
            "quantity",
            "unit_price",
        ],
        "order_items",
    )

    require_no_missing(
        order_items,
        [
            "order_item_id",
            "order_id",
            "product_id",
            "quantity",
            "unit_price",
        ],
        "order_items",
    )

    require_unique(
        order_items,
        ["order_item_id"],
        "order_items",
    )

    require_unique(
        order_items,
        [
            "order_id",
            "product_id",
        ],
        "order_items",
    )

    if (
        order_items["quantity"]
        .astype(int)
        .le(0)
        .any()
    ):
        raise AssertionError(
            "order_items: quantity must be positive"
        )

    if (
        order_items["unit_price"]
        .astype(float)
        .lt(0)
        .any()
    ):
        raise AssertionError(
            "order_items: negative unit_price detected"
        )

    unknown_orders = (
        ~order_items["order_id"]
        .isin(
            orders["order_id"]
        )
    ).sum()

    if unknown_orders:
        raise AssertionError(
            "order_items: "
            f"{unknown_orders} invalid order references"
        )

    unknown_products = (
        ~order_items["product_id"]
        .isin(
            products["product_id"]
        )
    ).sum()

    if unknown_products:
        raise AssertionError(
            "order_items: "
            f"{unknown_products} invalid product references"
        )

    orders_without_items = (
        set(
            orders["order_id"]
        )
        - set(
            order_items["order_id"]
        )
    )

    if orders_without_items:
        raise AssertionError(
            "order_items: "
            f"{len(orders_without_items)} orders have no items"
        )

    # ---------------------------------------------------------------
    # Verify warehouse/product relationship
    # ---------------------------------------------------------------

    order_to_warehouse = (
        orders
        .set_index("order_id")[
            "warehouse_id"
        ]
    )

    item_warehouse = (
        order_items["order_id"]
        .map(order_to_warehouse)
    )

    inventory_pairs = pd.MultiIndex.from_frame(
        inventory[
            [
                "warehouse_id",
                "product_id",
            ]
        ]
    )

    item_pairs = pd.MultiIndex.from_arrays(
        [
            item_warehouse,
            order_items[
                "product_id"
            ],
        ]
    )

    missing_stock_pairs = int(
        (
            ~item_pairs.isin(
                inventory_pairs
            )
        ).sum()
    )

    if missing_stock_pairs:
        raise AssertionError(
            "order_items: "
            f"{missing_stock_pairs} products were ordered "
            "from warehouses that do not stock them"
        )

    # ---------------------------------------------------------------
    # Verify order totals
    # ---------------------------------------------------------------

    calculated_totals = (
        order_items
        .assign(
            subtotal=(
                order_items[
                    "quantity"
                ].astype(float)
                *
                order_items[
                    "unit_price"
                ].astype(float)
            )
        )
        .groupby(
            "order_id"
        )[
            "subtotal"
        ]
        .sum()
        .round(2)
    )

    recorded_totals = (
        orders
        .set_index(
            "order_id"
        )[
            "total_amount"
        ]
        .astype(float)
        .round(2)
    )

    aligned = (
        recorded_totals
        .to_frame("recorded")
        .join(
            calculated_totals
            .rename("calculated"),
            how="left",
        )
    )

    incorrect_totals = int(
        (
            aligned[
                "recorded"
            ]
            != aligned[
                "calculated"
            ]
        ).sum()
    )

    if incorrect_totals:
        raise AssertionError(
            "orders/order_items: "
            f"{incorrect_totals} incorrect order totals"
        )


# ---------------------------------------------------------------------------
# Behavioral validation
# ---------------------------------------------------------------------------

def validate_transaction_behavior(
    orders: pd.DataFrame,
    order_items: pd.DataFrame,
    config: dict,
) -> None:
    """
    Validate high-level generated business behavior.

    These are deliberately tolerant rather than requiring exact values.
    Random generation should reproduce the configured distributions
    approximately without making validation unnecessarily brittle.
    """

    expected_cancel_rate = float(
        config[
            "orders"
        ][
            "cancellation_rate"
        ]
    )

    actual_cancel_rate = float(
        (
            orders[
                "order_status"
            ]
            == "cancelled"
        )
        .mean()
    )

    if abs(
        actual_cancel_rate
        - expected_cancel_rate
    ) > 0.01:
        raise AssertionError(
            "orders: cancellation rate differs "
            "too far from configured value: "
            f"{actual_cancel_rate:.4f} vs "
            f"{expected_cancel_rate:.4f}"
        )

    expected_items = float(
        config[
            "orders"
        ][
            "average_items_per_order"
        ]
    )

    actual_items = (
        len(order_items)
        / len(orders)
    )

    if abs(
        actual_items
        - expected_items
    ) > 0.15:
        raise AssertionError(
            "order_items: average items/order differs "
            "too far from configured value: "
            f"{actual_items:.3f} vs "
            f"{expected_items:.3f}"
        )

    shipping_config = (
        config[
            "shipping"
        ][
            "methods"
        ]
    )

    shipping_actual = (
        orders[
            "shipping_method"
        ]
        .value_counts(
            normalize=True
        )
    )

    for method, expected_share in (
        shipping_config.items()
    ):

        actual_share = float(
            shipping_actual.get(
                method,
                0.0,
            )
        )

        expected_share = float(
            expected_share
        )

        if abs(
            actual_share
            - expected_share
        ) > 0.02:
            raise AssertionError(
                f"orders: {method} shipping share "
                f"{actual_share:.4f} differs too far "
                f"from configured {expected_share:.4f}"
            )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:

    print(
        "Validating FulfillAI synthetic data..."
    )

    print()

    config = load_config()

    categories = load_csv(
        "product_categories.csv"
    )

    products = load_csv(
        "products.csv"
    )

    warehouses = load_csv(
        "warehouses.csv"
    )

    customers = load_csv(
        "customers.csv"
    )

    inventory = load_csv(
        "inventory.csv"
    )

    orders = load_csv(
        "orders.csv"
    )

    order_items = load_csv(
        "order_items.csv"
    )

    validate_product_categories(
        categories,
        config,
    )

    print(
        "✓ product_categories"
    )

    validate_products(
        products,
        categories,
        config,
    )

    print(
        "✓ products"
    )

    validate_warehouses(
        warehouses,
        config,
    )

    print(
        "✓ warehouses"
    )

    validate_customers(
        customers,
        config,
    )

    print(
        "✓ customers"
    )

    validate_inventory(
        inventory,
        products,
        warehouses,
    )

    print(
        "✓ inventory"
    )

    validate_orders(
        orders,
        customers,
        warehouses,
        config,
    )

    print(
        "✓ orders"
    )

    validate_order_items(
        order_items,
        orders,
        products,
        inventory,
    )

    print(
        "✓ order_items"
    )

    validate_transaction_behavior(
        orders,
        order_items,
        config,
    )

    print(
        "✓ transactional behavior"
    )

    print()

    low_stock = inventory[
        inventory[
            "on_hand_qty"
        ]
        <= inventory[
            "reorder_point"
        ]
    ]

    cancellation_rate = (
        (
            orders[
                "order_status"
            ]
            == "cancelled"
        )
        .mean()
        * 100
    )

    average_items = (
        len(order_items)
        / len(orders)
    )

    print(
        "Validation summary:"
    )

    print(
        f"  inventory positions : "
        f"{len(inventory):,}"
    )

    print(
        f"  products represented : "
        f"{inventory['product_id'].nunique():,}"
    )

    print(
        f"  warehouses represented: "
        f"{inventory['warehouse_id'].nunique():,}"
    )

    print(
        f"  low-stock positions  : "
        f"{len(low_stock):,}"
    )

    print(
        f"  low-stock rate       : "
        f"{len(low_stock) / len(inventory) * 100:.2f}%"
    )

    print(
        f"  orders               : "
        f"{len(orders):,}"
    )

    print(
        f"  order items          : "
        f"{len(order_items):,}"
    )

    print(
        f"  avg items/order      : "
        f"{average_items:.2f}"
    )

    print(
        f"  cancellation rate    : "
        f"{cancellation_rate:.2f}%"
    )

    print()

    print(
        "Shipping distribution:"
    )

    shipping_distribution = (
        orders[
            "shipping_method"
        ]
        .value_counts(
            normalize=True
        )
        .mul(100)
        .round(2)
    )

    for method, percentage in (
        shipping_distribution.items()
    ):

        print(
            f"  {method:<10}: "
            f"{percentage:.2f}%"
        )

    print()

    print(
        "All seven-dataset validation checks passed."
    )


if __name__ == "__main__":
    main()