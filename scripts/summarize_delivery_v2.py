from __future__ import annotations

import json
from pathlib import Path

ROOT = Path.cwd()
METRICS = ROOT / "artifacts" / "metrics" / "delivery_v2"
TASKS = ("late_delivery", "delivery_exception")
VAL_PHASE = "9V2_1-9V2_3"
TEST_PHASE = "9V2_5"

print("\n" + "=" * 84)
print("DELIVERY V2 COMPACT SUMMARY")
print("=" * 84)

for task in TASKS:
    val_path = METRICS / f"{task}_{VAL_PHASE}_validation.json"
    if not val_path.exists():
        print(f"{task:<20} validation artifact missing")
        continue
    val = json.loads(val_path.read_text())
    prevalence = float(val["population"]["validation_positive_rate"])
    metrics = val["winner_metrics_at_frozen_threshold"]
    print(
        f"{task:<20} VAL PR-AUC={metrics['pr_auc']:.6f} "
        f"baseline={prevalence:.6f} lift={metrics['pr_auc']/max(prevalence,1e-12):.2f}x "
        f"winner={val['winner']} threshold={val['validation_threshold']:.4f}"
    )

print()
for task in TASKS:
    test_path = METRICS / f"{task}_{TEST_PHASE}_test.json"
    if not test_path.exists():
        print(f"{task:<20} TEST LOCKED / NOT EVALUATED")
        continue
    test = json.loads(test_path.read_text())
    m = test["metrics"]
    prevalence = test["test_positive_rows"] / max(test["test_rows"], 1)
    print(
        f"{task:<20} TEST PR-AUC={m['pr_auc']:.6f} "
        f"baseline={prevalence:.6f} lift={m['pr_auc']/max(prevalence,1e-12):.2f}x "
        f"ROC-AUC={m['roc_auc']:.6f} F1={m['f1']:.6f}"
    )
