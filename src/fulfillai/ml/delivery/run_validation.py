"""Phase 9 — fast delivery model validation and selection."""
from src.fulfillai.ml.config import get_task_config
from src.fulfillai.ml.modeling.common_binary import (
    BinaryWorkflowError,
    print_validation_result,
    validate_task,
)

TASKS = ("late_delivery", "delivery_exception")
PHASE = "9.1-9.3"
GROUP = "delivery"


def _require_phase_90_contract() -> None:
    late = get_task_config("late_delivery")
    exc = get_task_config("delivery_exception")
    if getattr(late, "eligibility_column", None) != "is_delivered":
        raise BinaryWorkflowError(
            "Phase 9.0 contract missing: late_delivery must use eligibility_column='is_delivered'."
        )
    if getattr(exc, "eligibility_column", None) is not None:
        raise BinaryWorkflowError(
            "Phase 9.0 contract invalid: delivery_exception must keep all dispatched rows."
        )


def main() -> None:
    print("FULFILLAI PHASE 9 — DELIVERY VALIDATION")
    print("TRAIN + VALIDATION ONLY | TEST LOCKED 🔒")
    _require_phase_90_contract()
    results = {}
    for task_name in TASKS:
        result = validate_task(task_name, phase=PHASE, group=GROUP)
        results[task_name] = result
        print_validation_result(result)

    for split_name in ("train", "validation"):
        late_pop = results["late_delivery"]["population"]
        exc_pop = results["delivery_exception"]["population"]
        raw = late_pop[f"{split_name}_raw_rows"]
        eligible = late_pop[f"{split_name}_eligible_rows"]
        excluded = int(raw) - int(eligible)
        exception_positive = int(exc_pop[f"{split_name}_positive_rows"])
        if excluded != exception_positive:
            raise BinaryWorkflowError(
                f"Phase 9.0 reconciliation failed for {split_name}: "
                f"late excluded={excluded:,}, exception positives={exception_positive:,}."
            )

    print("\nPHASE 9.0 POPULATION RECONCILIATION PASSED ✓")
    print("PHASE 9 VALIDATION COMPLETE ✓")
    print("Next: final refit. TEST remains locked.")


if __name__ == "__main__":
    main()
