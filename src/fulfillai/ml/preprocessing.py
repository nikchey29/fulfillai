"""
Shared preprocessing utilities for FulfillAI machine-learning models.

The preprocessing pipeline is fitted only on training data.

Responsibilities
----------------
- distinguish numeric and categorical predictors
- median-impute numeric features
- fill missing categorical values
- standardize numeric features
- one-hot encode categoricals safely
- preserve deterministic feature construction
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import (
    OneHotEncoder,
    StandardScaler,
)


# ======================================================================
# Exceptions
# ======================================================================


class PreprocessingError(RuntimeError):
    """Raised when a feature matrix cannot be safely preprocessed."""


# ======================================================================
# Schema
# ======================================================================


@dataclass(frozen=True)
class FeatureSchema:
    """Predictor type contract for one ML dataset."""

    numeric_columns: tuple[str, ...]

    categorical_columns: tuple[str, ...]

    @property
    def feature_count(self) -> int:
        return (
            len(self.numeric_columns)
            + len(self.categorical_columns)
        )


# ======================================================================
# Schema detection
# ======================================================================


def infer_feature_schema(
    frame: pd.DataFrame,
) -> FeatureSchema:
    """
    Infer numeric and categorical predictors from training data.

    IMPORTANT:
    This function should be run against X_train only.
    """

    if frame.empty:
        raise PreprocessingError(
            "Cannot infer schema from an empty feature matrix."
        )

    if frame.columns.duplicated().any():
        duplicates = (
            frame.columns[
                frame.columns.duplicated()
            ]
            .tolist()
        )

        raise PreprocessingError(
            f"Duplicate predictor columns detected: {duplicates}"
        )

    numeric_columns: list[str] = []
    categorical_columns: list[str] = []

    for column in frame.columns:

        series = frame[column]

        if pd.api.types.is_numeric_dtype(series):
            numeric_columns.append(column)

        elif (
            pd.api.types.is_datetime64_any_dtype(series)
        ):
            raise PreprocessingError(
                f"Datetime predictor {column!r} reached the model "
                "without explicit feature engineering."
            )

        else:
            categorical_columns.append(column)

    if (
        len(numeric_columns)
        + len(categorical_columns)
        != len(frame.columns)
    ):
        raise PreprocessingError(
            "Feature schema does not account for all predictors."
        )

    return FeatureSchema(
        numeric_columns=tuple(
            numeric_columns
        ),
        categorical_columns=tuple(
            categorical_columns
        ),
    )


# ======================================================================
# Preprocessor
# ======================================================================


def build_preprocessor(
    schema: FeatureSchema,
) -> ColumnTransformer:
    """
    Construct the sklearn preprocessing graph.

    Numeric pipeline
    ----------------
    median imputation
        ↓
    standard scaling

    Categorical pipeline
    --------------------
    most-frequent imputation
        ↓
    one-hot encoding
    """

    transformers = []

    if schema.numeric_columns:

        numeric_pipeline = Pipeline(
            steps=[
                (
                    "imputer",
                    SimpleImputer(
                        strategy="median",
                    ),
                ),
                (
                    "scaler",
                    StandardScaler(
                        with_mean=False,
                    ),
                ),
            ]
        )

        transformers.append(
            (
                "numeric",
                numeric_pipeline,
                list(
                    schema.numeric_columns
                ),
            )
        )

    if schema.categorical_columns:

        categorical_pipeline = Pipeline(
            steps=[
                (
                    "imputer",
                    SimpleImputer(
                        strategy="most_frequent",
                    ),
                ),
                (
                    "encoder",
                    OneHotEncoder(
                        handle_unknown="ignore",
                        sparse_output=True,
                    ),
                ),
            ]
        )

        transformers.append(
            (
                "categorical",
                categorical_pipeline,
                list(
                    schema.categorical_columns
                ),
            )
        )

    if not transformers:
        raise PreprocessingError(
            "No usable predictor columns were found."
        )

    return ColumnTransformer(
        transformers=transformers,
        remainder="drop",
        sparse_threshold=1.0,
        verbose_feature_names_out=True,
    )


# ======================================================================
# Diagnostics
# ======================================================================


def print_feature_schema(
    schema: FeatureSchema,
) -> None:
    """Print the inferred training feature schema."""

    print()
    print(
        "FEATURE PREPROCESSING CONTRACT"
    )

    print(
        "=" * 78
    )

    print(
        f"numeric predictors     : "
        f"{len(schema.numeric_columns):,}"
    )

    print(
        f"categorical predictors : "
        f"{len(schema.categorical_columns):,}"
    )

    print(
        f"total predictors       : "
        f"{schema.feature_count:,}"
    )

    if schema.numeric_columns:

        print()
        print(
            "numeric:"
        )

        for column in schema.numeric_columns:

            print(
                f"  - {column}"
            )

    if schema.categorical_columns:

        print()
        print(
            "categorical:"
        )

        for column in schema.categorical_columns:

            print(
                f"  - {column}"
            )