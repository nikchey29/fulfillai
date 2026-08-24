"""Phase 10 — fast inventory-risk validation and selection."""
from src.fulfillai.ml.modeling.common_binary import print_validation_result, validate_task

TASKS = ("stockout_risk", "reorder_breach_risk")
PHASE = "10.1-10.3"
GROUP = "inventory"


def main() -> None:
    print("FULFILLAI PHASE 10 — INVENTORY VALIDATION")
    print("TRAIN + VALIDATION ONLY | TEST LOCKED 🔒")
    for task_name in TASKS:
        result = validate_task(task_name, phase=PHASE, group=GROUP)
        print_validation_result(result)
    print("\nPHASE 10 VALIDATION COMPLETE ✓")
    print("Next: freeze/commit source, then final refit. TEST remains locked.")


if __name__ == "__main__":
    main()
