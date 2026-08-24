from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml
from faker import Faker


# ---------------------------------------------------------------------------
# Project paths
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = PROJECT_ROOT / "configs" / "data_generation.yaml"
OUTPUT_DIR = PROJECT_ROOT / "data" / "raw" / "synthetic"


# ---------------------------------------------------------------------------
# Static reference data
# ---------------------------------------------------------------------------

CATEGORY_NAMES = [
    "Electronics",
    "Home & Kitchen",
    "Beauty & Personal Care",
    "Sports & Outdoors",
    "Books",
    "Clothing",
    "Shoes",
    "Office Supplies",
    "Toys & Games",
    "Pet Supplies",
    "Automotive",
    "Grocery",
]


REGIONS = {
    "US": [
        "California",
        "Texas",
        "Illinois",
        "New York",
        "Florida",
        "Washington",
        "Massachusetts",
        "Colorado",
    ],
    "DE": [
        "Berlin",
        "Bavaria",
        "Hesse",
        "Hamburg",
        "North Rhine-Westphalia",
        "Baden-Wurttemberg",
    ],
    "GB": [
        "London",
        "North West",
        "West Midlands",
        "Yorkshire",
        "South East",
        "Scotland",
    ],
    "CA": [
        "Ontario",
        "Quebec",
        "British Columbia",
        "Alberta",
        "Manitoba",
    ],
}


WAREHOUSE_LOCATIONS = [
    {
        "warehouse_code": "WH-US-CHI",
        "warehouse_name": "Chicago Fulfillment Center",
        "city": "Chicago",
        "country_code": "US",
    },
    {
        "warehouse_code": "WH-US-DAL",
        "warehouse_name": "Dallas Fulfillment Center",
        "city": "Dallas",
        "country_code": "US",
    },
    {
        "warehouse_code": "WH-DE-BER",
        "warehouse_name": "Berlin Fulfillment Center",
        "city": "Berlin",
        "country_code": "DE",
    },
    {
        "warehouse_code": "WH-GB-LON",
        "warehouse_name": "London Fulfillment Center",
        "city": "London",
        "country_code": "GB",
    },
    {
        "warehouse_code": "WH-CA-TOR",
        "warehouse_name": "Toronto Fulfillment Center",
        "city": "Toronto",
        "country_code": "CA",
    },
]


# Demand-spike dates inside the current simulation window.
HOLIDAY_DATES = {
    "2025-11-28",  # Black Friday
    "2025-12-01",  # Cyber Monday
    "2025-12-24",
    "2025-12-25",
    "2025-12-26",
    "2025-12-31",
    "2026-01-01",
}


PAYMENT_METHODS = [
    "card",
    "paypal",
    "digital_wallet",
    "bank_transfer",
]

PAYMENT_METHOD_WEIGHTS = [
    0.58,
    0.18,
    0.17,
    0.07,
]


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def load_config() -> dict[str, Any]:
    """Load synthetic-data generation configuration."""

    with CONFIG_PATH.open(
        "r",
        encoding="utf-8",
    ) as file:
        return yaml.safe_load(file)


# ---------------------------------------------------------------------------
# Randomness
# ---------------------------------------------------------------------------

def initialise_randomness(
    seed: int,
) -> tuple[np.random.Generator, Faker]:
    """Create deterministic NumPy and Faker generators."""

    rng = np.random.default_rng(seed)

    fake = Faker()

    Faker.seed(seed)
    fake.seed_instance(seed)

    return rng, fake


def random_utc_datetime(
    rng: np.random.Generator,
    start: datetime,
    end: datetime,
) -> datetime:
    """Generate a deterministic UTC datetime between boundaries."""

    start_ts = int(start.timestamp())
    end_ts = int(end.timestamp())

    timestamp = int(
        rng.integers(
            start_ts,
            end_ts + 1,
        )
    )

    return datetime.fromtimestamp(
        timestamp,
        tz=timezone.utc,
    )


# ---------------------------------------------------------------------------
# Product categories
# ---------------------------------------------------------------------------

def generate_categories(
    count: int,
) -> pd.DataFrame:
    """Generate product categories."""

    if count > len(CATEGORY_NAMES):
        raise ValueError(
            f"Requested {count} categories but only "
            f"{len(CATEGORY_NAMES)} category names are defined."
        )

    return pd.DataFrame(
        {
            "category_id": range(
                1,
                count + 1,
            ),
            "category_name": CATEGORY_NAMES[:count],
        }
    )


# ---------------------------------------------------------------------------
# Products
# ---------------------------------------------------------------------------

def generate_products(
    count: int,
    categories: pd.DataFrame,
    rng: np.random.Generator,
    fake: Faker,
    simulation_start: datetime,
) -> pd.DataFrame:
    """Generate products with realistic price relationships."""

    category_ids = categories[
        "category_id"
    ].to_numpy()

    created_start = (
        simulation_start
        - timedelta(days=3 * 365)
    )

    created_end = (
        simulation_start
        - timedelta(days=365)
    )

    rows = []

    for product_id in range(
        1,
        count + 1,
    ):
        category_id = int(
            rng.choice(category_ids)
        )

        unit_cost = round(
            float(
                rng.uniform(
                    3.0,
                    250.0,
                )
            ),
            2,
        )

        margin_multiplier = float(
            rng.uniform(
                1.20,
                2.40,
            )
        )

        unit_price = round(
            unit_cost
            * margin_multiplier,
            2,
        )

        weight_kg = round(
            float(
                rng.uniform(
                    0.05,
                    15.0,
                )
            ),
            3,
        )

        rows.append(
            {
                "product_id": product_id,
                "sku": f"SKU-{product_id:06d}",
                "product_name": (
                    fake.catch_phrase()[:200]
                ),
                "category_id": category_id,
                "unit_price": unit_price,
                "unit_cost": unit_cost,
                "weight_kg": weight_kg,
                "active": True,
                "created_at": random_utc_datetime(
                    rng,
                    created_start,
                    created_end,
                ),
            }
        )

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Warehouses
# ---------------------------------------------------------------------------

def generate_warehouses(
    count: int,
    rng: np.random.Generator,
    simulation_start: datetime,
) -> pd.DataFrame:
    """Generate fulfillment warehouse records."""

    if count > len(WAREHOUSE_LOCATIONS):
        raise ValueError(
            f"Requested {count} warehouses but only "
            f"{len(WAREHOUSE_LOCATIONS)} locations are defined."
        )

    created_start = (
        simulation_start
        - timedelta(days=5 * 365)
    )

    created_end = (
        simulation_start
        - timedelta(days=2 * 365)
    )

    rows = []

    for warehouse_id, warehouse in enumerate(
        WAREHOUSE_LOCATIONS[:count],
        start=1,
    ):
        rows.append(
            {
                "warehouse_id": warehouse_id,
                **warehouse,
                "capacity_units": int(
                    rng.integers(
                        50_000,
                        250_001,
                    )
                ),
                "created_at": random_utc_datetime(
                    rng,
                    created_start,
                    created_end,
                ),
            }
        )

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Customers
# ---------------------------------------------------------------------------

def generate_customers(
    count: int,
    countries: list[str],
    rng: np.random.Generator,
    simulation_start: datetime,
) -> pd.DataFrame:
    """Generate customers across configured countries."""

    country_weights = {
        "US": 0.45,
        "DE": 0.25,
        "GB": 0.18,
        "CA": 0.12,
    }

    weights = np.array(
        [
            country_weights.get(
                country,
                1.0,
            )
            for country in countries
        ],
        dtype=float,
    )

    weights /= weights.sum()

    created_start = (
        simulation_start
        - timedelta(days=4 * 365)
    )

    created_end = (
        simulation_start
        - timedelta(days=1)
    )

    rows = []

    for customer_id in range(
        1,
        count + 1,
    ):
        country_code = str(
            rng.choice(
                countries,
                p=weights,
            )
        )

        if country_code not in REGIONS:
            raise ValueError(
                f"No configured regions for country: "
                f"{country_code}"
            )

        region = str(
            rng.choice(
                REGIONS[country_code]
            )
        )

        rows.append(
            {
                "customer_id": customer_id,
                "customer_external_id": (
                    f"CUST-{customer_id:07d}"
                ),
                "country_code": country_code,
                "region": region,
                "created_at": random_utc_datetime(
                    rng,
                    created_start,
                    created_end,
                ),
            }
        )

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------

def generate_inventory(
    products: pd.DataFrame,
    warehouses: pd.DataFrame,
    rng: np.random.Generator,
    config: dict[str, Any],
    simulation_start: datetime,
) -> pd.DataFrame:
    """
    Generate initial warehouse inventory positions.

    Every product is stocked in at least two warehouses.

    A small percentage deliberately begins near or below its reorder
    threshold to create useful replenishment scenarios.
    """

    inventory_config = config[
        "inventory"
    ]

    stock_min = int(
        inventory_config[
            "initial_stock_min"
        ]
    )

    stock_max = int(
        inventory_config[
            "initial_stock_max"
        ]
    )

    reorder_min = int(
        inventory_config[
            "reorder_point_min"
        ]
    )

    reorder_max = int(
        inventory_config[
            "reorder_point_max"
        ]
    )

    if stock_min < 0:
        raise ValueError(
            "initial_stock_min cannot be negative."
        )

    if stock_max < stock_min:
        raise ValueError(
            "initial_stock_max must be >= "
            "initial_stock_min."
        )

    if reorder_min < 0:
        raise ValueError(
            "reorder_point_min cannot be negative."
        )

    if reorder_max < reorder_min:
        raise ValueError(
            "reorder_point_max must be >= "
            "reorder_point_min."
        )

    warehouse_ids = warehouses[
        "warehouse_id"
    ].to_numpy()

    if len(warehouse_ids) < 2:
        raise ValueError(
            "Inventory generation requires "
            "at least two warehouses."
        )

    rows = []

    for product_id in products[
        "product_id"
    ]:

        warehouse_count = int(
            rng.integers(
                2,
                len(warehouse_ids) + 1,
            )
        )

        selected_warehouses = (
            rng.choice(
                warehouse_ids,
                size=warehouse_count,
                replace=False,
            )
        )

        for warehouse_id in (
            selected_warehouses
        ):

            reorder_point = int(
                rng.integers(
                    reorder_min,
                    reorder_max + 1,
                )
            )

            low_stock = bool(
                rng.random() < 0.10
            )

            if low_stock:

                low_stock_minimum = max(
                    1,
                    reorder_point // 2,
                )

                on_hand_qty = int(
                    rng.integers(
                        low_stock_minimum,
                        reorder_point + 1,
                    )
                )

            else:

                normal_stock_minimum = max(
                    stock_min,
                    reorder_point,
                )

                if (
                    normal_stock_minimum
                    > stock_max
                ):
                    raise ValueError(
                        "Inventory configuration "
                        "is invalid: reorder point "
                        "can exceed maximum stock."
                    )

                on_hand_qty = int(
                    rng.integers(
                        normal_stock_minimum,
                        stock_max + 1,
                    )
                )

            rows.append(
                {
                    "warehouse_id": int(
                        warehouse_id
                    ),
                    "product_id": int(
                        product_id
                    ),
                    "on_hand_qty": (
                        on_hand_qty
                    ),
                    "reserved_qty": 0,
                    "reorder_point": (
                        reorder_point
                    ),
                    "updated_at": (
                        simulation_start
                    ),
                }
            )

    inventory = pd.DataFrame(
        rows
    )

    return (
        inventory
        .sort_values(
            by=[
                "warehouse_id",
                "product_id",
            ]
        )
        .reset_index(
            drop=True
        )
    )


# ---------------------------------------------------------------------------
# Order timestamp generation
# ---------------------------------------------------------------------------

def generate_order_timestamps(
    count: int,
    simulation_start: datetime,
    simulation_end: datetime,
    weekend_multiplier: float,
    holiday_multiplier: float,
    rng: np.random.Generator,
) -> list[datetime]:
    """
    Generate order timestamps with meaningful temporal demand patterns.

    Weekends receive additional demand weight and selected commercial/
    holiday dates receive a further demand multiplier.
    """

    days = pd.date_range(
        start=simulation_start.date(),
        end=simulation_end.date(),
        freq="D",
        tz="UTC",
    )

    day_weights = np.ones(
        len(days),
        dtype=float,
    )

    weekend_mask = (
        days.weekday >= 5
    )

    day_weights[
        weekend_mask
    ] *= weekend_multiplier

    holiday_mask = np.array(
        [
            str(day.date())
            in HOLIDAY_DATES
            for day in days
        ],
        dtype=bool,
    )

    day_weights[
        holiday_mask
    ] *= holiday_multiplier

    day_probabilities = (
        day_weights
        / day_weights.sum()
    )

    selected_day_indexes = (
        rng.choice(
            len(days),
            size=count,
            replace=True,
            p=day_probabilities,
        )
    )

    # E-commerce activity is intentionally heavier during
    # afternoon/evening hours than overnight.
    hour_weights = np.array(
        [
            0.30,  # 00
            0.20,
            0.15,
            0.12,
            0.10,
            0.12,
            0.20,
            0.40,
            0.70,
            0.95,
            1.10,
            1.20,
            1.30,
            1.35,
            1.40,
            1.45,
            1.55,
            1.70,
            1.85,
            2.00,
            1.90,
            1.60,
            1.15,
            0.70,
        ],
        dtype=float,
    )

    hour_probabilities = (
        hour_weights
        / hour_weights.sum()
    )

    hours = rng.choice(
        np.arange(24),
        size=count,
        p=hour_probabilities,
    )

    minutes = rng.integers(
        0,
        60,
        size=count,
    )

    seconds = rng.integers(
        0,
        60,
        size=count,
    )

    timestamps: list[datetime] = []

    for index in range(count):

        base_day = days[
            int(
                selected_day_indexes[
                    index
                ]
            )
        ]

        timestamp = (
            base_day
            + pd.Timedelta(
                hours=int(
                    hours[index]
                )
            )
            + pd.Timedelta(
                minutes=int(
                    minutes[index]
                )
            )
            + pd.Timedelta(
                seconds=int(
                    seconds[index]
                )
            )
        )

        timestamps.append(
            timestamp.to_pydatetime()
        )

    timestamps.sort()

    return timestamps


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------

def generate_orders(
    count: int,
    customers: pd.DataFrame,
    warehouses: pd.DataFrame,
    config: dict[str, Any],
    rng: np.random.Generator,
    simulation_start: datetime,
    simulation_end: datetime,
) -> pd.DataFrame:
    """
    Generate customer orders.

    Includes:
    - repeat-customer purchasing behavior
    - weekend and holiday demand effects
    - geography-aware warehouse routing
    - configured shipping-method mix
    - cancellation behavior
    """

    order_config = config[
        "orders"
    ]

    demand_config = config[
        "demand"
    ]

    shipping_config = config[
        "shipping"
    ]

    average_items = float(
        order_config[
            "average_items_per_order"
        ]
    )

    if average_items < 1:
        raise ValueError(
            "average_items_per_order "
            "must be >= 1."
        )

    cancellation_rate = float(
        order_config[
            "cancellation_rate"
        ]
    )

    weekend_multiplier = float(
        demand_config[
            "weekend_multiplier"
        ]
    )

    holiday_multiplier = float(
        demand_config[
            "holiday_multiplier"
        ]
    )

    shipping_methods = list(
        shipping_config[
            "methods"
        ].keys()
    )

    shipping_probabilities = np.array(
        [
            float(
                shipping_config[
                    "methods"
                ][method]
            )
            for method
            in shipping_methods
        ],
        dtype=float,
    )

    shipping_probabilities /= (
        shipping_probabilities.sum()
    )

    order_timestamps = (
        generate_order_timestamps(
            count=count,
            simulation_start=(
                simulation_start
            ),
            simulation_end=(
                simulation_end
            ),
            weekend_multiplier=(
                weekend_multiplier
            ),
            holiday_multiplier=(
                holiday_multiplier
            ),
            rng=rng,
        )
    )

    # A log-normal propensity gives us realistic repeat purchasers:
    # some customers place many orders while others place only a few.
    customer_propensity = (
        rng.lognormal(
            mean=0.0,
            sigma=0.85,
            size=len(customers),
        )
    )

    customer_probabilities = (
        customer_propensity
        / customer_propensity.sum()
    )

    selected_customer_indexes = (
        rng.choice(
            len(customers),
            size=count,
            replace=True,
            p=customer_probabilities,
        )
    )

    selected_customers = (
        customers.iloc[
            selected_customer_indexes
        ]
        .reset_index(
            drop=True
        )
    )

    warehouses_by_country: dict[
        str,
        np.ndarray,
    ] = {}

    for country_code, group in (
        warehouses.groupby(
            "country_code"
        )
    ):
        warehouses_by_country[
            str(country_code)
        ] = group[
            "warehouse_id"
        ].to_numpy()

    rows = []

    for index in range(count):

        order_id = index + 1

        customer = (
            selected_customers.iloc[
                index
            ]
        )

        destination_country = str(
            customer[
                "country_code"
            ]
        )

        destination_region = str(
            customer[
                "region"
            ]
        )

        country_warehouses = (
            warehouses_by_country.get(
                destination_country
            )
        )

        if (
            country_warehouses
            is None
            or len(
                country_warehouses
            )
            == 0
        ):
            raise ValueError(
                "No warehouse available for "
                f"destination country "
                f"{destination_country}."
            )

        # The US currently has two warehouses.
        # Give Chicago a slightly larger workload.
        if (
            destination_country == "US"
            and len(
                country_warehouses
            )
            == 2
        ):
            warehouse_id = int(
                rng.choice(
                    country_warehouses,
                    p=[
                        0.55,
                        0.45,
                    ],
                )
            )

        else:
            warehouse_id = int(
                rng.choice(
                    country_warehouses
                )
            )

        shipping_method = str(
            rng.choice(
                shipping_methods,
                p=shipping_probabilities,
            )
        )

        order_ts = (
            order_timestamps[
                index
            ]
        )

        if shipping_method == "same_day":

            promised_delivery_ts = (
                order_ts
                + timedelta(
                    hours=int(
                        rng.integers(
                            4,
                            13,
                        )
                    )
                )
            )

        elif shipping_method == "express":

            promised_delivery_ts = (
                order_ts
                + timedelta(
                    days=int(
                        rng.integers(
                            2,
                            4,
                        )
                    ),
                    hours=int(
                        rng.integers(
                            0,
                            13,
                        )
                    ),
                )
            )

        else:

            promised_delivery_ts = (
                order_ts
                + timedelta(
                    days=int(
                        rng.integers(
                            4,
                            8,
                        )
                    ),
                    hours=int(
                        rng.integers(
                            0,
                            13,
                        )
                    ),
                )
            )

        cancelled = bool(
            rng.random()
            < cancellation_rate
        )

        order_status = (
            "cancelled"
            if cancelled
            else "delivered"
        )

        payment_method = str(
            rng.choice(
                PAYMENT_METHODS,
                p=PAYMENT_METHOD_WEIGHTS,
            )
        )

        rows.append(
            {
                "order_id": order_id,
                "order_external_id": (
                    f"ORD-{order_id:08d}"
                ),
                "customer_id": int(
                    customer[
                        "customer_id"
                    ]
                ),
                "warehouse_id": (
                    warehouse_id
                ),
                "order_status": (
                    order_status
                ),
                "shipping_method": (
                    shipping_method
                ),
                "payment_method": (
                    payment_method
                ),
                "destination_country": (
                    destination_country
                ),
                "destination_region": (
                    destination_region
                ),
                "order_ts": (
                    order_ts
                ),
                "promised_delivery_ts": (
                    promised_delivery_ts
                ),
                "total_amount": 0.0,
                "created_at": (
                    order_ts
                ),
            }
        )

    return pd.DataFrame(
        rows
    )


# ---------------------------------------------------------------------------
# Order items
# ---------------------------------------------------------------------------

def generate_order_items(
    orders: pd.DataFrame,
    products: pd.DataFrame,
    inventory: pd.DataFrame,
    config: dict[str, Any],
    rng: np.random.Generator,
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
]:
    """
    Generate realistic order baskets.

    Products follow a Zipf-like popularity curve so a small set of items
    receives substantially more demand than the long tail.

    Product selection is also restricted to products stocked by the
    order's assigned warehouse.
    """

    average_items = float(
        config[
            "orders"
        ][
            "average_items_per_order"
        ]
    )

    product_ids = (
        products[
            "product_id"
        ]
        .astype(int)
        .to_numpy()
    )

    # Shuffle product identity before assigning popularity rank.
    # This prevents low product IDs from automatically becoming
    # the most popular products.
    ranked_product_ids = (
        rng.permutation(
            product_ids
        )
    )

    popularity_by_product: dict[
        int,
        float,
    ] = {}

    zipf_exponent = 1.15

    for rank, product_id in enumerate(
        ranked_product_ids,
        start=1,
    ):
        popularity_by_product[
            int(product_id)
        ] = (
            1.0
            / (
                rank
                ** zipf_exponent
            )
        )

    product_price = (
        products
        .set_index(
            "product_id"
        )[
            "unit_price"
        ]
        .to_dict()
    )

    warehouse_products: dict[
        int,
        np.ndarray,
    ] = {}

    for warehouse_id, group in (
        inventory.groupby(
            "warehouse_id"
        )
    ):
        warehouse_products[
            int(warehouse_id)
        ] = (
            group[
                "product_id"
            ]
            .astype(int)
            .to_numpy()
        )

    rows = []

    order_item_id = 1

    for order in (
        orders.itertuples(
            index=False
        )
    ):

        warehouse_id = int(
            order.warehouse_id
        )

        available_products = (
            warehouse_products[
                warehouse_id
            ]
        )

        item_count = (
            1
            + int(
                rng.poisson(
                    max(
                        average_items
                        - 1.0,
                        0.0,
                    )
                )
            )
        )

        # Keep baskets realistic and ensure sampling without replacement.
        item_count = min(
            item_count,
            7,
            len(
                available_products
            ),
        )

        product_weights = np.array(
            [
                popularity_by_product[
                    int(product_id)
                ]
                for product_id
                in available_products
            ],
            dtype=float,
        )

        product_probabilities = (
            product_weights
            / product_weights.sum()
        )

        selected_products = (
            rng.choice(
                available_products,
                size=item_count,
                replace=False,
                p=product_probabilities,
            )
        )

        for product_id_raw in (
            selected_products
        ):

            product_id = int(
                product_id_raw
            )

            quantity = int(
                rng.choice(
                    [
                        1,
                        2,
                        3,
                        4,
                    ],
                    p=[
                        0.72,
                        0.20,
                        0.06,
                        0.02,
                    ],
                )
            )

            base_price = float(
                product_price[
                    product_id
                ]
            )

            # A minority of purchases receive a realistic discount.
            if rng.random() < 0.22:

                sale_multiplier = float(
                    rng.uniform(
                        0.80,
                        0.95,
                    )
                )

            else:
                sale_multiplier = 1.0

            transaction_price = round(
                base_price
                * sale_multiplier,
                2,
            )

            rows.append(
                {
                    "order_item_id": (
                        order_item_id
                    ),
                    "order_id": int(
                        order.order_id
                    ),
                    "product_id": (
                        product_id
                    ),
                    "quantity": (
                        quantity
                    ),
                    "unit_price": (
                        transaction_price
                    ),
                }
            )

            order_item_id += 1

    order_items = pd.DataFrame(
        rows
    )

    # Derive the order total from the actual transaction-level items.
    item_subtotals = (
        order_items[
            "quantity"
        ]
        * order_items[
            "unit_price"
        ]
    )

    totals = (
        order_items
        .assign(
            item_subtotal=(
                item_subtotals
            )
        )
        .groupby(
            "order_id"
        )[
            "item_subtotal"
        ]
        .sum()
        .round(2)
    )

    updated_orders = (
        orders.copy()
    )

    updated_orders[
        "total_amount"
    ] = (
        updated_orders[
            "order_id"
        ]
        .map(
            totals
        )
        .round(2)
    )

    return (
        updated_orders,
        order_items,
    )



# ---------------------------------------------------------------------------
# Shipments
# ---------------------------------------------------------------------------

def _sigmoid_array(values: np.ndarray) -> np.ndarray:
    """Numerically stable logistic transform for synthetic risk scores."""

    clipped = np.clip(
        np.asarray(values, dtype=float),
        -40.0,
        40.0,
    )

    return 1.0 / (1.0 + np.exp(-clipped))


def _calibrated_probabilities(
    scores: np.ndarray,
    target_rate: float,
) -> np.ndarray:
    """
    Convert relative risk scores into probabilities while preserving the
    configured population event rate in expectation.

    The score ranking supplies learnable signal. A binary-searched intercept
    keeps the synthetic dataset aligned with the configured base prevalence.
    """

    values = np.asarray(scores, dtype=float)

    if values.ndim != 1 or len(values) == 0:
        raise ValueError("Risk scores must be a non-empty one-dimensional array.")

    if not 0.0 < target_rate < 1.0:
        raise ValueError("Target event rate must be strictly between 0 and 1.")

    low = -30.0
    high = 30.0

    for _ in range(80):
        midpoint = (low + high) / 2.0
        mean_probability = float(
            _sigmoid_array(values + midpoint).mean()
        )

        if mean_probability < target_rate:
            low = midpoint
        else:
            high = midpoint

    intercept = (low + high) / 2.0

    return _sigmoid_array(values + intercept)


def generate_shipments(
    orders: pd.DataFrame,
    config: dict[str, Any],
    rng: np.random.Generator,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Generate one shipment for every non-cancelled order.

    Version 2 keeps the configured overall exception/late prevalence but makes
    event probability depend on information that is legitimately available by
    shipment time. This fixes the original synthetic-data issue where delivery
    outcomes were independent Bernoulli draws and therefore not learnable by
    any leakage-safe model.

    The main generator RNG still consumes the same legacy outcome draws as the
    original implementation (shadow draws) so downstream simulation randomness
    remains stable. A dedicated risk RNG determines the V2 delivery outcomes.
    """

    fulfillment = config["fulfillment"]

    processing_hours = fulfillment["processing_hours"]
    transit_hours = fulfillment["transit_hours"]
    shipping_costs = fulfillment["shipping_cost"]

    exception_rate = float(
        fulfillment["delivery_exception_rate"]
    )
    late_rate = float(
        fulfillment["late_delivery_rate"]
    )

    if not 0.0 <= exception_rate <= 1.0:
        raise ValueError(
            "delivery_exception_rate must be between 0 and 1."
        )
    if not 0.0 <= late_rate <= 1.0:
        raise ValueError(
            "late_delivery_rate must be between 0 and 1."
        )

    carriers = fulfillment["carriers"]
    carrier_names = list(carriers.keys())
    carrier_probabilities = np.array(
        [float(carriers[name]) for name in carrier_names],
        dtype=float,
    )
    probability_total = carrier_probabilities.sum()
    if probability_total <= 0:
        raise ValueError(
            "Carrier probabilities must sum to a positive value."
        )
    carrier_probabilities = carrier_probabilities / probability_total

    risk_config = fulfillment.get("delivery_risk_v2", {})
    structured_risk = bool(risk_config.get("enabled", True))

    exception_signal_scale = float(
        risk_config.get("exception_signal_scale", 1.70)
    )
    late_signal_scale = float(
        risk_config.get("late_signal_scale", 1.35)
    )

    carrier_exception_effects = {
        "DHL": -0.55,
        "UPS": -0.25,
        "FedEx": 0.00,
        "DPD": 0.55,
        "GLS": 0.85,
        **risk_config.get("carrier_exception_effects", {}),
    }
    carrier_late_effects = {
        "DHL": -0.35,
        "UPS": -0.15,
        "FedEx": 0.05,
        "DPD": 0.35,
        "GLS": 0.55,
        **risk_config.get("carrier_late_effects", {}),
    }
    method_exception_effects = {
        "standard": -0.15,
        "express": 0.15,
        "same_day": 0.70,
        **risk_config.get("shipping_method_exception_effects", {}),
    }
    method_late_effects = {
        "standard": -0.25,
        "express": 0.15,
        "same_day": 0.90,
        **risk_config.get("shipping_method_late_effects", {}),
    }
    warehouse_effects = {
        1: 0.25,
        2: -0.15,
        3: 0.10,
        4: -0.10,
        5: 0.20,
    }
    warehouse_effects.update(
        {
            int(key): float(value)
            for key, value in risk_config.get(
                "warehouse_effects",
                {},
            ).items()
        }
    )
    month_effects = {
        1: 0.35,
        2: 0.10,
        6: 0.05,
        7: 0.10,
        11: 0.20,
        12: 0.55,
    }
    month_effects.update(
        {
            int(key): float(value)
            for key, value in risk_config.get(
                "month_effects",
                {},
            ).items()
        }
    )

    risk_seed = int(config.get("seed", 42)) + int(
        risk_config.get("seed_offset", 9107)
    )
    risk_rng = np.random.default_rng(risk_seed)

    updated_orders = orders.copy()
    provisional_rows: list[dict[str, Any]] = []
    shipment_id = 1

    for order in orders.itertuples(index=False):
        if str(order.order_status) == "cancelled":
            continue

        order_id = int(order.order_id)
        warehouse_id = int(order.warehouse_id)
        shipping_method = str(order.shipping_method)

        if shipping_method not in processing_hours:
            raise ValueError(
                "Missing processing-hours configuration for "
                f"{shipping_method}."
            )
        if shipping_method not in transit_hours:
            raise ValueError(
                "Missing transit-hours configuration for "
                f"{shipping_method}."
            )
        if shipping_method not in shipping_costs:
            raise ValueError(
                "Missing shipping-cost configuration for "
                f"{shipping_method}."
            )

        order_ts = pd.Timestamp(order.order_ts).to_pydatetime()
        expected_delivery_at = pd.Timestamp(
            order.promised_delivery_ts
        ).to_pydatetime()

        process_min = float(processing_hours[shipping_method]["min"])
        process_max = float(processing_hours[shipping_method]["max"])
        if process_max < process_min:
            raise ValueError(
                f"Invalid processing-hours range for {shipping_method}."
            )

        processing_duration = float(
            rng.uniform(process_min, process_max)
        )
        shipped_at = order_ts + timedelta(hours=processing_duration)
        created_at = order_ts + timedelta(
            hours=(processing_duration * 0.70)
        )

        transit_min = float(transit_hours[shipping_method]["min"])
        transit_max = float(transit_hours[shipping_method]["max"])
        if transit_max < transit_min:
            raise ValueError(
                f"Invalid transit-hours range for {shipping_method}."
            )

        transit_duration = float(
            rng.uniform(transit_min, transit_max)
        )
        natural_delivery_at = shipped_at + timedelta(
            hours=transit_duration
        )

        carrier = str(
            rng.choice(
                carrier_names,
                p=carrier_probabilities,
            )
        )

        cost_min = float(shipping_costs[shipping_method]["min"])
        cost_max = float(shipping_costs[shipping_method]["max"])
        if cost_max < cost_min:
            raise ValueError(
                f"Invalid shipping-cost range for {shipping_method}."
            )

        shipping_cost = round(
            float(rng.uniform(cost_min, cost_max)),
            2,
        )

        # Preserve the legacy main-RNG consumption pattern so later phases of
        # the synthetic simulation do not drift merely because the delivery
        # target mechanism changed.
        shadow_exception = bool(rng.random() < exception_rate)
        if not shadow_exception:
            shadow_late = bool(rng.random() < late_rate)
            if shadow_late:
                _ = float(rng.uniform(2.0, 36.0))

        process_ratio = processing_duration / max(process_max, 1e-9)
        expected_transit_hours = max(
            0.0,
            (expected_delivery_at - shipped_at).total_seconds() / 3600.0,
        )
        transit_window_ratio = expected_transit_hours / max(
            transit_max,
            1e-9,
        )
        ship_is_weekend = 1.0 if shipped_at.isoweekday() in (6, 7) else 0.0
        month_effect = float(month_effects.get(int(order_ts.month), 0.0))
        warehouse_effect = float(warehouse_effects.get(warehouse_id, 0.0))
        order_value = max(float(order.total_amount), 0.0)
        value_pressure = min(np.log1p(order_value) / 7.0, 1.5)

        if structured_risk:
            exception_score = exception_signal_scale * (
                float(carrier_exception_effects.get(carrier, 0.0))
                + float(method_exception_effects.get(shipping_method, 0.0))
                + (0.55 * ship_is_weekend)
                + (0.55 * process_ratio)
                + (0.15 * value_pressure)
                + warehouse_effect
                + month_effect
            )

            late_score = late_signal_scale * (
                float(carrier_late_effects.get(carrier, 0.0))
                + float(method_late_effects.get(shipping_method, 0.0))
                + (0.45 * ship_is_weekend)
                + (1.60 * process_ratio)
                - (1.10 * transit_window_ratio)
                + (0.10 * value_pressure)
                + warehouse_effect
                + (1.10 * month_effect)
            )
        else:
            exception_score = 0.0
            late_score = 0.0

        provisional_rows.append(
            {
                "shipment_id": shipment_id,
                "shipment_external_id": f"SHP-{shipment_id:08d}",
                "order_id": order_id,
                "warehouse_id": warehouse_id,
                "carrier": carrier,
                "shipped_at": shipped_at,
                "expected_delivery_at": expected_delivery_at,
                "shipping_cost": shipping_cost,
                "created_at": created_at,
                "_natural_delivery_at": natural_delivery_at,
                "_exception_score": exception_score,
                "_late_score": late_score,
            }
        )
        shipment_id += 1

    provisional = pd.DataFrame(provisional_rows)
    if provisional.empty:
        return updated_orders, provisional

    exception_probabilities = _calibrated_probabilities(
        provisional["_exception_score"].to_numpy(dtype=float),
        max(min(exception_rate, 1.0 - 1e-9), 1e-9),
    )
    is_exception = risk_rng.random(len(provisional)) < exception_probabilities

    is_late = np.zeros(len(provisional), dtype=bool)
    delivered_mask = ~is_exception

    if delivered_mask.any():
        late_probabilities = _calibrated_probabilities(
            provisional.loc[
                delivered_mask,
                "_late_score",
            ].to_numpy(dtype=float),
            max(min(late_rate, 1.0 - 1e-9), 1e-9),
        )
        is_late[delivered_mask] = (
            risk_rng.random(int(delivered_mask.sum()))
            < late_probabilities
        )

    shipment_rows: list[dict[str, Any]] = []
    exception_order_ids: list[int] = []

    for index, row in provisional.iterrows():
        if bool(is_exception[index]):
            shipment_status = "exception"
            delivered_at = None
            exception_order_ids.append(int(row["order_id"]))
        else:
            if bool(is_late[index]):
                late_delay = float(risk_rng.uniform(2.0, 36.0))
                delivered_at = max(
                    row["_natural_delivery_at"],
                    row["expected_delivery_at"]
                    + timedelta(hours=late_delay),
                )
            else:
                delivered_at = min(
                    row["_natural_delivery_at"],
                    row["expected_delivery_at"],
                )
                delivered_at = max(delivered_at, row["shipped_at"])
            shipment_status = "delivered"

        shipment_rows.append(
            {
                "shipment_id": int(row["shipment_id"]),
                "shipment_external_id": str(row["shipment_external_id"]),
                "order_id": int(row["order_id"]),
                "warehouse_id": int(row["warehouse_id"]),
                "carrier": str(row["carrier"]),
                "shipment_status": shipment_status,
                "shipped_at": row["shipped_at"],
                "expected_delivery_at": row["expected_delivery_at"],
                "delivered_at": delivered_at,
                "shipping_cost": float(row["shipping_cost"]),
                "created_at": row["created_at"],
            }
        )

    shipments = pd.DataFrame(shipment_rows)

    if exception_order_ids:
        updated_orders.loc[
            updated_orders["order_id"].isin(exception_order_ids),
            "order_status",
        ] = "shipped"

    return updated_orders, shipments



# ---------------------------------------------------------------------------
# Inventory movement ledger + order lifecycle events
# ---------------------------------------------------------------------------

def _normalised_probabilities(
    mapping: dict[str, Any],
    *,
    label: str,
) -> tuple[list[str], np.ndarray]:
    """Return deterministic choice labels and normalized probabilities."""

    names = list(mapping.keys())

    if not names:
        raise ValueError(
            f"{label} must contain at least one option."
        )

    probabilities = np.array(
        [
            float(mapping[name])
            for name in names
        ],
        dtype=float,
    )

    if (probabilities < 0).any():
        raise ValueError(
            f"{label} cannot contain negative probabilities."
        )

    total = float(
        probabilities.sum()
    )

    if total <= 0:
        raise ValueError(
            f"{label} probabilities must sum to a positive value."
        )

    return (
        names,
        probabilities / total,
    )


def _sample_config_value(
    rng: np.random.Generator,
    value: Any,
    *,
    default_min: float,
    default_max: float,
    label: str,
) -> float:
    """
    Sample a scalar or min/max configuration value.

    Supported shapes:
    - scalar: 5
    - mapping: {min: 2, max: 10}
    - two-item list/tuple: [2, 10]
    """

    if value is None:
        minimum = float(default_min)
        maximum = float(default_max)

    elif isinstance(
        value,
        dict,
    ):
        minimum = float(
            value.get(
                "min",
                default_min,
            )
        )

        maximum = float(
            value.get(
                "max",
                minimum,
            )
        )

    elif isinstance(
        value,
        (
            list,
            tuple,
        ),
    ):
        if len(value) != 2:
            raise ValueError(
                f"{label} list/tuple must contain exactly two values."
            )

        minimum = float(
            value[0]
        )
        maximum = float(
            value[1]
        )

    else:
        minimum = float(value)
        maximum = float(value)

    if minimum < 0:
        raise ValueError(
            f"{label} cannot be negative."
        )

    if maximum < minimum:
        raise ValueError(
            f"{label} max must be >= min."
        )

    if maximum == minimum:
        return minimum

    return float(
        rng.uniform(
            minimum,
            maximum,
        )
    )


def _lifecycle_delay(
    timing: dict[str, Any],
    key: str,
    rng: np.random.Generator,
    *,
    default_min: float,
    default_max: float,
    unit: str,
) -> timedelta:
    """Sample a configured lifecycle delay."""

    value = _sample_config_value(
        rng,
        timing.get(key),
        default_min=default_min,
        default_max=default_max,
        label=f"lifecycle.timing.{key}",
    )

    if unit == "minutes":
        return timedelta(
            minutes=value
        )

    if unit == "hours":
        return timedelta(
            hours=value
        )

    raise ValueError(
        f"Unsupported lifecycle delay unit: {unit}"
    )


def _json_payload(
    payload: dict[str, Any] | None = None,
) -> str:
    """Serialize event payloads deterministically for JSONB loading later."""

    return json.dumps(
        payload or {},
        sort_keys=True,
        separators=(
            ",",
            ":",
        ),
    )


def generate_inventory_movements_and_order_events(
    orders: pd.DataFrame,
    order_items: pd.DataFrame,
    shipments: pd.DataFrame,
    inventory: pd.DataFrame,
    config: dict[str, Any],
    rng: np.random.Generator,
    simulation_start: datetime,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Generate the FulfillAI inventory ledger and order lifecycle event stream.

    Inventory accounting semantics:
    - receipt: physical stock enters a warehouse
    - reservation: units are placed on hold for an order
    - release: a reservation is reversed
    - shipment: physical stock leaves the warehouse
    - return/adjustment remain supported by the SQL schema for later phases

    Opening inventory is represented by one receipt movement per inventory
    position. Replenishment receipts are inserted deterministically whenever
    projected available stock would otherwise be insufficient for a
    reservation or shipment.

    Lifecycle behavior:
    - all orders emit order_created
    - cancellation stage controls how far a cancelled order progresses
    - non-cancelled orders progress through payment, reservation, processing,
      packing, shipment creation, dispatch, and delivery/exception
    """

    lifecycle = dict(
        config.get(
            "lifecycle",
            {},
        )
    )

    timing = dict(
        lifecycle.get(
            "timing",
            {},
        )
    )

    cancellation_stages = dict(
        lifecycle.get(
            "cancellation_stages",
            {
                "pre_payment": 0.30,
                "post_payment": 0.30,
                "post_reservation": 0.40,
            },
        )
    )

    exception_reasons = dict(
        lifecycle.get(
            "exception_reasons",
            {
                "carrier_delay": 0.35,
                "weather": 0.20,
                "address_issue": 0.15,
                "damaged_in_transit": 0.15,
                "lost_in_transit": 0.10,
                "other": 0.05,
            },
        )
    )

    event_source = str(
        lifecycle.get(
            "event_source",
            "synthetic_generator",
        )
    )

    (
        cancellation_stage_names,
        cancellation_stage_probabilities,
    ) = _normalised_probabilities(
        cancellation_stages,
        label=(
            "lifecycle.cancellation_stages"
        ),
    )

    (
        exception_reason_names,
        exception_reason_probabilities,
    ) = _normalised_probabilities(
        exception_reasons,
        label=(
            "lifecycle.exception_reasons"
        ),
    )

    # ---------------------------------------------------------------
    # Fast lookup structures
    # ---------------------------------------------------------------

    item_map: dict[
        int,
        list[
            tuple[int, int]
        ],
    ] = {}

    for order_id, group in (
        order_items.groupby(
            "order_id",
            sort=False,
        )
    ):
        item_map[
            int(order_id)
        ] = [
            (
                int(row.product_id),
                int(row.quantity),
            )
            for row in group.itertuples(
                index=False
            )
        ]

    shipment_map = {
        int(row.order_id): row
        for row in shipments.itertuples(
            index=False
        )
    }

    inventory_state: dict[
        tuple[int, int],
        dict[str, int],
    ] = {}

    reorder_points: dict[
        tuple[int, int],
        int,
    ] = {}

    for row in inventory.itertuples(
        index=False
    ):
        key = (
            int(row.warehouse_id),
            int(row.product_id),
        )

        inventory_state[key] = {
            "on_hand": int(
                row.on_hand_qty
            ),
            "reserved": int(
                row.reserved_qty
            ),
        }

        reorder_points[key] = int(
            row.reorder_point
        )

    # ---------------------------------------------------------------
    # Event builders
    # ---------------------------------------------------------------

    event_rows: list[
        dict[str, Any]
    ] = []

    inventory_actions: list[
        dict[str, Any]
    ] = []

    event_id = 1
    action_sequence = 1

    def add_order_event(
        *,
        order_id: int,
        warehouse_id: int,
        event_type: str,
        event_ts: datetime,
        payload: dict[str, Any] | None = None,
    ) -> None:
        nonlocal event_id

        event_rows.append(
            {
                "event_id": event_id,
                "event_key": (
                    f"EVT-{event_id:09d}"
                ),
                "order_id": order_id,
                "warehouse_id": (
                    warehouse_id
                ),
                "event_type": event_type,
                "event_ts": event_ts,
                "source": event_source,
                "payload": (
                    _json_payload(
                        payload
                    )
                ),
                "ingested_at": (
                    event_ts
                    + timedelta(
                        seconds=1
                    )
                ),
            }
        )

        event_id += 1

    def add_inventory_action(
        *,
        warehouse_id: int,
        product_id: int,
        order_id: int,
        movement_type: str,
        quantity_change: int,
        event_ts: datetime,
    ) -> None:
        nonlocal action_sequence

        inventory_actions.append(
            {
                "sequence": (
                    action_sequence
                ),
                "warehouse_id": (
                    warehouse_id
                ),
                "product_id": (
                    product_id
                ),
                "order_id": (
                    order_id
                ),
                "movement_type": (
                    movement_type
                ),
                "quantity_change": (
                    quantity_change
                ),
                "event_ts": event_ts,
            }
        )

        action_sequence += 1

    # ---------------------------------------------------------------
    # Order lifecycle + candidate inventory actions
    # ---------------------------------------------------------------

    sorted_orders = (
        orders.sort_values(
            by=[
                "order_ts",
                "order_id",
            ]
        )
    )

    for order in sorted_orders.itertuples(
        index=False
    ):
        order_id = int(
            order.order_id
        )

        warehouse_id = int(
            order.warehouse_id
        )

        order_ts = (
            pd.Timestamp(
                order.order_ts
            )
            .to_pydatetime()
        )

        items = item_map.get(
            order_id,
            [],
        )

        if not items:
            raise ValueError(
                f"Order {order_id} has no order items."
            )

        total_units = sum(
            quantity
            for _, quantity
            in items
        )

        add_order_event(
            order_id=order_id,
            warehouse_id=warehouse_id,
            event_type="order_created",
            event_ts=order_ts,
            payload={
                "order_external_id": (
                    str(
                        order.order_external_id
                    )
                ),
                "shipping_method": (
                    str(
                        order.shipping_method
                    )
                ),
            },
        )

        payment_at = (
            order_ts
            + _lifecycle_delay(
                timing,
                "payment_confirmation_minutes",
                rng,
                default_min=2.0,
                default_max=20.0,
                unit="minutes",
            )
        )

        reservation_at = (
            payment_at
            + _lifecycle_delay(
                timing,
                "inventory_reservation_minutes",
                rng,
                default_min=1.0,
                default_max=15.0,
                unit="minutes",
            )
        )

        processing_at = (
            reservation_at
            + _lifecycle_delay(
                timing,
                "processing_start_minutes",
                rng,
                default_min=2.0,
                default_max=30.0,
                unit="minutes",
            )
        )

        packed_at = (
            processing_at
            + _lifecycle_delay(
                timing,
                "packing_hours",
                rng,
                default_min=0.25,
                default_max=2.0,
                unit="hours",
            )
        )

        if (
            str(order.order_status)
            == "cancelled"
        ):
            cancellation_stage = str(
                rng.choice(
                    cancellation_stage_names,
                    p=(
                        cancellation_stage_probabilities
                    ),
                )
            )

            cancellation_delay = (
                _lifecycle_delay(
                    timing,
                    "cancellation_delay_minutes",
                    rng,
                    default_min=5.0,
                    default_max=90.0,
                    unit="minutes",
                )
            )

            if (
                cancellation_stage
                == "pre_payment"
            ):
                cancelled_at = (
                    order_ts
                    + cancellation_delay
                )

            elif (
                cancellation_stage
                == "post_payment"
            ):
                add_order_event(
                    order_id=order_id,
                    warehouse_id=warehouse_id,
                    event_type=(
                        "payment_confirmed"
                    ),
                    event_ts=payment_at,
                    payload={
                        "payment_method": (
                            str(
                                order.payment_method
                            )
                        ),
                    },
                )

                cancelled_at = (
                    payment_at
                    + cancellation_delay
                )

            elif (
                cancellation_stage
                == "post_reservation"
            ):
                add_order_event(
                    order_id=order_id,
                    warehouse_id=warehouse_id,
                    event_type=(
                        "payment_confirmed"
                    ),
                    event_ts=payment_at,
                    payload={
                        "payment_method": (
                            str(
                                order.payment_method
                            )
                        ),
                    },
                )

                add_order_event(
                    order_id=order_id,
                    warehouse_id=warehouse_id,
                    event_type=(
                        "inventory_reserved"
                    ),
                    event_ts=reservation_at,
                    payload={
                        "line_count": len(items),
                        "units": total_units,
                    },
                )

                for (
                    product_id,
                    quantity,
                ) in items:
                    add_inventory_action(
                        warehouse_id=(
                            warehouse_id
                        ),
                        product_id=(
                            product_id
                        ),
                        order_id=order_id,
                        movement_type=(
                            "reservation"
                        ),
                        quantity_change=(
                            -quantity
                        ),
                        event_ts=(
                            reservation_at
                        ),
                    )

                cancelled_at = (
                    reservation_at
                    + cancellation_delay
                )

            else:
                raise ValueError(
                    "Unsupported cancellation stage "
                    f"{cancellation_stage!r}."
                )

            add_order_event(
                order_id=order_id,
                warehouse_id=warehouse_id,
                event_type="order_cancelled",
                event_ts=cancelled_at,
                payload={
                    "stage": (
                        cancellation_stage
                    )
                },
            )

            if (
                cancellation_stage
                == "post_reservation"
            ):
                release_at = (
                    cancelled_at
                    + _lifecycle_delay(
                        timing,
                        "inventory_release_minutes",
                        rng,
                        default_min=1.0,
                        default_max=15.0,
                        unit="minutes",
                    )
                )

                add_order_event(
                    order_id=order_id,
                    warehouse_id=warehouse_id,
                    event_type=(
                        "inventory_released"
                    ),
                    event_ts=release_at,
                    payload={
                        "line_count": len(items),
                        "units": total_units,
                    },
                )

                for (
                    product_id,
                    quantity,
                ) in items:
                    add_inventory_action(
                        warehouse_id=(
                            warehouse_id
                        ),
                        product_id=(
                            product_id
                        ),
                        order_id=order_id,
                        movement_type="release",
                        quantity_change=(
                            quantity
                        ),
                        event_ts=release_at,
                    )

            continue

        # -----------------------------------------------------------
        # Non-cancelled path
        # -----------------------------------------------------------

        shipment = shipment_map.get(
            order_id
        )

        if shipment is None:
            raise ValueError(
                "Non-cancelled order "
                f"{order_id} has no shipment."
            )

        shipment_created_at = (
            pd.Timestamp(
                shipment.created_at
            )
            .to_pydatetime()
        )

        shipped_at = (
            pd.Timestamp(
                shipment.shipped_at
            )
            .to_pydatetime()
        )

        # The shipment generator already owns the authoritative shipment
        # timestamps. If configured lifecycle delays would cross that
        # boundary, compress the pre-shipment milestones into the available
        # interval while preserving their order.
        if (
            packed_at
            >= shipment_created_at
        ):
            span_seconds = max(
                (
                    shipment_created_at
                    - order_ts
                ).total_seconds(),
                5.0,
            )

            payment_at = (
                order_ts
                + timedelta(
                    seconds=(
                        span_seconds
                        * 0.15
                    )
                )
            )

            reservation_at = (
                order_ts
                + timedelta(
                    seconds=(
                        span_seconds
                        * 0.30
                    )
                )
            )

            processing_at = (
                order_ts
                + timedelta(
                    seconds=(
                        span_seconds
                        * 0.50
                    )
                )
            )

            packed_at = (
                order_ts
                + timedelta(
                    seconds=(
                        span_seconds
                        * 0.80
                    )
                )
            )

        add_order_event(
            order_id=order_id,
            warehouse_id=warehouse_id,
            event_type="payment_confirmed",
            event_ts=payment_at,
            payload={
                "payment_method": (
                    str(
                        order.payment_method
                    )
                ),
            },
        )

        add_order_event(
            order_id=order_id,
            warehouse_id=warehouse_id,
            event_type="inventory_reserved",
            event_ts=reservation_at,
            payload={
                "line_count": len(items),
                "units": total_units,
            },
        )

        for (
            product_id,
            quantity,
        ) in items:
            add_inventory_action(
                warehouse_id=warehouse_id,
                product_id=product_id,
                order_id=order_id,
                movement_type="reservation",
                quantity_change=-quantity,
                event_ts=reservation_at,
            )

        add_order_event(
            order_id=order_id,
            warehouse_id=warehouse_id,
            event_type="processing_started",
            event_ts=processing_at,
        )

        add_order_event(
            order_id=order_id,
            warehouse_id=warehouse_id,
            event_type="order_packed",
            event_ts=packed_at,
        )

        add_order_event(
            order_id=order_id,
            warehouse_id=warehouse_id,
            event_type="shipment_created",
            event_ts=shipment_created_at,
            payload={
                "shipment_id": int(
                    shipment.shipment_id
                ),
                "shipment_external_id": (
                    str(
                        shipment.shipment_external_id
                    )
                ),
                "carrier": (
                    str(
                        shipment.carrier
                    )
                ),
            },
        )

        add_order_event(
            order_id=order_id,
            warehouse_id=warehouse_id,
            event_type="order_shipped",
            event_ts=shipped_at,
            payload={
                "shipment_id": int(
                    shipment.shipment_id
                )
            },
        )

        for (
            product_id,
            quantity,
        ) in items:
            add_inventory_action(
                warehouse_id=warehouse_id,
                product_id=product_id,
                order_id=order_id,
                movement_type="shipment",
                quantity_change=-quantity,
                event_ts=shipped_at,
            )

        if (
            str(
                shipment.shipment_status
            )
            == "delivered"
        ):
            delivered_at = (
                pd.Timestamp(
                    shipment.delivered_at
                )
                .to_pydatetime()
            )

            add_order_event(
                order_id=order_id,
                warehouse_id=warehouse_id,
                event_type=(
                    "order_delivered"
                ),
                event_ts=delivered_at,
                payload={
                    "shipment_id": int(
                        shipment.shipment_id
                    )
                },
            )

        elif (
            str(
                shipment.shipment_status
            )
            == "exception"
        ):
            expected_delivery_at = (
                pd.Timestamp(
                    shipment.expected_delivery_at
                )
                .to_pydatetime()
            )

            exception_at = max(
                expected_delivery_at,
                (
                    shipped_at
                    + timedelta(
                        minutes=1
                    )
                ),
            )

            exception_reason = str(
                rng.choice(
                    exception_reason_names,
                    p=(
                        exception_reason_probabilities
                    ),
                )
            )

            add_order_event(
                order_id=order_id,
                warehouse_id=warehouse_id,
                event_type=(
                    "delivery_exception"
                ),
                event_ts=exception_at,
                payload={
                    "shipment_id": int(
                        shipment.shipment_id
                    ),
                    "reason": (
                        exception_reason
                    ),
                },
            )

        else:
            raise ValueError(
                "Unsupported shipment status "
                f"{shipment.shipment_status!r}."
            )

    # ---------------------------------------------------------------
    # Build chronological inventory movement ledger
    # ---------------------------------------------------------------

    movement_rows: list[
        dict[str, Any]
    ] = []

    movement_id = 1

    def append_movement(
        *,
        warehouse_id: int,
        product_id: int,
        order_id: int | None,
        movement_type: str,
        quantity_change: int,
        event_ts: datetime,
    ) -> None:
        nonlocal movement_id

        if quantity_change == 0:
            raise ValueError(
                "Inventory movement quantity_change "
                "cannot be zero."
            )

        movement_rows.append(
            {
                "movement_id": movement_id,
                "warehouse_id": (
                    warehouse_id
                ),
                "product_id": (
                    product_id
                ),
                "order_id": order_id,
                "movement_type": (
                    movement_type
                ),
                "quantity_change": (
                    quantity_change
                ),
                "event_ts": event_ts,
                "created_at": event_ts,
            }
        )

        movement_id += 1

    # Opening inventory receipts make the physical ledger auditable from
    # its first state.
    for row in (
        inventory.sort_values(
            by=[
                "warehouse_id",
                "product_id",
            ]
        )
        .itertuples(
            index=False
        )
    ):
        opening_quantity = int(
            row.on_hand_qty
        )

        if opening_quantity > 0:
            append_movement(
                warehouse_id=int(
                    row.warehouse_id
                ),
                product_id=int(
                    row.product_id
                ),
                order_id=None,
                movement_type="receipt",
                quantity_change=(
                    opening_quantity
                ),
                event_ts=(
                    simulation_start
                ),
            )

    inventory_actions.sort(
        key=lambda action: (
            action["event_ts"],
            action["sequence"],
        )
    )

    for action in inventory_actions:
        warehouse_id = int(
            action["warehouse_id"]
        )

        product_id = int(
            action["product_id"]
        )

        order_id = int(
            action["order_id"]
        )

        movement_type = str(
            action["movement_type"]
        )

        quantity_change = int(
            action["quantity_change"]
        )

        event_ts = action[
            "event_ts"
        ]

        key = (
            warehouse_id,
            product_id,
        )

        if key not in inventory_state:
            raise ValueError(
                "Inventory action references "
                "an unknown warehouse/product pair: "
                f"{key}."
            )

        state = inventory_state[
            key
        ]

        if movement_type == "reservation":
            quantity = abs(
                quantity_change
            )

            available = (
                state["on_hand"]
                - state["reserved"]
            )

            if available < quantity:
                shortage = (
                    quantity
                    - available
                )

                reorder_point = (
                    reorder_points[
                        key
                    ]
                )

                receipt_quantity = max(
                    shortage,
                    max(
                        reorder_point * 2,
                        50,
                    ),
                )

                receipt_ts = max(
                    (
                        simulation_start
                        + timedelta(
                            seconds=1
                        )
                    ),
                    (
                        event_ts
                        - timedelta(
                            seconds=1
                        )
                    ),
                )

                append_movement(
                    warehouse_id=(
                        warehouse_id
                    ),
                    product_id=(
                        product_id
                    ),
                    order_id=None,
                    movement_type="receipt",
                    quantity_change=(
                        receipt_quantity
                    ),
                    event_ts=receipt_ts,
                )

                state["on_hand"] += (
                    receipt_quantity
                )

            state["reserved"] += (
                quantity
            )

        elif movement_type == "release":
            quantity = (
                quantity_change
            )

            if (
                quantity
                > state["reserved"]
            ):
                raise ValueError(
                    "Inventory release exceeds "
                    "currently reserved quantity for "
                    f"warehouse/product {key}."
                )

            state["reserved"] -= (
                quantity
            )

        elif movement_type == "shipment":
            quantity = abs(
                quantity_change
            )

            if (
                state["on_hand"]
                < quantity
            ):
                shortage = (
                    quantity
                    - state["on_hand"]
                )

                reorder_point = (
                    reorder_points[
                        key
                    ]
                )

                receipt_quantity = max(
                    shortage,
                    max(
                        reorder_point * 2,
                        50,
                    ),
                )

                receipt_ts = max(
                    (
                        simulation_start
                        + timedelta(
                            seconds=1
                        )
                    ),
                    (
                        event_ts
                        - timedelta(
                            seconds=1
                        )
                    ),
                )

                append_movement(
                    warehouse_id=(
                        warehouse_id
                    ),
                    product_id=(
                        product_id
                    ),
                    order_id=None,
                    movement_type="receipt",
                    quantity_change=(
                        receipt_quantity
                    ),
                    event_ts=receipt_ts,
                )

                state["on_hand"] += (
                    receipt_quantity
                )

            state["on_hand"] -= (
                quantity
            )

            # Dispatch consumes the corresponding reservation.
            state["reserved"] = max(
                0,
                (
                    state["reserved"]
                    - quantity
                ),
            )

        else:
            raise ValueError(
                "Unsupported generated inventory "
                f"movement type: {movement_type}."
            )

        append_movement(
            warehouse_id=warehouse_id,
            product_id=product_id,
            order_id=order_id,
            movement_type=movement_type,
            quantity_change=(
                quantity_change
            ),
            event_ts=event_ts,
        )

    inventory_movements = (
        pd.DataFrame(
            movement_rows
        )
        .sort_values(
            by=[
                "event_ts",
                "movement_id",
            ]
        )
        .reset_index(
            drop=True
        )
    )

    # Preserve nullable order references as integers.
    # Receipt/replenishment movements are not tied to an order,
    # while reservation/release/shipment movements are.
    inventory_movements["order_id"] = (
        inventory_movements["order_id"]
        .astype("Int64")
    )

    # Renumber after chronological sort so movement_id itself reflects ledger
    # order and remains deterministic.
    inventory_movements[
        "movement_id"
    ] = range(
        1,
        len(
            inventory_movements
        ) + 1,
    )

    order_events = (
        pd.DataFrame(
            event_rows
        )
        .sort_values(
            by=[
                "event_ts",
                "event_id",
            ]
        )
        .reset_index(
            drop=True
        )
    )

    # Preserve event_key uniqueness while also making event_id chronological.
    order_events[
        "event_id"
    ] = range(
        1,
        len(
            order_events
        ) + 1,
    )

    order_events[
        "event_key"
    ] = [
        f"EVT-{event_id:09d}"
        for event_id
        in order_events[
            "event_id"
        ]
    ]

    return (
        inventory_movements,
        order_events,
    )


# ---------------------------------------------------------------------------
# CSV output
# ---------------------------------------------------------------------------

def save_dataset(
    dataframe: pd.DataFrame,
    filename: str,
) -> None:
    """Write generated data to the raw synthetic-data directory."""

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    destination = (
        OUTPUT_DIR
        / filename
    )

    dataframe.to_csv(
        destination,
        index=False,
        date_format=(
            "%Y-%m-%dT%H:%M:%S%z"
        ),
    )

    print(
        f"Saved {len(dataframe):,} rows -> "
        f"{destination.relative_to(PROJECT_ROOT)}"
    )


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def main() -> None:
    """Generate FulfillAI synthetic datasets."""

    config = load_config()

    seed = int(
        config[
            "seed"
        ]
    )

    scale = config[
        "scale"
    ]

    countries = list(
        config[
            "geography"
        ][
            "countries"
        ]
    )

    simulation_start = (
        datetime.fromisoformat(
            config[
                "simulation"
            ][
                "start_date"
            ]
        )
        .replace(
            tzinfo=timezone.utc
        )
    )

    simulation_end = (
        datetime.fromisoformat(
            config[
                "simulation"
            ][
                "end_date"
            ]
        )
        .replace(
            tzinfo=timezone.utc
        )
    )

    if (
        simulation_end
        < simulation_start
    ):
        raise ValueError(
            "simulation.end_date must "
            "be on or after start_date."
        )

    rng, fake = (
        initialise_randomness(
            seed
        )
    )

    print(
        "Generating FulfillAI synthetic data..."
    )

    print(
        f"Random seed: {seed}"
    )

    print(
        f"Simulation window: "
        f"{simulation_start.date()} "
        f"to {simulation_end.date()}"
    )

    print()

    # ------------------------------------------------------------------
    # Master data
    # ------------------------------------------------------------------

    categories = (
        generate_categories(
            count=int(
                scale[
                    "categories"
                ]
            )
        )
    )

    products = (
        generate_products(
            count=int(
                scale[
                    "products"
                ]
            ),
            categories=categories,
            rng=rng,
            fake=fake,
            simulation_start=(
                simulation_start
            ),
        )
    )

    warehouses = (
        generate_warehouses(
            count=int(
                scale[
                    "warehouses"
                ]
            ),
            rng=rng,
            simulation_start=(
                simulation_start
            ),
        )
    )

    customers = (
        generate_customers(
            count=int(
                scale[
                    "customers"
                ]
            ),
            countries=countries,
            rng=rng,
            simulation_start=(
                simulation_start
            ),
        )
    )

    inventory = (
        generate_inventory(
            products=products,
            warehouses=warehouses,
            rng=rng,
            config=config,
            simulation_start=(
                simulation_start
            ),
        )
    )

    # ------------------------------------------------------------------
    # Transactional data
    # ------------------------------------------------------------------

    orders = generate_orders(
        count=int(
            scale[
                "target_orders"
            ]
        ),
        customers=customers,
        warehouses=warehouses,
        config=config,
        rng=rng,
        simulation_start=(
            simulation_start
        ),
        simulation_end=(
            simulation_end
        ),
    )

    orders, order_items = (
        generate_order_items(
            orders=orders,
            products=products,
            inventory=inventory,
            config=config,
            rng=rng,
        )
    )


    orders, shipments = (
        generate_shipments(
            orders=orders,
            config=config,
            rng=rng,
        )
    )

    (
        inventory_movements,
        order_events,
    ) = generate_inventory_movements_and_order_events(
        orders=orders,
        order_items=order_items,
        shipments=shipments,
        inventory=inventory,
        config=config,
        rng=rng,
        simulation_start=(
            simulation_start
        ),
    )

    # ------------------------------------------------------------------
    # Save datasets
    # ------------------------------------------------------------------

    save_dataset(
        categories,
        "product_categories.csv",
    )

    save_dataset(
        products,
        "products.csv",
    )

    save_dataset(
        warehouses,
        "warehouses.csv",
    )

    save_dataset(
        customers,
        "customers.csv",
    )

    save_dataset(
        inventory,
        "inventory.csv",
    )

    save_dataset(
        orders,
        "orders.csv",
    )

    save_dataset(
        order_items,
        "order_items.csv",
    )


    save_dataset(
        shipments,
        "shipments.csv",
    )

    save_dataset(
        inventory_movements,
        "inventory_movements.csv",
    )

    save_dataset(
        order_events,
        "order_events.csv",
    )

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    print()
    print(
        "Generation complete."
    )
    print()

    print(
        "Dataset sizes:"
    )

    print(
        f"  product_categories : "
        f"{len(categories):,}"
    )

    print(
        f"  products           : "
        f"{len(products):,}"
    )

    print(
        f"  warehouses         : "
        f"{len(warehouses):,}"
    )

    print(
        f"  customers          : "
        f"{len(customers):,}"
    )

    print(
        f"  inventory          : "
        f"{len(inventory):,}"
    )

    print(
        f"  orders             : "
        f"{len(orders):,}"
    )

    print(
        f"  order_items        : "
        f"{len(order_items):,}"
    )

    print(
        f"  shipments          : "
        f"{len(shipments):,}"
    )

    print(
        f"  inventory_movements: "
        f"{len(inventory_movements):,}"
    )

    print(
        f"  order_events       : "
        f"{len(order_events):,}"
    )

    print()

    average_items = (
        len(order_items)
        / len(orders)
    )

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

    weekend_rate = (
        pd.to_datetime(
            orders[
                "order_ts"
            ],
            utc=True,
        )
        .dt.weekday
        .ge(5)
        .mean()
        * 100
    )

    print(
        "Transactional summary:"
    )

    print(
        f"  average items/order : "
        f"{average_items:.2f}"
    )

    print(
        f"  cancellation rate   : "
        f"{cancellation_rate:.2f}%"
    )

    print(
        f"  weekend orders      : "
        f"{weekend_rate:.2f}%"
    )


if __name__ == "__main__":
    main()