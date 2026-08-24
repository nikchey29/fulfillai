#!/usr/bin/env python3
"""Fast, data-free source verification for the FulfillAI repository.

This script deliberately does not connect to PostgreSQL, load generated Parquet
files, train models, or open final test partitions.
"""
from __future__ import annotations

import ast
import compileall
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]


class UniqueKeyLoader(yaml.SafeLoader):
    """PyYAML loader that rejects duplicate mapping keys."""


def _construct_mapping(loader: UniqueKeyLoader, node: yaml.MappingNode, deep: bool = False) -> dict[Any, Any]:
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise ValueError(f"Duplicate YAML key: {key!r} at line {key_node.start_mark.line + 1}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_mapping,
)


def check_required_files() -> None:
    required = [
        "README.md",
        "compose.yaml",
        ".env.example",
        "configs/data_generation.yaml",
        "sql/schema/001_core_schema.sql",
        "sql/models/002_daily_product_demand.sql",
        "sql/models/004_delivery_features.sql",
        "sql/models/005_inventory_risk_features.sql",
        "src/fulfillai/features/config.py",
        "src/fulfillai/ml/config.py",
        "src/fulfillai/ml/modeling/common_binary.py",
        "src/fulfillai/ml/demand/evaluate_hurdle_test.py",
        "src/fulfillai/ml/delivery_v2/evaluate_test.py",
        "src/fulfillai/ml/inventory/evaluate_test.py",
        "docs/results.md",
        "docs/ml_methodology.md",
    ]
    missing = [name for name in required if not (ROOT / name).exists()]
    if missing:
        raise RuntimeError(f"Missing required source files: {missing}")


def check_yaml() -> None:
    path = ROOT / "configs/data_generation.yaml"
    with path.open("r", encoding="utf-8") as handle:
        config = yaml.load(handle, Loader=UniqueKeyLoader)
    if not isinstance(config, dict):
        raise RuntimeError("data_generation.yaml root must be a mapping")
    v2 = config.get("fulfillment", {}).get("delivery_risk_v2", {})
    if v2.get("enabled") is not True:
        raise RuntimeError("Delivery V2 benchmark must remain explicitly enabled in the final source")


def check_python_syntax() -> None:
    if not compileall.compile_dir(ROOT / "src", quiet=1):
        raise RuntimeError("Python compilation failed under src/")
    for path in (ROOT / "scripts").glob("*.py"):
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def check_contracts() -> None:
    import sys

    sys.path.insert(0, str(ROOT))
    from src.fulfillai.features.config import (
        DATASET_CONFIGS,
        TEST_END_DATE,
        TEST_START_DATE,
        TRAIN_END_DATE,
        VALIDATION_END_DATE,
        VALIDATION_START_DATE,
        validate_configuration,
    )
    from src.fulfillai.ml.config import TASKS

    validate_configuration()

    expected_datasets = {"demand_forecasting", "delivery_prediction", "inventory_risk"}
    expected_tasks = {
        "demand_forecasting",
        "late_delivery",
        "delivery_exception",
        "stockout_risk",
        "reorder_breach_risk",
    }
    if set(DATASET_CONFIGS) != expected_datasets:
        raise RuntimeError(f"Unexpected feature dataset registry: {sorted(DATASET_CONFIGS)}")
    if set(TASKS) != expected_tasks:
        raise RuntimeError(f"Unexpected ML task registry: {sorted(TASKS)}")

    for config in DATASET_CONFIGS.values():
        forbidden = set(config.excluded_feature_columns)
        missing_targets = set(config.target_columns) - forbidden
        if missing_targets:
            raise RuntimeError(
                f"{config.name}: targets are not explicitly excluded from predictors: {sorted(missing_targets)}"
            )

    if not (TRAIN_END_DATE < VALIDATION_START_DATE <= VALIDATION_END_DATE < TEST_START_DATE <= TEST_END_DATE):
        raise RuntimeError("Chronological split boundaries are invalid")

    if TASKS["late_delivery"].eligibility_column != "is_delivered":
        raise RuntimeError("late_delivery eligibility contract changed")
    if TASKS["delivery_exception"].eligibility_column is not None:
        raise RuntimeError("delivery_exception should keep the full dispatched population")


def main() -> None:
    checks = [
        ("required files", check_required_files),
        ("YAML uniqueness / V2 config", check_yaml),
        ("Python syntax", check_python_syntax),
        ("feature + ML contracts", check_contracts),
    ]
    print("FulfillAI fast source verification")
    print("=" * 40)
    for name, fn in checks:
        fn()
        print(f"PASS  {name}")
    print("=" * 40)
    print("PASS  source package is internally consistent")
    print("NOTE  no PostgreSQL, Parquet, model training, or TEST access occurred")


if __name__ == "__main__":
    main()
