"""Log FulfillAI's frozen evaluation record to MLflow without retraining models."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MANIFEST = PROJECT_ROOT / "results" / "frozen_metrics_v1.0.0.json"


def _flatten_metrics(prefix: str, value: Any) -> dict[str, float]:
    metrics: dict[str, float] = {}
    if isinstance(value, dict):
        for key, item in value.items():
            next_prefix = f"{prefix}.{key}" if prefix else str(key)
            metrics.update(_flatten_metrics(next_prefix, item))
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        metrics[prefix] = float(value)
    return metrics


def log_frozen_results(manifest_path: Path = DEFAULT_MANIFEST) -> str:
    """Create one MLflow run containing the immutable public benchmark metrics."""
    try:
        import mlflow
    except ImportError as exc:  # pragma: no cover - dependency is optional
        raise RuntimeError(
            "MLflow is not installed. Run: pip install -r requirements-platform.txt"
        ) from exc

    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    tracking_uri = os.getenv("MLFLOW_TRACKING_URI", "http://127.0.0.1:5001")
    experiment = os.getenv("MLFLOW_EXPERIMENT_NAME", "FulfillAI-Frozen-Benchmarks-v2")
    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment(experiment)

    with mlflow.start_run(run_name="v1.0.0-frozen-results") as run:
        mlflow.set_tags(
            {
                "project": "FulfillAI",
                "benchmark_version": "v1.0.0",
                "data_scope": payload["data_scope"],
                "post_test_tuning_allowed": "false",
                "purpose": "immutable result provenance; no retraining",
            }
        )
        for name, metric in _flatten_metrics("", payload).items():
            # MLflow metric names are easier to scan without spaces.
            mlflow.log_metric(name.replace(" ", "_"), metric)
        mlflow.log_artifact(str(manifest_path), artifact_path="evidence")
        return run.info.run_id


def main() -> None:
    run_id = log_frozen_results()
    print(f"MLflow frozen-results run created: {run_id}")
    print("No training and no test-partition access occurred.")


if __name__ == "__main__":
    main()
