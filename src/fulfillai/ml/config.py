"""
Central machine-learning configuration for FulfillAI.

This module defines the contract between the Phase 7 feature datasets and
all downstream Phase 8 modeling code.

No model-specific training logic belongs here.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal


TaskType = Literal[
    "forecasting",
    "binary_classification",
]


# ======================================================================
# Project paths
# ======================================================================


PROJECT_ROOT = Path.cwd()

FEATURE_ROOT = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "features"
)

ARTIFACT_ROOT = (
    PROJECT_ROOT
    / "artifacts"
)

MODEL_ROOT = ARTIFACT_ROOT / "models"
METRIC_ROOT = ARTIFACT_ROOT / "metrics"
PREDICTION_ROOT = ARTIFACT_ROOT / "predictions"
EXPERIMENT_ROOT = ARTIFACT_ROOT / "experiments"


# ======================================================================
# Dataset contract
# ======================================================================


@dataclass(frozen=True)
class MLTaskConfig:
    """
    Modeling contract for one FulfillAI ML task.
    """

    name: str

    task_type: TaskType

    dataset_name: str

    split_column: str

    target_column: str

    primary_metric: str

    secondary_metrics: tuple[str, ...]

    positive_class: int | None = None

    threshold_metric: str | None = None

    # Optional binary row-eligibility flag applied after raw split validation.
    eligibility_column: str | None = None


# ======================================================================
# Demand forecasting
# ======================================================================


DEMAND_FORECASTING = MLTaskConfig(
    name="demand_forecasting",

    task_type="forecasting",

    dataset_name="demand_forecasting",

    split_column="demand_date",

    target_column="units_sold",

    primary_metric="wape",

    secondary_metrics=(
        "mae",
        "rmse",
        "smape",
    ),
)


# ======================================================================
# Delivery models
# ======================================================================


LATE_DELIVERY = MLTaskConfig(
    name="late_delivery",

    task_type="binary_classification",

    dataset_name="delivery_prediction",

    split_column="order_date",

    target_column="is_late_delivery",

    primary_metric="pr_auc",

    secondary_metrics=(
        "roc_auc",
        "precision",
        "recall",
        "f1",
        "log_loss",
        "brier_score",
    ),

    positive_class=1,

    threshold_metric="f1",

    eligibility_column="is_delivered",
)


DELIVERY_EXCEPTION = MLTaskConfig(
    name="delivery_exception",

    task_type="binary_classification",

    dataset_name="delivery_prediction",

    split_column="order_date",

    target_column="is_delivery_exception",

    primary_metric="pr_auc",

    secondary_metrics=(
        "roc_auc",
        "precision",
        "recall",
        "f1",
        "log_loss",
        "brier_score",
    ),

    positive_class=1,

    threshold_metric="f1",

    eligibility_column=None,
)


# ======================================================================
# Inventory models
# ======================================================================


STOCKOUT_RISK = MLTaskConfig(
    name="stockout_risk",

    task_type="binary_classification",

    dataset_name="inventory_risk",

    split_column="demand_date",

    target_column="target_stockout_next_7d",

    primary_metric="pr_auc",

    secondary_metrics=(
        "roc_auc",
        "precision",
        "recall",
        "f1",
        "precision_at_k",
        "recall_at_k",
        "lift_at_k",
    ),

    positive_class=1,

    threshold_metric="recall",
)


REORDER_BREACH_RISK = MLTaskConfig(
    name="reorder_breach_risk",

    task_type="binary_classification",

    dataset_name="inventory_risk",

    split_column="demand_date",

    target_column="target_reorder_breach_next_7d",

    primary_metric="pr_auc",

    secondary_metrics=(
        "roc_auc",
        "precision",
        "recall",
        "f1",
        "precision_at_k",
        "recall_at_k",
        "lift_at_k",
    ),

    positive_class=1,

    threshold_metric="f1",
)


# ======================================================================
# Registry
# ======================================================================


TASKS: dict[str, MLTaskConfig] = {
    config.name: config
    for config in (
        DEMAND_FORECASTING,
        LATE_DELIVERY,
        DELIVERY_EXCEPTION,
        STOCKOUT_RISK,
        REORDER_BREACH_RISK,
    )
}


def task_names() -> tuple[str, ...]:
    """Return all registered ML task names."""

    return tuple(TASKS)


def get_task_config(
    name: str,
) -> MLTaskConfig:
    """
    Return configuration for an ML task.
    """

    try:
        return TASKS[name]

    except KeyError as exc:

        available = ", ".join(
            task_names()
        )

        raise KeyError(
            f"Unknown ML task {name!r}. "
            f"Available tasks: {available}"
        ) from exc


def dataset_directory(
    task: MLTaskConfig,
) -> Path:
    """
    Return materialized Phase 7 dataset directory.
    """

    return (
        FEATURE_ROOT
        / task.dataset_name
    )


def split_path(
    task: MLTaskConfig,
    split: str,
) -> Path:
    """
    Return Parquet path for one split.
    """

    if split not in {
        "train",
        "validation",
        "test",
    }:

        raise ValueError(
            f"Unsupported split: {split!r}"
        )

    return (
        dataset_directory(task)
        / f"{split}.parquet"
    )


def metadata_path(
    task: MLTaskConfig,
) -> Path:
    """
    Return Phase 7 metadata path.
    """

    return (
        dataset_directory(task)
        / "metadata.json"
    )


def ensure_artifact_directories() -> None:
    """
    Create all generated ML artifact directories.
    """

    for path in (
        MODEL_ROOT,
        METRIC_ROOT,
        PREDICTION_ROOT,
        EXPERIMENT_ROOT,
    ):
        path.mkdir(
            parents=True,
            exist_ok=True,
        )


def main() -> None:
    """
    Print the registered FulfillAI ML contract.
    """

    print(
        "FulfillAI ML task configuration"
    )

    print("=" * 72)

    for name in task_names():

        config = get_task_config(name)

        print()
        print(name)

        print(
            f"  task type      : "
            f"{config.task_type}"
        )

        print(
            f"  dataset        : "
            f"{config.dataset_name}"
        )

        print(
            f"  split column   : "
            f"{config.split_column}"
        )

        print(
            f"  target         : "
            f"{config.target_column}"
        )

        print(
            f"  primary metric : "
            f"{config.primary_metric}"
        )


if __name__ == "__main__":
    main()