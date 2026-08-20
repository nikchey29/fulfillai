import json
from pathlib import Path

import pandas as pd
import yaml


# ============================================================
# Paths
# ============================================================

BASE_DIR = Path("data/raw/synthetic")
CONFIG_PATH = Path("configs/data_generation.yaml")


# ============================================================
# Helpers
# ============================================================

def load_config() -> dict:
    with CONFIG_PATH.open("r", encoding="utf-8") as file:
        return yaml.safe_load(file)


def load_csv(name: str, **kwargs) -> pd.DataFrame:
    path = BASE_DIR / f"{name}.csv"

    if not path.exists():
        raise FileNotFoundError(
            f"Required dataset not found: {path}"
        )

    return pd.read_csv(path, **kwargs)


def assert_no_missing(
    df: pd.DataFrame,
    columns: list[str],
    dataset_name: str,
) -> None:
    for column in columns:
        missing = df[column].isna().sum()

        assert missing == 0, (
            f"{dataset_name}.{column} "
            f"contains {missing} missing values"
        )


def assert_unique(
    df: pd.DataFrame,
    column: str,
    dataset_name: str,
) -> None:
    duplicates = df[column].duplicated().sum()

    assert duplicates == 0, (
        f"{dataset_name}.{column} "
        f"contains {duplicates} duplicates"
    )


# ============================================================
# Product Categories
# ============================================================

def validate_product_categories(
    categories: pd.DataFrame,
    config: dict,
) -> None:

    required = {
        "category_id",
        "category_name",
    }

    assert required.issubset(categories.columns), (
        "product_categories.csv missing columns: "
        f"{required - set(categories.columns)}"
    )

    assert_no_missing(
        categories,
        list(required),
        "product_categories",
    )

    assert_unique(
        categories,
        "category_id",
        "product_categories",
    )

    assert_unique(
        categories,
        "category_name",
        "product_categories",
    )

    expected = config["scale"]["categories"]

    assert len(categories) == expected, (
        f"Expected {expected} product categories, "
        f"found {len(categories)}"
    )


# ============================================================
# Products
# ============================================================

def validate_products(
    products: pd.DataFrame,
    categories: pd.DataFrame,
    config: dict,
) -> None:

    required = {
        "product_id",
        "sku",
        "product_name",
        "category_id",
        "unit_price",
        "unit_cost",
        "weight_kg",
        "active",
        "created_at",
    }

    assert required.issubset(products.columns), (
        "products.csv missing columns: "
        f"{required - set(products.columns)}"
    )

    assert_no_missing(
        products,
        [
            "product_id",
            "sku",
            "product_name",
            "category_id",
            "unit_price",
            "unit_cost",
        ],
        "products",
    )

    assert_unique(
        products,
        "product_id",
        "products",
    )

    assert_unique(
        products,
        "sku",
        "products",
    )

    expected = config["scale"]["products"]

    assert len(products) == expected, (
        f"Expected {expected} products, "
        f"found {len(products)}"
    )

    invalid_categories = (
        ~products["category_id"].isin(
            categories["category_id"]
        )
    ).sum()

    assert invalid_categories == 0, (
        f"{invalid_categories} products reference "
        "unknown categories"
    )

    assert (products["unit_price"] >= 0).all(), (
        "Negative product prices detected"
    )

    assert (products["unit_cost"] >= 0).all(), (
        "Negative product costs detected"
    )

    assert (
        products["unit_cost"]
        <= products["unit_price"]
    ).all(), (
        "Products found with unit_cost > unit_price"
    )

    weight = products["weight_kg"].dropna()

    assert (weight > 0).all(), (
        "Non-positive product weights detected"
    )


# ============================================================
# Warehouses
# ============================================================

def validate_warehouses(
    warehouses: pd.DataFrame,
    config: dict,
) -> None:

    required = {
        "warehouse_id",
        "warehouse_code",
        "warehouse_name",
        "city",
        "country_code",
        "capacity_units",
        "created_at",
    }

    assert required.issubset(warehouses.columns), (
        "warehouses.csv missing columns: "
        f"{required - set(warehouses.columns)}"
    )

    assert_no_missing(
        warehouses,
        list(required),
        "warehouses",
    )

    assert_unique(
        warehouses,
        "warehouse_id",
        "warehouses",
    )

    assert_unique(
        warehouses,
        "warehouse_code",
        "warehouses",
    )

    expected = config["scale"]["warehouses"]

    assert len(warehouses) == expected, (
        f"Expected {expected} warehouses, "
        f"found {len(warehouses)}"
    )

    assert (
        warehouses["capacity_units"] > 0
    ).all(), (
        "Warehouse capacity must be positive"
    )


# ============================================================
# Customers
# ============================================================

def validate_customers(
    customers: pd.DataFrame,
    config: dict,
) -> None:

    required = {
        "customer_id",
        "customer_external_id",
        "country_code",
        "region",
        "created_at",
    }

    assert required.issubset(customers.columns), (
        "customers.csv missing columns: "
        f"{required - set(customers.columns)}"
    )

    assert_no_missing(
        customers,
        [
            "customer_id",
            "customer_external_id",
            "country_code",
        ],
        "customers",
    )

    assert_unique(
        customers,
        "customer_id",
        "customers",
    )

    assert_unique(
        customers,
        "customer_external_id",
        "customers",
    )

    expected = config["scale"]["customers"]

    assert len(customers) == expected, (
        f"Expected {expected} customers, "
        f"found {len(customers)}"
    )

    allowed_countries = set(
        config["geography"]["countries"]
    )

    unknown = (
        ~customers["country_code"].isin(
            allowed_countries
        )
    ).sum()

    assert unknown == 0, (
        f"{unknown} customers have invalid country codes"
    )


# ============================================================
# Inventory
# ============================================================

def validate_inventory(
    inventory: pd.DataFrame,
    products: pd.DataFrame,
    warehouses: pd.DataFrame,
) -> dict:

    required = {
        "warehouse_id",
        "product_id",
        "on_hand_qty",
        "reserved_qty",
        "reorder_point",
        "updated_at",
    }

    assert required.issubset(inventory.columns), (
        "inventory.csv missing columns: "
        f"{required - set(inventory.columns)}"
    )

    assert_no_missing(
        inventory,
        list(required),
        "inventory",
    )

    duplicates = inventory.duplicated(
        ["warehouse_id", "product_id"]
    ).sum()

    assert duplicates == 0, (
        f"{duplicates} duplicate warehouse/product "
        "inventory positions"
    )

    invalid_products = (
        ~inventory["product_id"].isin(
            products["product_id"]
        )
    ).sum()

    assert invalid_products == 0, (
        f"{invalid_products} inventory rows "
        "reference unknown products"
    )

    invalid_warehouses = (
        ~inventory["warehouse_id"].isin(
            warehouses["warehouse_id"]
        )
    ).sum()

    assert invalid_warehouses == 0, (
        f"{invalid_warehouses} inventory rows "
        "reference unknown warehouses"
    )

    assert (
        inventory["on_hand_qty"] >= 0
    ).all(), (
        "Negative inventory quantity detected"
    )

    assert (
        inventory["reserved_qty"] >= 0
    ).all(), (
        "Negative reserved inventory detected"
    )

    assert (
        inventory["reorder_point"] >= 0
    ).all(), (
        "Negative reorder point detected"
    )

    assert (
        inventory["reserved_qty"]
        <= inventory["on_hand_qty"]
    ).all(), (
        "reserved_qty exceeds on_hand_qty"
    )

    low_stock = inventory[
        inventory["on_hand_qty"]
        <= inventory["reorder_point"]
    ]

    return {
        "inventory_positions": len(inventory),
        "products_represented":
            inventory["product_id"].nunique(),
        "warehouses_represented":
            inventory["warehouse_id"].nunique(),
        "low_stock_positions": len(low_stock),
        "low_stock_rate":
            len(low_stock) / len(inventory) * 100,
    }


# ============================================================
# Orders
# ============================================================

def validate_orders(
    orders: pd.DataFrame,
    customers: pd.DataFrame,
    warehouses: pd.DataFrame,
    config: dict,
) -> None:

    required = {
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
    }

    assert required.issubset(orders.columns), (
        "orders.csv missing columns: "
        f"{required - set(orders.columns)}"
    )

    assert_unique(
        orders,
        "order_id",
        "orders",
    )

    assert_unique(
        orders,
        "order_external_id",
        "orders",
    )

    expected = config["scale"]["target_orders"]

    assert len(orders) == expected, (
        f"Expected {expected:,} orders, "
        f"found {len(orders):,}"
    )

    unknown_customers = (
        ~orders["customer_id"].isin(
            customers["customer_id"]
        )
    ).sum()

    assert unknown_customers == 0, (
        f"{unknown_customers} orders reference "
        "unknown customers"
    )

    unknown_warehouses = (
        ~orders["warehouse_id"].isin(
            warehouses["warehouse_id"]
        )
    ).sum()

    assert unknown_warehouses == 0, (
        f"{unknown_warehouses} orders reference "
        "unknown warehouses"
    )

    allowed_statuses = {
        "created",
        "payment_confirmed",
        "processing",
        "packed",
        "shipped",
        "delivered",
        "cancelled",
    }

    invalid_statuses = set(
        orders["order_status"].dropna()
    ) - allowed_statuses

    assert not invalid_statuses, (
        f"Invalid order statuses: {invalid_statuses}"
    )

    shipping_methods = set(
        config["shipping"]["methods"].keys()
    )

    invalid_shipping = set(
        orders["shipping_method"].dropna()
    ) - shipping_methods

    assert not invalid_shipping, (
        f"Invalid shipping methods: {invalid_shipping}"
    )

    assert (orders["total_amount"] >= 0).all(), (
        "Negative order totals detected"
    )

    assert (
        orders["promised_delivery_ts"]
        >= orders["order_ts"]
    ).all(), (
        "Orders found with promised delivery "
        "before order timestamp"
    )


# ============================================================
# Order Items
# ============================================================

def validate_order_items(
    order_items: pd.DataFrame,
    orders: pd.DataFrame,
    products: pd.DataFrame,
    inventory: pd.DataFrame,
) -> dict:

    required = {
        "order_item_id",
        "order_id",
        "product_id",
        "quantity",
        "unit_price",
    }

    assert required.issubset(order_items.columns), (
        "order_items.csv missing columns: "
        f"{required - set(order_items.columns)}"
    )

    assert_unique(
        order_items,
        "order_item_id",
        "order_items",
    )

    duplicate_products = order_items.duplicated(
        ["order_id", "product_id"]
    ).sum()

    assert duplicate_products == 0, (
        f"{duplicate_products} duplicate products "
        "within orders"
    )

    unknown_orders = (
        ~order_items["order_id"].isin(
            orders["order_id"]
        )
    ).sum()

    assert unknown_orders == 0, (
        f"{unknown_orders} order items reference "
        "unknown orders"
    )

    unknown_products = (
        ~order_items["product_id"].isin(
            products["product_id"]
        )
    ).sum()

    assert unknown_products == 0, (
        f"{unknown_products} order items reference "
        "unknown products"
    )

    assert (order_items["quantity"] > 0).all(), (
        "Non-positive order quantities detected"
    )

    assert (order_items["unit_price"] >= 0).all(), (
        "Negative order-item price detected"
    )

    orders_without_items = (
        ~orders["order_id"].isin(
            order_items["order_id"]
        )
    ).sum()

    assert orders_without_items == 0, (
        f"{orders_without_items} orders have no items"
    )

    # --------------------------------------------------------
    # Ensure each ordered product exists in assigned warehouse
    # --------------------------------------------------------

    order_locations = orders[
        ["order_id", "warehouse_id"]
    ]

    item_locations = order_items.merge(
        order_locations,
        on="order_id",
        how="left",
    )

    inventory_pairs = set(
        zip(
            inventory["warehouse_id"],
            inventory["product_id"],
        )
    )

    invalid_pairs = sum(
        (
            warehouse_id,
            product_id,
        )
        not in inventory_pairs
        for warehouse_id, product_id
        in zip(
            item_locations["warehouse_id"],
            item_locations["product_id"],
        )
    )

    assert invalid_pairs == 0, (
        f"{invalid_pairs} order items are not stocked "
        "at their assigned warehouse"
    )

    # --------------------------------------------------------
    # Order totals
    # --------------------------------------------------------

    calculated = (
        order_items.assign(
            subtotal=(
                order_items["quantity"]
                * order_items["unit_price"]
            )
        )
        .groupby("order_id")["subtotal"]
        .sum()
        .round(2)
    )

    reported = (
        orders
        .set_index("order_id")["total_amount"]
        .round(2)
    )

    difference = (
        reported.loc[calculated.index]
        - calculated
    ).abs()

    incorrect_totals = (
        difference > 0.01
    ).sum()

    assert incorrect_totals == 0, (
        f"{incorrect_totals} incorrect order totals"
    )

    cancellation_rate = (
        orders["order_status"]
        .eq("cancelled")
        .mean()
        * 100
    )

    average_items = (
        len(order_items) / len(orders)
    )

    return {
        "orders": len(orders),
        "order_items": len(order_items),
        "average_items": average_items,
        "cancellation_rate": cancellation_rate,
    }


# ============================================================
# Transactional Behavior
# ============================================================

def validate_transactional_behavior(
    orders: pd.DataFrame,
    config: dict,
) -> dict:

    shipping_distribution = (
        orders["shipping_method"]
        .value_counts(normalize=True)
        .mul(100)
    )

    configured_shipping = (
        config["shipping"]["methods"]
    )

    for method, expected_rate in configured_shipping.items():

        actual_rate = (
            orders["shipping_method"]
            .eq(method)
            .mean()
        )

        assert abs(
            actual_rate - expected_rate
        ) < 0.02, (
            f"{method} shipping distribution "
            f"{actual_rate:.4f} differs too much "
            f"from configured {expected_rate:.4f}"
        )

    expected_cancel = config[
        "orders"
    ]["cancellation_rate"]

    actual_cancel = (
        orders["order_status"]
        .eq("cancelled")
        .mean()
    )

    assert abs(
        actual_cancel - expected_cancel
    ) < 0.015, (
        "Cancellation rate differs too much "
        "from configured rate"
    )

    return {
        "shipping_distribution":
            shipping_distribution,
    }


# ============================================================
# Shipments
# ============================================================

def validate_shipments(
    shipments: pd.DataFrame,
    orders: pd.DataFrame,
    config: dict,
) -> dict:

    required = {
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
    }

    assert required.issubset(shipments.columns), (
        "shipments.csv missing columns: "
        f"{required - set(shipments.columns)}"
    )

    assert_no_missing(
        shipments,
        [
            "shipment_id",
            "shipment_external_id",
            "order_id",
            "warehouse_id",
            "carrier",
            "shipment_status",
            "shipped_at",
            "expected_delivery_at",
            "shipping_cost",
            "created_at",
        ],
        "shipments",
    )

    # --------------------------------------------------------
    # Counts
    # --------------------------------------------------------

    non_cancelled = orders[
        orders["order_status"] != "cancelled"
    ]

    assert len(shipments) == len(non_cancelled), (
        "Shipment count does not equal "
        "non-cancelled order count"
    )

    # --------------------------------------------------------
    # IDs
    # --------------------------------------------------------

    assert_unique(
        shipments,
        "shipment_id",
        "shipments",
    )

    assert_unique(
        shipments,
        "shipment_external_id",
        "shipments",
    )

    assert_unique(
        shipments,
        "order_id",
        "shipments",
    )

    # --------------------------------------------------------
    # Order references
    # --------------------------------------------------------

    unknown_orders = (
        ~shipments["order_id"].isin(
            orders["order_id"]
        )
    ).sum()

    assert unknown_orders == 0, (
        f"{unknown_orders} shipments reference "
        "unknown orders"
    )

    cancelled_ids = set(
        orders.loc[
            orders["order_status"] == "cancelled",
            "order_id",
        ]
    )

    cancelled_shipments = (
        shipments["order_id"]
        .isin(cancelled_ids)
        .sum()
    )

    assert cancelled_shipments == 0, (
        f"{cancelled_shipments} cancelled orders "
        "have shipments"
    )

    # --------------------------------------------------------
    # Warehouse consistency
    # --------------------------------------------------------

    warehouse_check = shipments.merge(
        orders[
            ["order_id", "warehouse_id"]
        ].rename(
            columns={
                "warehouse_id":
                    "order_warehouse_id"
            }
        ),
        on="order_id",
        how="left",
    )

    warehouse_mismatch = (
        warehouse_check["warehouse_id"]
        != warehouse_check[
            "order_warehouse_id"
        ]
    ).sum()

    assert warehouse_mismatch == 0, (
        f"{warehouse_mismatch} shipment warehouse "
        "mismatches detected"
    )

    # --------------------------------------------------------
    # Status integrity
    # --------------------------------------------------------

    allowed_statuses = {
        "delivered",
        "exception",
    }

    invalid_statuses = set(
        shipments["shipment_status"].dropna()
    ) - allowed_statuses

    assert not invalid_statuses, (
        f"Unexpected shipment statuses: "
        f"{invalid_statuses}"
    )

    delivered = shipments[
        shipments["shipment_status"]
        == "delivered"
    ]

    exceptions = shipments[
        shipments["shipment_status"]
        == "exception"
    ]

    assert (
        delivered["delivered_at"]
        .notna()
        .all()
    ), (
        "Delivered shipments missing delivered_at"
    )

    assert (
        exceptions["delivered_at"]
        .isna()
        .all()
    ), (
        "Exception shipments unexpectedly "
        "have delivered_at"
    )

    # --------------------------------------------------------
    # Temporal consistency
    # --------------------------------------------------------

    order_times = orders[
        ["order_id", "order_ts"]
    ]

    shipment_times = shipments.merge(
        order_times,
        on="order_id",
        how="left",
    )

    before_order = (
        shipment_times["shipped_at"]
        < shipment_times["order_ts"]
    ).sum()

    assert before_order == 0, (
        f"{before_order} shipments occur "
        "before their order"
    )

    delivered_before_ship = (
        delivered["delivered_at"]
        < delivered["shipped_at"]
    ).sum()

    assert delivered_before_ship == 0, (
        f"{delivered_before_ship} deliveries "
        "occur before shipment"
    )

    # --------------------------------------------------------
    # Monetary integrity
    # --------------------------------------------------------

    assert (
        shipments["shipping_cost"] >= 0
    ).all(), (
        "Negative shipping costs detected"
    )

    # --------------------------------------------------------
    # Behavior
    # --------------------------------------------------------

    exception_rate = (
        len(exceptions)
        / len(shipments)
    )

    expected_exception = config[
        "fulfillment"
    ]["delivery_exception_rate"]

    assert abs(
        exception_rate - expected_exception
    ) < 0.015, (
        "Shipment exception rate differs too much "
        "from configured value"
    )

    late = delivered[
        delivered["delivered_at"]
        > delivered["expected_delivery_at"]
    ]

    late_rate = (
        len(late) / len(delivered)
    )

    expected_late = config[
        "fulfillment"
    ]["late_delivery_rate"]

    assert abs(
        late_rate - expected_late
    ) < 0.02, (
        "Late delivery rate differs too much "
        "from configured value"
    )

    # --------------------------------------------------------
    # Carrier distribution
    # --------------------------------------------------------

    carrier_distribution = (
        shipments["carrier"]
        .value_counts(normalize=True)
    )

    configured_carriers = config[
        "fulfillment"
    ]["carriers"]

    for carrier, expected_rate in (
        configured_carriers.items()
    ):

        actual_rate = carrier_distribution.get(
            carrier,
            0.0,
        )

        assert abs(
            actual_rate - expected_rate
        ) < 0.02, (
            f"{carrier} carrier distribution "
            f"{actual_rate:.4f} differs too much "
            f"from configured {expected_rate:.4f}"
        )

    return {
        "shipments": len(shipments),
        "delivered": len(delivered),
        "exceptions": len(exceptions),
        "exception_rate":
            exception_rate * 100,
        "late_rate":
            late_rate * 100,
        "carrier_distribution":
            carrier_distribution * 100,
    }



# ============================================================
# Inventory Movements
# ============================================================

def validate_inventory_movements(
    inventory_movements: pd.DataFrame,
    inventory: pd.DataFrame,
    orders: pd.DataFrame,
    order_items: pd.DataFrame,
    warehouses: pd.DataFrame,
    products: pd.DataFrame,
    order_events: pd.DataFrame,
    config: dict,
) -> dict:

    required = {
        "movement_id",
        "warehouse_id",
        "product_id",
        "order_id",
        "movement_type",
        "quantity_change",
        "event_ts",
        "created_at",
    }

    assert required.issubset(
        inventory_movements.columns
    ), (
        "inventory_movements.csv missing columns: "
        f"{required - set(inventory_movements.columns)}"
    )

    assert_no_missing(
        inventory_movements,
        [
            "movement_id",
            "warehouse_id",
            "product_id",
            "movement_type",
            "quantity_change",
            "event_ts",
            "created_at",
        ],
        "inventory_movements",
    )

    assert_unique(
        inventory_movements,
        "movement_id",
        "inventory_movements",
    )

    allowed_types = {
        "receipt",
        "reservation",
        "release",
        "shipment",
        "adjustment",
        "return",
    }

    invalid_types = set(
        inventory_movements[
            "movement_type"
        ].dropna()
    ) - allowed_types

    assert not invalid_types, (
        "Invalid inventory movement types: "
        f"{invalid_types}"
    )

    assert (
        inventory_movements[
            "quantity_change"
        ] != 0
    ).all(), (
        "Zero-quantity inventory movements detected"
    )

    positive_types = {
        "receipt",
        "release",
        "return",
    }

    negative_types = {
        "reservation",
        "shipment",
    }

    for movement_type in positive_types:
        rows = inventory_movements[
            inventory_movements[
                "movement_type"
            ] == movement_type
        ]

        assert (
            rows[
                "quantity_change"
            ] > 0
        ).all(), (
            f"{movement_type} movements must be positive"
        )

    for movement_type in negative_types:
        rows = inventory_movements[
            inventory_movements[
                "movement_type"
            ] == movement_type
        ]

        assert (
            rows[
                "quantity_change"
            ] < 0
        ).all(), (
            f"{movement_type} movements must be negative"
        )

    unknown_warehouses = (
        ~inventory_movements[
            "warehouse_id"
        ].isin(
            warehouses[
                "warehouse_id"
            ]
        )
    ).sum()

    assert unknown_warehouses == 0, (
        f"{unknown_warehouses} inventory movements "
        "reference unknown warehouses"
    )

    unknown_products = (
        ~inventory_movements[
            "product_id"
        ].isin(
            products[
                "product_id"
            ]
        )
    ).sum()

    assert unknown_products == 0, (
        f"{unknown_products} inventory movements "
        "reference unknown products"
    )

    order_linked = (
        inventory_movements[
            "order_id"
        ].dropna()
    )

    unknown_orders = (
        ~order_linked.isin(
            orders[
                "order_id"
            ]
        )
    ).sum()

    assert unknown_orders == 0, (
        f"{unknown_orders} inventory movements "
        "reference unknown orders"
    )

    receipt_orders = (
        inventory_movements.loc[
            inventory_movements[
                "movement_type"
            ] == "receipt",
            "order_id",
        ]
    )

    assert (
        receipt_orders.isna().all()
    ), (
        "Receipt movements should not be tied "
        "directly to customer orders"
    )

    transactional_movements = (
        inventory_movements[
            inventory_movements[
                "movement_type"
            ].isin(
                {
                    "reservation",
                    "release",
                    "shipment",
                }
            )
        ]
    )

    assert (
        transactional_movements[
            "order_id"
        ].notna().all()
    ), (
        "Reservation/release/shipment movements "
        "must reference an order"
    )

    # --------------------------------------------------------
    # Opening inventory reconciliation
    # --------------------------------------------------------

    simulation_start = pd.Timestamp(
        config[
            "simulation"
        ][
            "start_date"
        ],
        tz="UTC",
    )

    opening_receipts = (
        inventory_movements[
            (
                inventory_movements[
                    "movement_type"
                ] == "receipt"
            )
            & (
                inventory_movements[
                    "event_ts"
                ] == simulation_start
            )
        ]
    )

    opening = (
        opening_receipts
        .groupby(
            [
                "warehouse_id",
                "product_id",
            ],
            as_index=False,
        )[
            "quantity_change"
        ]
        .sum()
        .rename(
            columns={
                "quantity_change":
                    "opening_quantity"
            }
        )
    )

    expected_opening = (
        inventory[
            [
                "warehouse_id",
                "product_id",
                "on_hand_qty",
            ]
        ]
        .rename(
            columns={
                "on_hand_qty":
                    "expected_opening"
            }
        )
    )

    opening_check = (
        expected_opening.merge(
            opening,
            on=[
                "warehouse_id",
                "product_id",
            ],
            how="left",
        )
        .fillna(
            {
                "opening_quantity": 0
            }
        )
    )

    opening_mismatches = (
        opening_check[
            "opening_quantity"
        ]
        != opening_check[
            "expected_opening"
        ]
    ).sum()

    assert opening_mismatches == 0, (
        f"{opening_mismatches} opening inventory "
        "receipt mismatches detected"
    )

    # --------------------------------------------------------
    # Order-line reconciliation
    # --------------------------------------------------------

    reserved_order_ids = set(
        order_events.loc[
            order_events[
                "event_type"
            ] == "inventory_reserved",
            "order_id",
        ].astype(int)
    )

    released_order_ids = set(
        order_events.loc[
            order_events[
                "event_type"
            ] == "inventory_released",
            "order_id",
        ].astype(int)
    )

    shipped_order_ids = set(
        order_events.loc[
            order_events[
                "event_type"
            ] == "order_shipped",
            "order_id",
        ].astype(int)
    )

    def movement_totals(
        movement_type: str,
    ) -> pd.DataFrame:
        rows = inventory_movements[
            inventory_movements[
                "movement_type"
            ] == movement_type
        ].copy()

        if rows.empty:
            return pd.DataFrame(
                columns=[
                    "order_id",
                    "product_id",
                    "movement_units",
                ]
            )

        rows[
            "movement_units"
        ] = rows[
            "quantity_change"
        ].abs()

        return (
            rows.groupby(
                [
                    "order_id",
                    "product_id",
                ],
                as_index=False,
            )[
                "movement_units"
            ]
            .sum()
        )

    def expected_item_totals(
        order_ids: set[int],
    ) -> pd.DataFrame:
        rows = order_items[
            order_items[
                "order_id"
            ].isin(
                order_ids
            )
        ]

        return (
            rows.groupby(
                [
                    "order_id",
                    "product_id",
                ],
                as_index=False,
            )[
                "quantity"
            ]
            .sum()
            .rename(
                columns={
                    "quantity":
                        "expected_units"
                }
            )
        )

    for (
        movement_type,
        relevant_order_ids,
    ) in [
        (
            "reservation",
            reserved_order_ids,
        ),
        (
            "release",
            released_order_ids,
        ),
        (
            "shipment",
            shipped_order_ids,
        ),
    ]:
        actual = movement_totals(
            movement_type
        )

        expected = expected_item_totals(
            relevant_order_ids
        )

        comparison = (
            expected.merge(
                actual,
                on=[
                    "order_id",
                    "product_id",
                ],
                how="outer",
            )
            .fillna(0)
        )

        mismatches = (
            comparison[
                "expected_units"
            ]
            != comparison[
                "movement_units"
            ]
        ).sum()

        assert mismatches == 0, (
            f"{mismatches} {movement_type} movement "
            "quantities do not match order items"
        )

    # --------------------------------------------------------
    # Chronological inventory-state integrity
    # --------------------------------------------------------

    state: dict[
        tuple[int, int],
        dict[str, int],
    ] = {}

    sorted_movements = (
        inventory_movements.sort_values(
            by=[
                "event_ts",
                "movement_id",
            ]
        )
    )

    for movement in (
        sorted_movements.itertuples(
            index=False
        )
    ):
        key = (
            int(
                movement.warehouse_id
            ),
            int(
                movement.product_id
            ),
        )

        current = state.setdefault(
            key,
            {
                "on_hand": 0,
                "reserved": 0,
            },
        )

        quantity = int(
            movement.quantity_change
        )

        movement_type = str(
            movement.movement_type
        )

        if movement_type in {
            "receipt",
            "return",
        }:
            current[
                "on_hand"
            ] += quantity

        elif movement_type == "adjustment":
            current[
                "on_hand"
            ] += quantity

        elif movement_type == "reservation":
            units = abs(quantity)

            available = (
                current["on_hand"]
                - current["reserved"]
            )

            assert available >= units, (
                "Reservation exceeds available stock "
                f"for warehouse/product {key}"
            )

            current[
                "reserved"
            ] += units

        elif movement_type == "release":
            units = quantity

            assert (
                current["reserved"]
                >= units
            ), (
                "Release exceeds reserved stock "
                f"for warehouse/product {key}"
            )

            current[
                "reserved"
            ] -= units

        elif movement_type == "shipment":
            units = abs(quantity)

            assert (
                current["on_hand"]
                >= units
            ), (
                "Shipment drives physical inventory "
                f"negative for warehouse/product {key}"
            )

            assert (
                current["reserved"]
                >= units
            ), (
                "Shipment exceeds reserved stock "
                f"for warehouse/product {key}"
            )

            current[
                "on_hand"
            ] -= units

            current[
                "reserved"
            ] -= units

        assert (
            current["on_hand"] >= 0
        ), (
            "Negative physical stock detected "
            f"for warehouse/product {key}"
        )

        assert (
            current["reserved"] >= 0
        ), (
            "Negative reserved stock detected "
            f"for warehouse/product {key}"
        )

    open_reservations = sum(
        values[
            "reserved"
        ]
        for values in state.values()
    )

    assert open_reservations == 0, (
        f"{open_reservations} units remain reserved "
        "after the simulated lifecycle completes"
    )

    return {
        "movements":
            len(inventory_movements),
        "opening_receipts":
            len(opening_receipts),
        "replenishment_receipts":
            (
                (
                    inventory_movements[
                        "movement_type"
                    ]
                    == "receipt"
                ).sum()
                - len(opening_receipts)
            ),
        "reservations":
            (
                inventory_movements[
                    "movement_type"
                ]
                == "reservation"
            ).sum(),
        "releases":
            (
                inventory_movements[
                    "movement_type"
                ]
                == "release"
            ).sum(),
        "shipment_movements":
            (
                inventory_movements[
                    "movement_type"
                ]
                == "shipment"
            ).sum(),
    }


# ============================================================
# Order Events
# ============================================================

def validate_order_events(
    order_events: pd.DataFrame,
    orders: pd.DataFrame,
    shipments: pd.DataFrame,
    warehouses: pd.DataFrame,
    config: dict,
) -> dict:

    required = {
        "event_id",
        "event_key",
        "order_id",
        "warehouse_id",
        "event_type",
        "event_ts",
        "source",
        "payload",
        "ingested_at",
    }

    assert required.issubset(
        order_events.columns
    ), (
        "order_events.csv missing columns: "
        f"{required - set(order_events.columns)}"
    )

    assert_no_missing(
        order_events,
        [
            "event_id",
            "event_key",
            "order_id",
            "warehouse_id",
            "event_type",
            "event_ts",
            "source",
            "payload",
            "ingested_at",
        ],
        "order_events",
    )

    assert_unique(
        order_events,
        "event_id",
        "order_events",
    )

    assert_unique(
        order_events,
        "event_key",
        "order_events",
    )

    unknown_orders = (
        ~order_events[
            "order_id"
        ].isin(
            orders[
                "order_id"
            ]
        )
    ).sum()

    assert unknown_orders == 0, (
        f"{unknown_orders} order events reference "
        "unknown orders"
    )

    unknown_warehouses = (
        ~order_events[
            "warehouse_id"
        ].isin(
            warehouses[
                "warehouse_id"
            ]
        )
    ).sum()

    assert unknown_warehouses == 0, (
        f"{unknown_warehouses} order events reference "
        "unknown warehouses"
    )

    allowed_types = {
        "order_created",
        "payment_confirmed",
        "inventory_reserved",
        "processing_started",
        "order_packed",
        "shipment_created",
        "order_shipped",
        "order_delivered",
        "delivery_exception",
        "order_cancelled",
        "inventory_released",
    }

    invalid_types = set(
        order_events[
            "event_type"
        ].dropna()
    ) - allowed_types

    assert not invalid_types, (
        "Unexpected order event types: "
        f"{invalid_types}"
    )

    expected_source = str(
        config.get(
            "lifecycle",
            {},
        ).get(
            "event_source",
            "synthetic_generator",
        )
    )

    invalid_sources = (
        order_events[
            "source"
        ]
        != expected_source
    ).sum()

    assert invalid_sources == 0, (
        f"{invalid_sources} order events have "
        "an unexpected source"
    )

    invalid_payloads = 0

    for payload in order_events[
        "payload"
    ]:
        try:
            parsed = json.loads(
                payload
            )
        except (
            TypeError,
            json.JSONDecodeError,
        ):
            invalid_payloads += 1
            continue

        if not isinstance(
            parsed,
            dict,
        ):
            invalid_payloads += 1

    assert invalid_payloads == 0, (
        f"{invalid_payloads} order events contain "
        "invalid JSON-object payloads"
    )

    created_events = order_events[
        order_events[
            "event_type"
        ] == "order_created"
    ]

    created_counts = (
        created_events[
            "order_id"
        ]
        .value_counts()
    )

    assert (
        created_counts.eq(1).all()
        and len(created_counts)
        == len(orders)
    ), (
        "Every order must have exactly one "
        "order_created event"
    )

    created_check = (
        created_events[
            [
                "order_id",
                "event_ts",
            ]
        ]
        .merge(
            orders[
                [
                    "order_id",
                    "order_ts",
                ]
            ],
            on="order_id",
            how="left",
        )
    )

    assert (
        created_check[
            "event_ts"
        ]
        == created_check[
            "order_ts"
        ]
    ).all(), (
        "order_created timestamps do not match order_ts"
    )

    # --------------------------------------------------------
    # Per-order lifecycle path
    # --------------------------------------------------------

    events_by_order = {
        int(order_id): group.sort_values(
            by=[
                "event_ts",
                "event_id",
            ]
        )
        for order_id, group
        in order_events.groupby(
            "order_id",
            sort=False,
        )
    }

    shipment_by_order = {
        int(row.order_id): row
        for row in shipments.itertuples(
            index=False
        )
    }

    cancelled = 0
    delivered = 0
    exceptions = 0
    post_reservation_cancellations = 0

    required_non_cancelled = {
        "order_created",
        "payment_confirmed",
        "inventory_reserved",
        "processing_started",
        "order_packed",
        "shipment_created",
        "order_shipped",
    }

    for order in orders.itertuples(
        index=False
    ):
        order_id = int(
            order.order_id
        )

        group = events_by_order.get(
            order_id
        )

        assert group is not None, (
            f"Order {order_id} has no events"
        )

        assert (
            group[
                "event_ts"
            ]
            .is_monotonic_increasing
        ), (
            f"Order {order_id} event timestamps "
            "are not chronological"
        )

        event_types = set(
            group[
                "event_type"
            ]
        )

        status = str(
            order.order_status
        )

        if status == "cancelled":
            cancelled += 1

            assert (
                "order_cancelled"
                in event_types
            ), (
                f"Cancelled order {order_id} lacks "
                "order_cancelled event"
            )

            forbidden = {
                "shipment_created",
                "order_shipped",
                "order_delivered",
                "delivery_exception",
            }

            assert not (
                event_types
                & forbidden
            ), (
                f"Cancelled order {order_id} contains "
                "shipment/delivery events"
            )

            cancel_row = group[
                group[
                    "event_type"
                ] == "order_cancelled"
            ]

            assert len(cancel_row) == 1, (
                f"Cancelled order {order_id} has "
                "multiple cancellation events"
            )

            payload = json.loads(
                cancel_row.iloc[0][
                    "payload"
                ]
            )

            stage = payload.get(
                "stage"
            )

            assert stage in {
                "pre_payment",
                "post_payment",
                "post_reservation",
            }, (
                f"Cancelled order {order_id} has "
                f"invalid cancellation stage {stage!r}"
            )

            if stage == "pre_payment":
                assert (
                    "payment_confirmed"
                    not in event_types
                ), (
                    f"Pre-payment cancellation {order_id} "
                    "contains payment confirmation"
                )

                assert (
                    "inventory_reserved"
                    not in event_types
                ), (
                    f"Pre-payment cancellation {order_id} "
                    "contains inventory reservation"
                )

            elif stage == "post_payment":
                assert (
                    "payment_confirmed"
                    in event_types
                ), (
                    f"Post-payment cancellation {order_id} "
                    "lacks payment confirmation"
                )

                assert (
                    "inventory_reserved"
                    not in event_types
                ), (
                    f"Post-payment cancellation {order_id} "
                    "contains inventory reservation"
                )

            else:
                post_reservation_cancellations += 1

                assert {
                    "payment_confirmed",
                    "inventory_reserved",
                    "inventory_released",
                }.issubset(
                    event_types
                ), (
                    f"Post-reservation cancellation "
                    f"{order_id} lacks required events"
                )

            continue

        assert required_non_cancelled.issubset(
            event_types
        ), (
            f"Non-cancelled order {order_id} lacks "
            "required lifecycle events"
        )

        assert (
            "order_cancelled"
            not in event_types
        ), (
            f"Non-cancelled order {order_id} contains "
            "order_cancelled"
        )

        shipment = shipment_by_order.get(
            order_id
        )

        assert shipment is not None, (
            f"Non-cancelled order {order_id} lacks shipment"
        )

        if status == "delivered":
            delivered += 1

            assert (
                "order_delivered"
                in event_types
            ), (
                f"Delivered order {order_id} lacks "
                "order_delivered event"
            )

            assert (
                "delivery_exception"
                not in event_types
            ), (
                f"Delivered order {order_id} contains "
                "delivery_exception"
            )

        elif status == "shipped":
            exceptions += 1

            assert (
                str(
                    shipment.shipment_status
                )
                == "exception"
            ), (
                f"Shipped order {order_id} is not linked "
                "to an exception shipment"
            )

            assert (
                "delivery_exception"
                in event_types
            ), (
                f"Exception order {order_id} lacks "
                "delivery_exception event"
            )

            assert (
                "order_delivered"
                not in event_types
            ), (
                f"Exception order {order_id} contains "
                "order_delivered"
            )

        else:
            raise AssertionError(
                "Unexpected final order status in "
                f"lifecycle validation: {status!r}"
            )

    return {
        "events": len(order_events),
        "cancelled_orders": cancelled,
        "delivered_orders": delivered,
        "exception_orders": exceptions,
        "post_reservation_cancellations":
            post_reservation_cancellations,
    }


# ============================================================
# Main Validation Pipeline
# ============================================================

def main() -> None:

    print(
        "Validating FulfillAI synthetic data..."
    )
    print()

    config = load_config()

    # --------------------------------------------------------
    # Load datasets
    # --------------------------------------------------------

    categories = load_csv(
        "product_categories"
    )

    products = load_csv(
        "products",
        parse_dates=["created_at"],
    )

    warehouses = load_csv(
        "warehouses",
        parse_dates=["created_at"],
    )

    customers = load_csv(
        "customers",
        parse_dates=["created_at"],
    )

    inventory = load_csv(
        "inventory",
        parse_dates=["updated_at"],
    )

    orders = load_csv(
        "orders",
        parse_dates=[
            "order_ts",
            "promised_delivery_ts",
            "created_at",
        ],
    )

    order_items = load_csv(
        "order_items"
    )

    shipments = load_csv(
        "shipments",
        parse_dates=[
            "shipped_at",
            "expected_delivery_at",
            "delivered_at",
            "created_at",
        ],
    )

    inventory_movements = load_csv(
        "inventory_movements",
        parse_dates=[
            "event_ts",
            "created_at",
        ],
    )

    order_events = load_csv(
        "order_events",
        parse_dates=[
            "event_ts",
            "ingested_at",
        ],
    )

    # --------------------------------------------------------
    # Validate
    # --------------------------------------------------------

    validate_product_categories(
        categories,
        config,
    )
    print("✓ product_categories")

    validate_products(
        products,
        categories,
        config,
    )
    print("✓ products")

    validate_warehouses(
        warehouses,
        config,
    )
    print("✓ warehouses")

    validate_customers(
        customers,
        config,
    )
    print("✓ customers")

    inventory_summary = validate_inventory(
        inventory,
        products,
        warehouses,
    )
    print("✓ inventory")

    validate_orders(
        orders,
        customers,
        warehouses,
        config,
    )
    print("✓ orders")

    transactional_summary = (
        validate_order_items(
            order_items,
            orders,
            products,
            inventory,
        )
    )
    print("✓ order_items")

    behavior_summary = (
        validate_transactional_behavior(
            orders,
            config,
        )
    )
    print("✓ transactional behavior")

    shipment_summary = (
        validate_shipments(
            shipments,
            orders,
            config,
        )
    )
    print("✓ shipments")

    event_summary = (
        validate_order_events(
            order_events,
            orders,
            shipments,
            warehouses,
            config,
        )
    )
    print("✓ order_events")

    movement_summary = (
        validate_inventory_movements(
            inventory_movements,
            inventory,
            orders,
            order_items,
            warehouses,
            products,
            order_events,
            config,
        )
    )
    print("✓ inventory_movements")

    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    print()
    print("Validation summary:")

    print(
        "  inventory positions : "
        f"{inventory_summary['inventory_positions']:,}"
    )

    print(
        "  products represented : "
        f"{inventory_summary['products_represented']:,}"
    )

    print(
        "  warehouses represented: "
        f"{inventory_summary['warehouses_represented']:,}"
    )

    print(
        "  low-stock positions  : "
        f"{inventory_summary['low_stock_positions']:,}"
    )

    print(
        "  low-stock rate       : "
        f"{inventory_summary['low_stock_rate']:.2f}%"
    )

    print(
        "  orders               : "
        f"{transactional_summary['orders']:,}"
    )

    print(
        "  order items          : "
        f"{transactional_summary['order_items']:,}"
    )

    print(
        "  avg items/order      : "
        f"{transactional_summary['average_items']:.2f}"
    )

    print(
        "  cancellation rate    : "
        f"{transactional_summary['cancellation_rate']:.2f}%"
    )

    print(
        "  shipments            : "
        f"{shipment_summary['shipments']:,}"
    )

    print(
        "  delivered            : "
        f"{shipment_summary['delivered']:,}"
    )

    print(
        "  exceptions           : "
        f"{shipment_summary['exceptions']:,}"
    )

    print(
        "  exception rate       : "
        f"{shipment_summary['exception_rate']:.2f}%"
    )

    print(
        "  late-delivery rate   : "
        f"{shipment_summary['late_rate']:.2f}%"
    )

    print(
        "  inventory movements  : "
        f"{movement_summary['movements']:,}"
    )

    print(
        "  replenishment receipts: "
        f"{movement_summary['replenishment_receipts']:,}"
    )

    print(
        "  order events         : "
        f"{event_summary['events']:,}"
    )

    print(
        "  post-reservation cancels: "
        f"{event_summary['post_reservation_cancellations']:,}"
    )

    print()
    print("Shipping distribution:")

    for method, value in (
        behavior_summary[
            "shipping_distribution"
        ].items()
    ):
        print(
            f"  {method:<10}: {value:.2f}%"
        )

    print()
    print("Carrier distribution:")

    for carrier, value in (
        shipment_summary[
            "carrier_distribution"
        ].items()
    ):
        print(
            f"  {carrier:<10}: {value:.2f}%"
        )

    print()
    print(
        "All ten-dataset validation "
        "checks passed."
    )


if __name__ == "__main__":
    main()