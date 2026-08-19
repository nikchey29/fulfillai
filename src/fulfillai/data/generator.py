from __future__ import annotations

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