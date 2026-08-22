"""
FulfillAI feature-pipeline configuration.

This module defines the contracts for every ML-ready dataset built from
the PostgreSQL analytical layer.

The configuration describes:

- PostgreSQL source view
- feature dataset name
- time column used for chronological splitting
- prediction targets
- primary/grain columns
- columns that must never become model inputs
- optional eligibility filtering
- train / validation / test boundaries

No database access or feature extraction should happen in this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final


# ======================================================================
# Project paths
# ======================================================================

PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[3]

FEATURE_OUTPUT_ROOT: Final[Path] = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "features"
)


# ======================================================================
# Time split
# ======================================================================
#
# Synthetic simulation window:
#
#     2025-08-01 -> 2026-07-31
#
# We deliberately use chronological splits.
#
# TRAIN
#     <= 2026-04-30
#
# VALIDATION
#     2026-05-01 -> 2026-05-31
#
# TEST
#     2026-06-01 -> 2026-07-31
#
# No random train_test_split() is permitted for these datasets.
# ======================================================================

TRAIN_END_DATE: Final[str] = "2026-04-30"

VALIDATION_START_DATE: Final[str] = "2026-05-01"
VALIDATION_END_DATE: Final[str] = "2026-05-31"

TEST_START_DATE: Final[str] = "2026-06-01"
TEST_END_DATE: Final[str] = "2026-07-31"


# ======================================================================
# Dataset configuration object
# ======================================================================


@dataclass(frozen=True)
class DatasetConfig:
    """
    Contract describing one ML feature dataset.

    Attributes
    ----------
    name:
        Stable internal dataset identifier.

    source_view:
        PostgreSQL analytical view used as the source.

    output_directory:
        Directory below data/processed/features/.

    split_column:
        Timestamp/date column used for chronological splitting.

    target_columns:
        Prediction labels.

        These remain in the exported dataset but MUST NOT be included in
        the predictor matrix X.

    primary_key:
        Columns defining the expected grain of the dataset.

    required_columns:
        Columns that must exist before the dataset can be materialized.

    excluded_feature_columns:
        Columns prohibited from becoming ML predictors.

        This includes:
        - targets
        - direct outcome information
        - future information
        - post-outcome information
        - technical identifiers when inappropriate as features

    eligibility_filter:
        Optional SQL-style eligibility condition represented as metadata.
        Filtering itself will be implemented in build_features.py.

    task_type:
        Human-readable ML task category.

    description:
        Description of the prediction problem.
    """

    name: str
    source_view: str
    output_directory: str
    split_column: str
    target_columns: tuple[str, ...]
    primary_key: tuple[str, ...]
    required_columns: tuple[str, ...]
    excluded_feature_columns: tuple[str, ...]
    eligibility_filter: str | None
    task_type: str
    description: str

    @property
    def output_path(self) -> Path:
        """Return the root output directory for this dataset."""

        return FEATURE_OUTPUT_ROOT / self.output_directory


# ======================================================================
# Demand forecasting
# ======================================================================
#
# Goal
# ----
#
# Predict product demand using only information available before the
# demand being predicted.
#
# Source
# ------
#
# vw_daily_product_demand
#
# Grain
# -----
#
# demand_date × warehouse_id × product_id
#
# The target is units_sold.
#
# IMPORTANT:
#
# Same-day realized demand must not be used as an input feature.
# Gross requested units and cancellation outcomes are also excluded from
# the predictor matrix because they describe the realized transaction
# state of the target day.
# ======================================================================


DEMAND_FORECASTING_CONFIG: Final[DatasetConfig] = DatasetConfig(
    name="demand_forecasting",
    source_view="vw_daily_product_demand",
    output_directory="demand_forecasting",
    split_column="demand_date",
    target_columns=(
        "units_sold",
    ),
    primary_key=(
        "demand_date",
        "warehouse_id",
        "product_id",
    ),
    required_columns=(
        "demand_date",
        "warehouse_id",
        "product_id",
        "units_sold",
    ),
    excluded_feature_columns=(
        # Target
        "units_sold",

        # Same-day realized demand / transaction outcomes
        "gross_units_requested",
        "cancelled_units",
        "revenue",

        # Identifiers that should not be treated as numerical signals
        "warehouse_id",
        "product_id",
    ),
    eligibility_filter=None,
    task_type="forecasting",
    description=(
        "Forecast future warehouse/product demand using historical "
        "demand and calendar features."
    ),
)


# ======================================================================
# Delivery prediction
# ======================================================================
#
# Goal
# ----
#
# Predict whether a shipment will:
#
#     1. become a delivery exception
#     2. arrive late
#
# Source
# ------
#
# vw_delivery_features
#
# Grain
# -----
#
# one row per shipment
#
# Outcome information such as actual delivery timestamps, final shipment
# status and realized transit duration must NEVER be used as predictors.
# ======================================================================


DELIVERY_PREDICTION_CONFIG: Final[DatasetConfig] = DatasetConfig(
    name="delivery_prediction",
    source_view="vw_delivery_features",
    output_directory="delivery_prediction",

    # We will validate this column against the PostgreSQL view before
    # materialization.
    split_column="order_date",

    target_columns=(
        "is_late_delivery",
        "is_delivery_exception",
    ),
    primary_key=(
        "shipment_id",
    ),
    required_columns=(
        "shipment_id",
        "order_id",
        "warehouse_id",
        "is_late_delivery",
        "is_delivery_exception",
    ),
    excluded_feature_columns=(
        # Targets
        "is_late_delivery",
        "is_delivery_exception",

        # Direct final-state outcome columns
        "is_delivered",
        "shipment_status",

        # Post-outcome timestamps
        "delivered_at",

        # Realized delivery information
        "actual_transit_hours",
        "delivery_delay_hours",

        # Technical identifiers
        "shipment_id",
        "order_id",
        "customer_id",
    ),
    eligibility_filter=None,
    task_type="classification",
    description=(
        "Predict late deliveries and delivery exceptions using "
        "information available before the delivery outcome."
    ),
)


# ======================================================================
# Inventory risk
# ======================================================================
#
# Goal
# ----
#
# Predict whether a warehouse/product inventory position will:
#
#     1. stock out within the next seven days
#     2. cross its reorder threshold within the next seven days
#
# Source
# ------
#
# vw_inventory_risk_features
#
# Grain
# -----
#
# demand_date × warehouse_id × product_id
#
# Only rows explicitly marked ml_feature_eligible = 1 may be used.
#
# Future-window columns exist solely for constructing target labels.
# They are forbidden as predictors.
# ======================================================================


INVENTORY_RISK_CONFIG: Final[DatasetConfig] = DatasetConfig(
    name="inventory_risk",
    source_view="vw_inventory_risk_features",
    output_directory="inventory_risk",
    split_column="demand_date",
    target_columns=(
        "target_stockout_next_7d",
        "target_reorder_breach_next_7d",
    ),
    primary_key=(
        "demand_date",
        "warehouse_id",
        "product_id",
    ),
    required_columns=(
        "demand_date",
        "warehouse_id",
        "product_id",
        "ml_feature_eligible",
        "target_stockout_next_7d",
        "target_reorder_breach_next_7d",
    ),
    excluded_feature_columns=(
        # Targets
        "target_stockout_next_7d",
        "target_stockout_days_next_7d",
        "target_reorder_breach_next_7d",
        "target_min_available_next_7d",

        # Future information used only to construct targets
        "future_observation_days",
        "future_min_available_qty_raw",
        "future_stockout_days_raw",
        "future_reorder_breach_raw",

        # Current-day realized inventory state
        "ending_on_hand_qty",
        "ending_reserved_qty",
        "ending_available_qty",

        # Current-day realized demand
        "units_sold",
        "revenue",

        # Eligibility metadata
        "ml_feature_eligible",

        # Technical identifiers
        "warehouse_id",
        "product_id",
    ),
    eligibility_filter="ml_feature_eligible = 1",
    task_type="classification",
    description=(
        "Predict seven-day stockout and reorder-threshold risk using "
        "historical demand and prior inventory state."
    ),
)


# ======================================================================
# Registry
# ======================================================================
#
# All downstream feature-pipeline modules should obtain configurations
# from this registry rather than importing individual constants.
# ======================================================================


DATASET_CONFIGS: Final[dict[str, DatasetConfig]] = {
    DEMAND_FORECASTING_CONFIG.name: DEMAND_FORECASTING_CONFIG,
    DELIVERY_PREDICTION_CONFIG.name: DELIVERY_PREDICTION_CONFIG,
    INVENTORY_RISK_CONFIG.name: INVENTORY_RISK_CONFIG,
}


# ======================================================================
# Convenience helpers
# ======================================================================


def get_dataset_config(name: str) -> DatasetConfig:
    """
    Return the configuration for a dataset.

    Raises
    ------
    KeyError
        If the requested dataset does not exist.
    """

    try:
        return DATASET_CONFIGS[name]

    except KeyError as exc:
        available = ", ".join(sorted(DATASET_CONFIGS))

        raise KeyError(
            f"Unknown feature dataset: {name!r}. "
            f"Available datasets: {available}"
        ) from exc


def dataset_names() -> tuple[str, ...]:
    """Return all configured dataset names."""

    return tuple(DATASET_CONFIGS)


def validate_configuration() -> None:
    """
    Perform configuration-only integrity checks.

    This does not connect to PostgreSQL.

    Database schema validation will happen later in validate.py.
    """

    if not DATASET_CONFIGS:
        raise ValueError("No feature datasets are configured.")

    for name, config in DATASET_CONFIGS.items():

        if name != config.name:
            raise ValueError(
                f"Registry key {name!r} does not match "
                f"DatasetConfig.name {config.name!r}."
            )

        if not config.source_view.startswith("vw_"):
            raise ValueError(
                f"{name}: source_view must reference an analytical view."
            )

        if not config.primary_key:
            raise ValueError(
                f"{name}: primary_key cannot be empty."
            )

        if not config.required_columns:
            raise ValueError(
                f"{name}: required_columns cannot be empty."
            )

        missing_targets = (
            set(config.target_columns)
            - set(config.required_columns)
        )

        if missing_targets:
            raise ValueError(
                f"{name}: target columns missing from required_columns: "
                f"{sorted(missing_targets)}"
            )

        targets_not_excluded = (
            set(config.target_columns)
            - set(config.excluded_feature_columns)
        )

        if targets_not_excluded:
            raise ValueError(
                f"{name}: target columns must also be excluded from "
                f"predictor features: "
                f"{sorted(targets_not_excluded)}"
            )


# Validate static configuration immediately when imported.
validate_configuration()