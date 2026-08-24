from __future__ import annotations

from src.fulfillai.features.config import (
    DATASET_CONFIGS,
    TEST_END_DATE,
    TEST_START_DATE,
    TRAIN_END_DATE,
    VALIDATION_END_DATE,
    VALIDATION_START_DATE,
)
from src.fulfillai.ml.config import TASKS


def test_expected_registries() -> None:
    assert set(DATASET_CONFIGS) == {
        "demand_forecasting",
        "delivery_prediction",
        "inventory_risk",
    }
    assert set(TASKS) == {
        "demand_forecasting",
        "late_delivery",
        "delivery_exception",
        "stockout_risk",
        "reorder_breach_risk",
    }


def test_targets_are_explicitly_excluded_from_predictors() -> None:
    for config in DATASET_CONFIGS.values():
        assert set(config.target_columns) <= set(config.excluded_feature_columns)


def test_chronology_is_strictly_ordered() -> None:
    assert TRAIN_END_DATE < VALIDATION_START_DATE
    assert VALIDATION_START_DATE <= VALIDATION_END_DATE
    assert VALIDATION_END_DATE < TEST_START_DATE
    assert TEST_START_DATE <= TEST_END_DATE


def test_delivery_population_contracts() -> None:
    assert TASKS["late_delivery"].eligibility_column == "is_delivered"
    assert TASKS["delivery_exception"].eligibility_column is None
