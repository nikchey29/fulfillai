"""
Demand forecasting baselines for FulfillAI.

Phase 8 modeling begins with deliberately simple forecasting strategies.

These baselines establish the minimum performance that later statistical
and machine-learning models must beat.

Important
---------
Model selection is performed using the validation partition only.

The test partition remains untouched until a final candidate model has
been selected.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from ..config import (
    METRIC_ROOT,
    ensure_artifact_directories,
)
from ..data import (
    LoadedSplit,
    load_task_dataset,
)
from ..metrics import (
    forecasting_metrics,
)


# ======================================================================
# Constants
# ======================================================================


TASK_NAME = "demand_forecasting"

PRIMARY_METRIC = "wape"

OUTPUT_PATH = (
    METRIC_ROOT
    / "demand_forecasting_baselines.json"
)


# ======================================================================
# Baseline feature contract
# ======================================================================


BASELINE_COLUMNS: dict[str, str | None] = {
    "zero_forecast": None,
    "lag_1": "lag_1_units",
    "lag_7": "lag_7_units",
    "rolling_7": "rolling_7d_avg_units",
    "rolling_28": "rolling_28d_avg_units",
}


# ======================================================================
# Exceptions
# ======================================================================


class BaselineError(RuntimeError):
    """Raised when baseline evaluation cannot safely continue."""


# ======================================================================
# Validation helpers
# ======================================================================


def validate_baseline_columns(
    split: LoadedSplit,
) -> None:
    """
    Ensure all historical baseline columns exist and are usable.
    """

    frame = split.frame

    required_columns = [
        column
        for column in BASELINE_COLUMNS.values()
        if column is not None
    ]

    missing = sorted(
        set(required_columns)
        - set(frame.columns)
    )

    if missing:

        raise BaselineError(
            "Demand baseline columns are missing: "
            f"{missing}"
        )

    for column in required_columns:

        values = pd.to_numeric(
            frame[column],
            errors="coerce",
        )

        null_count = int(
            values.isna().sum()
        )

        if null_count:

            raise BaselineError(
                f"{split.name}: baseline column "
                f"{column!r} contains "
                f"{null_count:,} null/non-numeric values."
            )

        if not np.isfinite(
            values.to_numpy(
                dtype=float
            )
        ).all():

            raise BaselineError(
                f"{split.name}: baseline column "
                f"{column!r} contains infinite values."
            )

        negative_count = int(
            (values < 0).sum()
        )

        if negative_count:

            raise BaselineError(
                f"{split.name}: baseline column "
                f"{column!r} contains "
                f"{negative_count:,} negative values."
            )


# ======================================================================
# Prediction generation
# ======================================================================


def generate_baseline_predictions(
    split: LoadedSplit,
) -> dict[str, np.ndarray]:
    """
    Generate deterministic demand forecasts.

    All lag/rolling features were created upstream using historical data,
    so no future observations are accessed here.
    """

    validate_baseline_columns(
        split
    )

    frame = split.frame

    predictions: dict[
        str,
        np.ndarray,
    ] = {}

    for (
        baseline_name,
        source_column,
    ) in BASELINE_COLUMNS.items():

        if source_column is None:

            values = np.zeros(
                len(frame),
                dtype=float,
            )

        else:

            values = (
                pd.to_numeric(
                    frame[source_column],
                    errors="raise",
                )
                .to_numpy(
                    dtype=float
                )
            )

        predictions[
            baseline_name
        ] = values

    return predictions


# ======================================================================
# Baseline evaluation
# ======================================================================


def evaluate_baselines(
    split: LoadedSplit,
) -> pd.DataFrame:
    """
    Evaluate all baseline models on one partition.
    """

    y_true = (
        pd.to_numeric(
            split.y,
            errors="raise",
        )
        .to_numpy(
            dtype=float
        )
    )

    if not np.isfinite(
        y_true
    ).all():

        raise BaselineError(
            f"{split.name}: target contains "
            "NaN or infinite values."
        )

    predictions = (
        generate_baseline_predictions(
            split
        )
    )

    rows: list[dict] = []

    for (
        baseline_name,
        prediction,
    ) in predictions.items():

        metrics = forecasting_metrics(
            y_true,
            prediction,
        )

        rows.append(
            {
                "baseline": baseline_name,
                "rows": len(y_true),
                **metrics,
            }
        )

    leaderboard = pd.DataFrame(
        rows
    )

    leaderboard = (
        leaderboard
        .sort_values(
            by=[
                PRIMARY_METRIC,
                "mae",
                "rmse",
            ],
            ascending=[
                True,
                True,
                True,
            ],
        )
        .reset_index(
            drop=True
        )
    )

    leaderboard.insert(
        0,
        "rank",
        np.arange(
            1,
            len(leaderboard) + 1,
        ),
    )

    return leaderboard


# ======================================================================
# Diagnostics
# ======================================================================


def print_target_summary(
    split: LoadedSplit,
) -> None:
    """Print useful statistics about demand."""

    target = (
        pd.to_numeric(
            split.y,
            errors="raise",
        )
        .to_numpy(
            dtype=float
        )
    )

    zero_rows = int(
        np.sum(
            target == 0
        )
    )

    positive_rows = int(
        np.sum(
            target > 0
        )
    )

    zero_pct = (
        zero_rows
        / len(target)
        * 100.0
    )

    positive_pct = (
        positive_rows
        / len(target)
        * 100.0
    )

    print()
    print(
        "VALIDATION TARGET PROFILE"
    )

    print(
        "-" * 88
    )

    print(
        f"rows                 : "
        f"{len(target):,}"
    )

    print(
        f"zero-demand rows     : "
        f"{zero_rows:,} "
        f"({zero_pct:.2f}%)"
    )

    print(
        f"positive-demand rows : "
        f"{positive_rows:,} "
        f"({positive_pct:.2f}%)"
    )

    print(
        f"mean units sold      : "
        f"{target.mean():.4f}"
    )

    print(
        f"total units sold     : "
        f"{target.sum():,.0f}"
    )


def print_leaderboard(
    leaderboard: pd.DataFrame,
) -> None:
    """Print baseline leaderboard."""

    print()
    print(
        "DEMAND FORECASTING BASELINE LEADERBOARD"
    )

    print(
        "=" * 88
    )

    display = leaderboard.copy()

    for column in (
        "mae",
        "rmse",
        "wape",
        "smape",
    ):

        display[column] = (
            display[column]
            .map(
                lambda value: (
                    f"{value:.4f}"
                )
            )
        )

    print(
        display.to_string(
            index=False
        )
    )


# ======================================================================
# Artifact persistence
# ======================================================================


def save_results(
    *,
    split: LoadedSplit,
    leaderboard: pd.DataFrame,
) -> Path:
    """
    Persist reproducible validation baseline metrics.
    """

    ensure_artifact_directories()

    best = (
        leaderboard
        .iloc[0]
        .to_dict()
    )

    records = []

    for record in (
        leaderboard
        .to_dict(
            orient="records"
        )
    ):

        records.append(
            {
                key: (
                    value.item()
                    if isinstance(
                        value,
                        np.generic,
                    )
                    else value
                )
                for key, value
                in record.items()
            }
        )

    payload = {
        "artifact_version": 1,

        "generated_at_utc": (
            datetime.now(
                timezone.utc
            )
            .isoformat()
        ),

        "task": TASK_NAME,

        "evaluation_split": (
            split.name
        ),

        "test_set_used": False,

        "primary_metric": (
            PRIMARY_METRIC
        ),

        "rows": split.rows,

        "winner": {
            "baseline": (
                best["baseline"]
            ),

            "wape": float(
                best["wape"]
            ),

            "mae": float(
                best["mae"]
            ),

            "rmse": float(
                best["rmse"]
            ),

            "smape": float(
                best["smape"]
            ),
        },

        "leaderboard": records,
    }

    OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with OUTPUT_PATH.open(
        "w",
        encoding="utf-8",
    ) as handle:

        json.dump(
            payload,
            handle,
            indent=2,
        )

        handle.write(
            "\n"
        )

    return OUTPUT_PATH


# ======================================================================
# Main
# ======================================================================


def main() -> None:
    """
    Evaluate demand baselines on validation data.

    The test partition is deliberately not evaluated.
    """

    print(
        "FulfillAI demand forecasting baselines"
    )

    print(
        "=" * 88
    )

    dataset = load_task_dataset(
        TASK_NAME
    )

    validation = (
        dataset.validation
    )

    print(
        f"task             : "
        f"{TASK_NAME}"
    )

    print(
        f"evaluation split : "
        f"{validation.name}"
    )

    print(
        f"rows             : "
        f"{validation.rows:,}"
    )

    print(
        f"target           : "
        f"{dataset.task.target_column}"
    )

    print(
        "test set         : LOCKED / NOT USED"
    )

    print_target_summary(
        validation
    )

    leaderboard = (
        evaluate_baselines(
            validation
        )
    )

    print_leaderboard(
        leaderboard
    )

    winner = (
        leaderboard
        .iloc[0]
    )

    zero = (
        leaderboard[
            leaderboard[
                "baseline"
            ]
            == "zero_forecast"
        ]
        .iloc[0]
    )

    print()
    print(
        "BEST VALIDATION BASELINE"
    )

    print(
        "-" * 88
    )

    print(
        f"model : "
        f"{winner['baseline']}"
    )

    print(
        f"WAPE  : "
        f"{winner['wape']:.4f}%"
    )

    print(
        f"MAE   : "
        f"{winner['mae']:.4f}"
    )

    print(
        f"RMSE  : "
        f"{winner['rmse']:.4f}"
    )

    print(
        f"sMAPE : "
        f"{winner['smape']:.4f}%"
    )

    zero_wape = float(
        zero["wape"]
    )

    winner_wape = float(
        winner["wape"]
    )

    if zero_wape > 0:

        improvement = (
            (
                zero_wape
                - winner_wape
            )
            / zero_wape
            * 100.0
        )

        print()
        print(
            "WAPE improvement over "
            f"zero forecast : "
            f"{improvement:.2f}%"
        )

    output_path = save_results(
        split=validation,
        leaderboard=leaderboard,
    )

    print()
    print(
        f"metrics artifact : "
        f"{output_path}"
    )

    print(
        "test evaluation  : NOT PERFORMED ✓"
    )

    print()
    print(
        "=" * 88
    )

    print(
        "DEMAND BASELINE EVALUATION PASSED ✓"
    )

    print(
        "=" * 88
    )


if __name__ == "__main__":
    main()