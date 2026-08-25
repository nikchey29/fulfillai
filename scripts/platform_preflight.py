"""Data-free validation for FulfillAI's platform expansion."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = [
    "requirements-platform.txt",
    "results/frozen_metrics_v1.0.0.json",
    "src/fulfillai/api/main.py",
    "src/fulfillai/mlops/mlflow_tracking.py",
    "src/fulfillai/streaming/producer.py",
    "src/fulfillai/streaming/spark_pipeline.py",
    "dbt/dbt_project.yml",
    "dbt/models/marts/fct_fulfillment.sql",
    "docker/Dockerfile.api",
    "infra/azure/main.bicep",
    ".github/workflows/ci.yml",
]

missing = [rel for rel in REQUIRED if not (ROOT / rel).exists()]
if missing:
    raise SystemExit(f"Missing platform files: {missing}")
manifest = json.loads((ROOT / "results/frozen_metrics_v1.0.0.json").read_text())
assert manifest["post_test_tuning_allowed"] is False
assert manifest["delivery_v2"]["late_delivery"]["pr_auc"] == 0.303115
assert manifest["demand_forecasting"]["relative_wape_improvement_pct"] == 21.14
print("PASS FulfillAI platform source preflight")
print("PASS frozen result manifest integrity")
print("NOTE no model training, PostgreSQL access, or test-partition access occurred")
