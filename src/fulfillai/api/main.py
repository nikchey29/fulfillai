"""FastAPI service for FulfillAI model metadata, frozen metrics, and inference.

The API never trains or tunes models. It loads already-frozen local artifacts.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import joblib
import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

PROJECT_ROOT = Path(__file__).resolve().parents[3]
MANIFEST_PATH = PROJECT_ROOT / "results" / "frozen_metrics_v1.0.0.json"
ARTIFACT_ROOT = PROJECT_ROOT / "artifacts" / "models"

TaskName = Literal[
    "demand_forecasting",
    "late_delivery",
    "delivery_exception",
    "stockout_risk",
    "reorder_breach_risk",
]

ARTIFACTS: dict[str, Path] = {
    "demand_forecasting": ARTIFACT_ROOT / "demand" / "hurdle_phase_8_15_final.joblib",
    "late_delivery": ARTIFACT_ROOT / "delivery_v2" / "late_delivery_9V2_4_final.joblib",
    "delivery_exception": ARTIFACT_ROOT / "delivery_v2" / "delivery_exception_9V2_4_final.joblib",
    "stockout_risk": ARTIFACT_ROOT / "inventory" / "stockout_risk_10_4_final.joblib",
    "reorder_breach_risk": ARTIFACT_ROOT / "inventory" / "reorder_breach_risk_10_4_final.joblib",
}


class PredictionRequest(BaseModel):
    records: list[dict[str, Any]] = Field(min_length=1, max_length=1000)


class PredictionResponse(BaseModel):
    task: str
    model: str
    threshold: float | None
    predictions: list[dict[str, Any]]


@lru_cache(maxsize=1)
def frozen_manifest() -> dict[str, Any]:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=8)
def load_artifact(task: str) -> dict[str, Any]:
    path = ARTIFACTS[task]
    if not path.exists():
        raise FileNotFoundError(path)
    artifact = joblib.load(path)
    if not isinstance(artifact, dict):
        raise RuntimeError(f"Unexpected model artifact type for {task}: {type(artifact)!r}")
    return artifact


def _require_columns(frame: pd.DataFrame, expected: list[str]) -> pd.DataFrame:
    missing = [column for column in expected if column not in frame.columns]
    if missing:
        raise HTTPException(
            status_code=422,
            detail={"message": "Missing model features", "missing": missing},
        )
    return frame.loc[:, expected].copy()


def _predict_binary(task: str, artifact: dict[str, Any], frame: pd.DataFrame) -> PredictionResponse:
    expected = list(artifact["feature_columns"])
    frame = _require_columns(frame, expected)
    encoded = artifact["preprocessor"].transform(frame)
    probability = np.asarray(artifact["model"].predict_proba(encoded)[:, 1], dtype=float)
    threshold = float(artifact["threshold"])
    predicted = (probability >= threshold).astype(int)
    rows = [
        {"probability": float(p), "prediction": int(y)}
        for p, y in zip(probability, predicted, strict=True)
    ]
    return PredictionResponse(
        task=task,
        model=str(artifact.get("model_name", type(artifact["model"]).__name__)),
        threshold=threshold,
        predictions=rows,
    )


def _predict_demand(artifact: dict[str, Any], frame: pd.DataFrame) -> PredictionResponse:
    expected = list(artifact["safe_predictors"])
    frame = _require_columns(frame, expected)
    encoded = artifact["preprocessor"].transform(frame)
    probability = np.asarray(
        artifact["occurrence_model"].predict_proba(encoded)[:, 1], dtype=float
    )
    magnitude = np.maximum(
        np.asarray(artifact["magnitude_model"].predict(encoded), dtype=float), 0.0
    )
    threshold = float(artifact["threshold"])
    demand = np.where(probability >= threshold, magnitude, 0.0)
    rows = [
        {
            "positive_demand_probability": float(p),
            "positive_magnitude_prediction": float(m),
            "units_sold_prediction": float(y),
        }
        for p, m, y in zip(probability, magnitude, demand, strict=True)
    ]
    return PredictionResponse(
        task="demand_forecasting",
        model="hard_gated_hurdle",
        threshold=threshold,
        predictions=rows,
    )


app = FastAPI(
    title="FulfillAI Model API",
    version="1.1.0",
    description=(
        "Inference and observability surface for frozen FulfillAI models. "
        "This service performs no training, tuning, or test evaluation."
    ),
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "fulfillai-api", "version": "1.1.0"}


@app.get("/v1/results")
def results() -> dict[str, Any]:
    return frozen_manifest()


@app.get("/v1/models")
def models() -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for task, path in ARTIFACTS.items():
        item: dict[str, Any] = {"artifact": str(path.relative_to(PROJECT_ROOT)), "available": path.exists()}
        if path.exists():
            artifact = load_artifact(task)
            feature_key = "safe_predictors" if task == "demand_forecasting" else "feature_columns"
            item["features"] = list(artifact.get(feature_key, []))
            item["threshold"] = float(artifact.get("threshold", 0.0))
        payload[task] = item
    return payload


@app.post("/v1/predict/{task}", response_model=PredictionResponse)
def predict(task: TaskName, request: PredictionRequest) -> PredictionResponse:
    path = ARTIFACTS[task]
    if not path.exists():
        raise HTTPException(
            status_code=503,
            detail=(
                f"Frozen artifact is not mounted at {path.relative_to(PROJECT_ROOT)}. "
                "Run this API from the completed local project or mount artifacts/ into the container."
            ),
        )
    frame = pd.DataFrame(request.records)
    artifact = load_artifact(task)
    if task == "demand_forecasting":
        return _predict_demand(artifact, frame)
    return _predict_binary(task, artifact, frame)
