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


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def load_config() -> dict[str, Any]:
    """Load synthetic-data generation configuration."""
    with CONFIG_PATH.open("r", encoding="utf-8") as file:
        return yaml.safe_load(file)


# ---------------------------------------------------------------------------
# Randomness
# ---------------------------------------------------------------------------

def initialise_randomness(seed: int) -> tuple[np.random.Generator, Faker]:
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
    """Generate a deterministic UTC datetime between fixed boundaries."""
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

def generate_categories(count: int) -> pd.DataFrame:
    """Generate product categories."""
    if count > len(CATEGORY_NAMES):
        raise ValueError(
            f"Requested {count} categories but only "
            f"{len(CATEGORY_NAMES)} category names are defined."
        )

    return pd.DataFrame(
        {
            "category_id": range(1, count + 1),
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

    category_ids = categories["category_id"].to_numpy()

    created_start = simulation_start - timedelta(days=3 * 365)
    created_end = simulation_start - timedelta(days=365)

    rows = []

    for product_id in range(1, count + 1):
        category_id = int(
            rng.choice(category_ids)
        )

        unit_cost = round(
            float(rng.uniform(3.0, 250.0)),
            2,
        )

        margin_multiplier = float(
            rng.uniform(1.20, 2.40)
        )

        unit_price = round(
            unit_cost * margin_multiplier,
            2,
        )

        weight_kg = round(
            float(rng.uniform(0.05, 15.0)),
            3,
        )

        rows.append(
            {
                "product_id": product_id,
                "sku": f"SKU-{product_id:06d}",
                "product_name": fake.catch_phrase()[:200],
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

    created_start = simulation_start - timedelta(days=5 * 365)
    created_end = simulation_start - timedelta(days=2 * 365)

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
            country_weights.get(country, 1.0)
            for country in countries
        ],
        dtype=float,
    )

    weights /= weights.sum()

    created_start = simulation_start - timedelta(days=4 * 365)
    created_end = simulation_start - timedelta(days=1)

    rows = []

    for customer_id in range(1, count + 1):
        country_code = str(
            rng.choice(
                countries,
                p=weights,
            )
        )

        if country_code not in REGIONS:
            raise ValueError(
                f"No configured regions for country: {country_code}"
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

    Most inventory positions begin comfortably above their reorder point,
    while a small percentage deliberately begin near or below the reorder
    threshold. This gives later analytics and ML stages meaningful
    low-stock and replenishment scenarios.
    """

    inventory_config = config["inventory"]

    stock_min = int(
        inventory_config["initial_stock_min"]
    )

    stock_max = int(
        inventory_config["initial_stock_max"]
    )

    reorder_min = int(
        inventory_config["reorder_point_min"]
    )

    reorder_max = int(
        inventory_config["reorder_point_max"]
    )

    if stock_min < 0:
        raise ValueError(
            "initial_stock_min cannot be negative."
        )

    if stock_max < stock_min:
        raise ValueError(
            "initial_stock_max must be >= initial_stock_min."
        )

    if reorder_min < 0:
        raise ValueError(
            "reorder_point_min cannot be negative."
        )

    if reorder_max < reorder_min:
        raise ValueError(
            "reorder_point_max must be >= reorder_point_min."
        )

    warehouse_ids = warehouses[
        "warehouse_id"
    ].to_numpy()

    if len(warehouse_ids) < 2:
        raise ValueError(
            "Inventory generation requires at least two warehouses."
        )

    rows = []

    for product_id in products["product_id"]:

        # Each product is stocked in between 2 warehouses
        # and all available warehouses.
        warehouse_count = int(
            rng.integers(
                2,
                len(warehouse_ids) + 1,
            )
        )

        selected_warehouses = rng.choice(
            warehouse_ids,
            size=warehouse_count,
            replace=False,
        )

        for warehouse_id in selected_warehouses:

            reorder_point = int(
                rng.integers(
                    reorder_min,
                    reorder_max + 1,
                )
            )

            # About 10% of inventory positions intentionally
            # begin at or below their reorder threshold.
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

                if normal_stock_minimum > stock_max:
                    raise ValueError(
                        "Inventory configuration is invalid: "
                        "reorder point can exceed maximum stock."
                    )

                on_hand_qty = int(
                    rng.integers(
                        normal_stock_minimum,
                        stock_max + 1,
                    )
                )

            rows.append(
                {
                    "warehouse_id": int(warehouse_id),
                    "product_id": int(product_id),
                    "on_hand_qty": on_hand_qty,
                    "reserved_qty": 0,
                    "reorder_point": reorder_point,
                    "updated_at": simulation_start,
                }
            )

    inventory = pd.DataFrame(rows)

    return inventory.sort_values(
        by=[
            "warehouse_id",
            "product_id",
        ]
    ).reset_index(drop=True)


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

    destination = OUTPUT_DIR / filename

    dataframe.to_csv(
        destination,
        index=False,
        date_format="%Y-%m-%dT%H:%M:%S%z",
    )

    print(
        f"Saved {len(dataframe):,} rows -> "
        f"{destination.relative_to(PROJECT_ROOT)}"
    )


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def main() -> None:
    """Generate the FulfillAI synthetic master datasets."""

    config = load_config()

    seed = int(
        config["seed"]
    )

    scale = config["scale"]

    countries = list(
        config["geography"]["countries"]
    )

    simulation_start = datetime.fromisoformat(
        config["simulation"]["start_date"]
    ).replace(
        tzinfo=timezone.utc
    )

    rng, fake = initialise_randomness(seed)

    print(
        "Generating FulfillAI synthetic master data..."
    )

    print(
        f"Random seed: {seed}"
    )

    print(
        f"Simulation start: "
        f"{simulation_start.date()}"
    )

    print()

    # ------------------------------------------------------------------
    # Product categories
    # ------------------------------------------------------------------

    categories = generate_categories(
        count=int(
            scale["categories"]
        )
    )

    # ------------------------------------------------------------------
    # Products
    # ------------------------------------------------------------------

    products = generate_products(
        count=int(
            scale["products"]
        ),
        categories=categories,
        rng=rng,
        fake=fake,
        simulation_start=simulation_start,
    )

    # ------------------------------------------------------------------
    # Warehouses
    # ------------------------------------------------------------------

    warehouses = generate_warehouses(
        count=int(
            scale["warehouses"]
        ),
        rng=rng,
        simulation_start=simulation_start,
    )

    # ------------------------------------------------------------------
    # Customers
    # ------------------------------------------------------------------

    customers = generate_customers(
        count=int(
            scale["customers"]
        ),
        countries=countries,
        rng=rng,
        simulation_start=simulation_start,
    )

    # ------------------------------------------------------------------
    # Inventory
    # ------------------------------------------------------------------

    inventory = generate_inventory(
        products=products,
        warehouses=warehouses,
        rng=rng,
        config=config,
        simulation_start=simulation_start,
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

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    print()
    print("Generation complete.")
    print()

    print("Dataset sizes:")

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


if __name__ == "__main__":
    main()