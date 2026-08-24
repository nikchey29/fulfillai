"""
Evaluation metrics used across FulfillAI ML tasks.

Regression / forecasting
------------------------
MAE
RMSE
WAPE
sMAPE

Binary classification
---------------------
PR-AUC
ROC-AUC
precision
recall
F1
F2
log loss
Brier score
confusion matrix

Rare-event ranking
------------------
precision@k
recall@k
lift@k
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    fbeta_score,
    log_loss,
    mean_absolute_error,
    mean_squared_error,
    precision_score,
    recall_score,
    roc_auc_score,
)


# ======================================================================
# Exceptions
# ======================================================================


class MetricError(ValueError):
    """Raised when metric inputs are invalid."""


# ======================================================================
# Utilities
# ======================================================================


def _as_1d_float(
    values,
    *,
    name: str,
) -> np.ndarray:
    """Convert input to finite 1-D float array."""

    array = np.asarray(
        values,
        dtype=float,
    )

    if array.ndim != 1:

        raise MetricError(
            f"{name} must be one-dimensional."
        )

    if len(array) == 0:

        raise MetricError(
            f"{name} cannot be empty."
        )

    if not np.isfinite(
        array
    ).all():

        raise MetricError(
            f"{name} contains NaN or "
            "infinite values."
        )

    return array


def _validate_pair(
    y_true,
    y_pred,
) -> tuple[
    np.ndarray,
    np.ndarray,
]:
    """Validate target/prediction arrays."""

    actual = _as_1d_float(
        y_true,
        name="y_true",
    )

    predicted = _as_1d_float(
        y_pred,
        name="y_pred",
    )

    if len(actual) != len(
        predicted
    ):

        raise MetricError(
            "y_true and y_pred must "
            "have the same length."
        )

    return (
        actual,
        predicted,
    )


# ======================================================================
# Forecasting metrics
# ======================================================================


def mae(
    y_true,
    y_pred,
) -> float:
    """Mean absolute error."""

    actual, predicted = (
        _validate_pair(
            y_true,
            y_pred,
        )
    )

    return float(
        mean_absolute_error(
            actual,
            predicted,
        )
    )


def rmse(
    y_true,
    y_pred,
) -> float:
    """Root mean squared error."""

    actual, predicted = (
        _validate_pair(
            y_true,
            y_pred,
        )
    )

    return float(
        math.sqrt(
            mean_squared_error(
                actual,
                predicted,
            )
        )
    )


def wape(
    y_true,
    y_pred,
) -> float:
    """
    Weighted absolute percentage error.

    Returned as a percentage.

    WAPE =
        sum(abs(actual - prediction))
        -------------------------------- * 100
              sum(abs(actual))
    """

    actual, predicted = (
        _validate_pair(
            y_true,
            y_pred,
        )
    )

    denominator = float(
        np.abs(
            actual
        ).sum()
    )

    if denominator == 0:

        return float(
            "nan"
        )

    numerator = float(
        np.abs(
            actual
            - predicted
        ).sum()
    )

    return (
        numerator
        / denominator
        * 100.0
    )


def smape(
    y_true,
    y_pred,
) -> float:
    """
    Symmetric mean absolute percentage error.

    Zero/zero observations contribute zero rather than producing NaN.

    Returned as a percentage.
    """

    actual, predicted = (
        _validate_pair(
            y_true,
            y_pred,
        )
    )

    denominator = (
        np.abs(actual)
        + np.abs(predicted)
    )

    numerator = (
        2.0
        * np.abs(
            predicted
            - actual
        )
    )

    terms = np.divide(
        numerator,
        denominator,
        out=np.zeros_like(
            numerator,
            dtype=float,
        ),
        where=(
            denominator
            != 0
        ),
    )

    return float(
        np.mean(
            terms
        )
        * 100.0
    )


def forecasting_metrics(
    y_true,
    y_pred,
) -> dict[str, float]:
    """
    Calculate the standard FulfillAI forecasting metric suite.
    """

    return {
        "mae": mae(
            y_true,
            y_pred,
        ),

        "rmse": rmse(
            y_true,
            y_pred,
        ),

        "wape": wape(
            y_true,
            y_pred,
        ),

        "smape": smape(
            y_true,
            y_pred,
        ),
    }


# ======================================================================
# Binary-classification helpers
# ======================================================================


def _validate_binary_targets(
    y_true,
) -> np.ndarray:
    """Validate binary labels."""

    target = _as_1d_float(
        y_true,
        name="y_true",
    )

    unique = set(
        np.unique(
            target
        ).tolist()
    )

    if not unique.issubset(
        {0.0, 1.0}
    ):

        raise MetricError(
            "Binary targets must contain "
            "only 0 and 1."
        )

    return target.astype(
        int
    )


def _validate_probabilities(
    probabilities,
    *,
    expected_length: int,
) -> np.ndarray:
    """Validate predicted positive-class probabilities."""

    probability = _as_1d_float(
        probabilities,
        name="y_probability",
    )

    if len(
        probability
    ) != expected_length:

        raise MetricError(
            "Target and probability arrays "
            "must have the same length."
        )

    if (
        (probability < 0)
        | (probability > 1)
    ).any():

        raise MetricError(
            "Predicted probabilities must "
            "lie between 0 and 1."
        )

    return probability


def labels_from_probability(
    probabilities,
    *,
    threshold: float = 0.5,
) -> np.ndarray:
    """Convert positive-class probabilities to binary predictions."""

    if not (
        0.0
        <= threshold
        <= 1.0
    ):

        raise MetricError(
            "threshold must lie "
            "between 0 and 1."
        )

    probability = _as_1d_float(
        probabilities,
        name="probabilities",
    )

    return (
        probability
        >= threshold
    ).astype(
        int
    )


# ======================================================================
# Ranking metrics
# ======================================================================


@dataclass(frozen=True)
class RankingMetrics:
    """Top-k rare-event ranking metrics."""

    k_fraction: float

    k_rows: int

    positives_total: int

    positives_at_k: int

    precision_at_k: float

    recall_at_k: float

    lift_at_k: float


def ranking_metrics_at_k(
    y_true,
    scores,
    *,
    k_fraction: float = 0.01,
) -> RankingMetrics:
    """
    Calculate precision, recall and lift in the highest-scored fraction.

    Example:
        k_fraction=0.01 evaluates the highest-risk 1% of observations.
    """

    if not (
        0.0
        < k_fraction
        <= 1.0
    ):

        raise MetricError(
            "k_fraction must be in "
            "(0, 1]."
        )

    target = (
        _validate_binary_targets(
            y_true
        )
    )

    score = _as_1d_float(
        scores,
        name="scores",
    )

    if len(target) != len(
        score
    ):

        raise MetricError(
            "Target and score arrays "
            "must have equal lengths."
        )

    rows = len(
        target
    )

    k_rows = max(
        1,
        int(
            math.ceil(
                rows
                * k_fraction
            )
        ),
    )

    order = np.argsort(
        -score,
        kind="stable",
    )

    selected = target[
        order[:k_rows]
    ]

    positives_total = int(
        target.sum()
    )

    positives_at_k = int(
        selected.sum()
    )

    precision_at_k = (
        positives_at_k
        / k_rows
    )

    if positives_total:

        recall_at_k = (
            positives_at_k
            / positives_total
        )

    else:

        recall_at_k = float(
            "nan"
        )

    prevalence = float(
        target.mean()
    )

    if prevalence > 0:

        lift_at_k = (
            precision_at_k
            / prevalence
        )

    else:

        lift_at_k = float(
            "nan"
        )

    return RankingMetrics(
        k_fraction=k_fraction,
        k_rows=k_rows,
        positives_total=(
            positives_total
        ),
        positives_at_k=(
            positives_at_k
        ),
        precision_at_k=float(
            precision_at_k
        ),
        recall_at_k=float(
            recall_at_k
        ),
        lift_at_k=float(
            lift_at_k
        ),
    )


# ======================================================================
# Classification metrics
# ======================================================================


def binary_classification_metrics(
    y_true,
    y_probability,
    *,
    threshold: float = 0.5,
    k_fraction: float = 0.01,
) -> dict[str, float | int]:
    """
    Calculate FulfillAI binary classification metrics.
    """

    target = (
        _validate_binary_targets(
            y_true
        )
    )

    probability = (
        _validate_probabilities(
            y_probability,
            expected_length=len(
                target
            ),
        )
    )

    prediction = (
        labels_from_probability(
            probability,
            threshold=threshold,
        )
    )

    unique_classes = np.unique(
        target
    )

    if len(
        unique_classes
    ) == 2:

        roc_auc = float(
            roc_auc_score(
                target,
                probability,
            )
        )

        pr_auc = float(
            average_precision_score(
                target,
                probability,
            )
        )

    else:

        roc_auc = float(
            "nan"
        )

        pr_auc = float(
            "nan"
        )

    tn, fp, fn, tp = (
        confusion_matrix(
            target,
            prediction,
            labels=[
                0,
                1,
            ],
        )
        .ravel()
    )

    ranking = (
        ranking_metrics_at_k(
            target,
            probability,
            k_fraction=k_fraction,
        )
    )

    return {
        "threshold": float(
            threshold
        ),

        "prevalence": float(
            target.mean()
        ),

        "positive_count": int(
            target.sum()
        ),

        "negative_count": int(
            len(target)
            - target.sum()
        ),

        "pr_auc": pr_auc,

        "roc_auc": roc_auc,

        "precision": float(
            precision_score(
                target,
                prediction,
                zero_division=0,
            )
        ),

        "recall": float(
            recall_score(
                target,
                prediction,
                zero_division=0,
            )
        ),

        "f1": float(
            f1_score(
                target,
                prediction,
                zero_division=0,
            )
        ),

        "f2": float(
            fbeta_score(
                target,
                prediction,
                beta=2.0,
                zero_division=0,
            )
        ),

        "log_loss": float(
            log_loss(
                target,
                probability,
                labels=[
                    0,
                    1,
                ],
            )
        ),

        "brier_score": float(
            brier_score_loss(
                target,
                probability,
            )
        ),

        "true_negatives": int(
            tn
        ),

        "false_positives": int(
            fp
        ),

        "false_negatives": int(
            fn
        ),

        "true_positives": int(
            tp
        ),

        "k_fraction": float(
            ranking.k_fraction
        ),

        "k_rows": int(
            ranking.k_rows
        ),

        "precision_at_k": float(
            ranking.precision_at_k
        ),

        "recall_at_k": float(
            ranking.recall_at_k
        ),

        "lift_at_k": float(
            ranking.lift_at_k
        ),
    }


# ======================================================================
# Validation-threshold search
# ======================================================================


def find_best_threshold(
    y_true,
    y_probability,
    *,
    metric: str = "f1",
    minimum_threshold: float = 0.01,
    maximum_threshold: float = 0.99,
    steps: int = 99,
) -> tuple[
    float,
    float,
]:
    """
    Search validation probabilities for the best F1 or F2 threshold.

    IMPORTANT:
    This function should be used only on validation data.
    Test data must never be used to choose a threshold.
    """

    if metric not in {
        "f1",
        "f2",
    }:

        raise MetricError(
            "Threshold search supports "
            "only 'f1' and 'f2'."
        )

    if steps < 2:

        raise MetricError(
            "steps must be at least 2."
        )

    target = (
        _validate_binary_targets(
            y_true
        )
    )

    probability = (
        _validate_probabilities(
            y_probability,
            expected_length=len(
                target
            ),
        )
    )

    thresholds = np.linspace(
        minimum_threshold,
        maximum_threshold,
        steps,
    )

    best_threshold = 0.5
    best_score = -1.0

    for threshold in thresholds:

        prediction = (
            probability
            >= threshold
        ).astype(
            int
        )

        if metric == "f1":

            score = f1_score(
                target,
                prediction,
                zero_division=0,
            )

        else:

            score = fbeta_score(
                target,
                prediction,
                beta=2.0,
                zero_division=0,
            )

        if score > best_score:

            best_score = float(
                score
            )

            best_threshold = float(
                threshold
            )

    return (
        best_threshold,
        best_score,
    )


# ======================================================================
# CLI smoke test
# ======================================================================


def main() -> None:
    """Run deterministic metric smoke tests."""

    actual_regression = np.array(
        [
            0,
            1,
            2,
            4,
            0,
        ],
        dtype=float,
    )

    predicted_regression = np.array(
        [
            0,
            1,
            1,
            5,
            0,
        ],
        dtype=float,
    )

    regression = forecasting_metrics(
        actual_regression,
        predicted_regression,
    )

    print(
        "Forecasting metric smoke test"
    )

    print(
        "=" * 72
    )

    for name, value in regression.items():

        print(
            f"{name:<12}: "
            f"{value:.6f}"
        )

    actual_classification = np.array(
        [
            0,
            0,
            1,
            0,
            1,
            0,
            1,
            0,
        ]
    )

    probabilities = np.array(
        [
            0.05,
            0.10,
            0.90,
            0.20,
            0.80,
            0.30,
            0.70,
            0.15,
        ]
    )

    classification = (
        binary_classification_metrics(
            actual_classification,
            probabilities,
            threshold=0.5,
            k_fraction=0.25,
        )
    )

    print()
    print(
        "Classification metric smoke test"
    )

    print(
        "=" * 72
    )

    for name in (
        "pr_auc",
        "roc_auc",
        "precision",
        "recall",
        "f1",
        "f2",
        "brier_score",
        "precision_at_k",
        "recall_at_k",
        "lift_at_k",
    ):

        value = classification[
            name
        ]

        print(
            f"{name:<18}: "
            f"{value:.6f}"
        )

    print()
    print(
        "METRIC SMOKE TESTS PASSED ✓"
    )


if __name__ == "__main__":
    main()