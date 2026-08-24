"""Phase 11 — summarize all configured FulfillAI ML work after Phase 8.

This module never trains models and never reads Parquet data. It only reads
already-produced JSON metric artifacts and writes a compact project summary.
"""
from __future__ import annotations

import json
from pathlib import Path

from src.fulfillai.ml.config import METRIC_ROOT

TASK_ARTIFACTS = {
    "late_delivery": {
        "group": "delivery",
        "validation": "late_delivery_9_1-9_3_validation.json",
        "refit": "late_delivery_9_4_refit.json",
        "test": "late_delivery_9_5_test.json",
    },
    "delivery_exception": {
        "group": "delivery",
        "validation": "delivery_exception_9_1-9_3_validation.json",
        "refit": "delivery_exception_9_4_refit.json",
        "test": "delivery_exception_9_5_test.json",
    },
    "stockout_risk": {
        "group": "inventory",
        "validation": "stockout_risk_10_1-10_3_validation.json",
        "refit": "stockout_risk_10_4_refit.json",
        "test": "stockout_risk_10_5_test.json",
    },
    "reorder_breach_risk": {
        "group": "inventory",
        "validation": "reorder_breach_risk_10_1-10_3_validation.json",
        "refit": "reorder_breach_risk_10_4_refit.json",
        "test": "reorder_breach_risk_10_5_test.json",
    },
}


def _read(path: Path):
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def main() -> None:
    output = {
        "artifact_version": 1,
        "phase": "11.0",
        "purpose": "remaining ML project summary",
        "tasks": {},
    }
    lines = [
        "# FulfillAI Remaining ML Summary",
        "",
        "Phase 8 demand forecasting is treated as already completed/frozen.",
        "This report summarizes the remaining configured binary ML tasks.",
        "",
        "| Task | Validation winner | Frozen threshold | Test PR-AUC | Test ROC-AUC | Test F1 |",
        "|---|---|---:|---:|---:|---:|",
    ]

    for task_name, spec in TASK_ARTIFACTS.items():
        root = METRIC_ROOT / spec["group"]
        validation = _read(root / spec["validation"])
        refit = _read(root / spec["refit"])
        test = _read(root / spec["test"])
        status = {
            "validation_complete": validation is not None,
            "refit_complete": refit is not None,
            "test_complete": test is not None,
        }
        if validation:
            status["winner"] = validation.get("winner")
            status["threshold"] = validation.get("validation_threshold")
            status["validation_pr_auc"] = (
                validation.get("winner_metrics_at_frozen_threshold", {}).get("pr_auc")
            )
        if test:
            status["test_metrics"] = test.get("metrics", {})
        output["tasks"][task_name] = status

        winner = status.get("winner", "—")
        threshold = status.get("threshold")
        threshold_s = f"{threshold:.4f}" if isinstance(threshold, (int, float)) else "—"
        tm = status.get("test_metrics", {})
        def fmt(name):
            value = tm.get(name)
            return f"{value:.4f}" if isinstance(value, (int, float)) else "—"
        lines.append(
            f"| {task_name} | {winner} | {threshold_s} | {fmt('pr_auc')} | {fmt('roc_auc')} | {fmt('f1')} |"
        )

    complete = all(v.get("test_complete") for v in output["tasks"].values())
    output["remaining_binary_tasks_complete"] = complete
    output["post_test_model_changes_allowed"] = False if complete else None

    METRIC_ROOT.mkdir(parents=True, exist_ok=True)
    json_path = METRIC_ROOT / "final_remaining_ml_summary.json"
    md_path = METRIC_ROOT / "final_remaining_ml_summary.md"
    json_path.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines += ["", f"Remaining binary ML tasks complete: **{'YES' if complete else 'NO'}**"]
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("=" * 88)
    print("FULFILLAI PHASE 11.0 — REMAINING ML FINALIZATION")
    print("=" * 88)
    for name, status in output["tasks"].items():
        print(
            f"{name:<24} validation={'YES' if status['validation_complete'] else 'NO':<3} "
            f"refit={'YES' if status['refit_complete'] else 'NO':<3} "
            f"test={'YES' if status['test_complete'] else 'NO':<3}"
        )
    print(f"summary JSON : {json_path}")
    print(f"summary MD   : {md_path}")
    print("No Parquet/test data was opened by this summary script.")


if __name__ == "__main__":
    main()
