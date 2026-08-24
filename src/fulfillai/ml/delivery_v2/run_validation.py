"""Delivery V2 validation and selection — TRAIN + VALIDATION only."""
from src.fulfillai.ml.config import get_task_config
from src.fulfillai.ml.modeling.common_binary import (
    BinaryWorkflowError,
    load_train_validation,
    print_validation_result,
    validate_task,
)

TASKS = ("late_delivery", "delivery_exception")
PHASE = "9V2.1-9V2.3"
GROUP = "delivery_v2"
REQUIRED_V2_FEATURES = {
    "promise_month",
    "processing_share_of_promise",
    "remaining_window_share_of_promise",
    "carrier_shipping_method",
    "warehouse_shipping_method",
}


def _require_v2_contract() -> None:
    late = get_task_config("late_delivery")
    exc = get_task_config("delivery_exception")
    if getattr(late, "eligibility_column", None) != "is_delivered":
        raise BinaryWorkflowError(
            "Delivery V2 contract missing: late_delivery must use eligibility_column='is_delivered'."
        )
    if getattr(exc, "eligibility_column", None) is not None:
        raise BinaryWorkflowError(
            "Delivery V2 contract invalid: delivery_exception must retain all dispatched shipments."
        )

    bundle = load_train_validation("delivery_exception")
    missing = sorted(REQUIRED_V2_FEATURES - set(bundle["predictors"]))
    if missing:
        raise BinaryWorkflowError(
            "Delivery V2 feature dataset was not rebuilt. Missing predictors: "
            + ", ".join(missing)
        )


def main() -> None:
    print("FULFILLAI DELIVERY V2 — VALIDATION")
    print("TRAIN + VALIDATION ONLY | V2 TEST LOCKED 🔒")
    _require_v2_contract()

    results = {}
    for task_name in TASKS:
        result = validate_task(task_name, phase=PHASE, group=GROUP)
        results[task_name] = result
        print_validation_result(result)

    for split_name in ("train", "validation"):
        late_pop = results["late_delivery"]["population"]
        exc_pop = results["delivery_exception"]["population"]
        raw = int(late_pop[f"{split_name}_raw_rows"])
        eligible = int(late_pop[f"{split_name}_eligible_rows"])
        excluded = raw - eligible
        exception_positive = int(exc_pop[f"{split_name}_positive_rows"])
        if excluded != exception_positive:
            raise BinaryWorkflowError(
                f"Population reconciliation failed for {split_name}: "
                f"late excluded={excluded:,}, exception positives={exception_positive:,}."
            )

    print("\nDELIVERY V2 POPULATION RECONCILIATION PASSED ✓")
    print("DELIVERY V2 VALIDATION COMPLETE ✓")
    print("Next: freeze source, then final refit. V2 TEST remains locked.")


if __name__ == "__main__":
    main()
