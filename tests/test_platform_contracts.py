import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_frozen_result_manifest_is_immutable_and_matches_public_results():
    manifest = json.loads((ROOT / "results/frozen_metrics_v1.0.0.json").read_text())
    assert manifest["post_test_tuning_allowed"] is False
    assert manifest["demand_forecasting"]["relative_wape_improvement_pct"] == 21.14
    assert manifest["delivery_v2"]["late_delivery"]["pr_auc"] == 0.303115
    assert manifest["delivery_v2"]["delivery_exception"]["pr_auc"] == 0.167229
    assert manifest["inventory"]["stockout_risk"]["pr_auc"] == 0.359567
    assert manifest["inventory"]["reorder_breach_risk"]["pr_auc"] == 0.998317


def test_hurdle_docs_match_hard_gated_implementation():
    docs = "\n".join(
        (ROOT / rel).read_text(encoding="utf-8")
        for rel in ["README.md", "docs/architecture.md", "docs/ml_methodology.md", "docs/results.md", "docs/build_notes.md"]
    )
    lowered = docs.lower()
    assert "full hurdle expectation" not in lowered
    assert "expected-value forecast" not in lowered
    assert "hard-gated" in lowered


def test_platform_files_are_present():
    required = [
        "pyproject.toml",
        "requirements-platform.txt",
        "src/fulfillai/api/main.py",
        "src/fulfillai/mlops/mlflow_tracking.py",
        "src/fulfillai/streaming/producer.py",
        "src/fulfillai/streaming/spark_pipeline.py",
        "dbt/dbt_project.yml",
        "docker/Dockerfile.api",
        "infra/azure/main.bicep",
        ".github/workflows/ci.yml",
        ".github/workflows/container.yml",
    ]
    assert not [rel for rel in required if not (ROOT / rel).exists()]


def test_ci_does_not_train_or_open_frozen_tests():
    text = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8").lower()
    forbidden = ["train_hurdle", "evaluate_test", "run_delivery_v2_test", "db-load", "build-features"]
    assert all(token not in text for token in forbidden)
