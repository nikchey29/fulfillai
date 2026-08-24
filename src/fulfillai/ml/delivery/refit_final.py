"""Phase 9.4 — final delivery refit on TRAIN + VALIDATION."""
from src.fulfillai.ml.modeling.common_binary import final_refit_task

TASKS = ("late_delivery", "delivery_exception")
VALIDATION_PHASE = "9.1-9.3"
FINAL_PHASE = "9.4"
GROUP = "delivery"


def main() -> None:
    print("FULFILLAI PHASE 9.4 — DELIVERY FINAL REFIT")
    print("TRAIN + VALIDATION ONLY | TEST LOCKED 🔒")
    for task_name in TASKS:
        result = final_refit_task(
            task_name,
            validation_phase=VALIDATION_PHASE,
            final_phase=FINAL_PHASE,
            group=GROUP,
        )
        print(
            f"{task_name:<22} winner={result['winner']:<20} "
            f"threshold={result['threshold']:.4f} rows={result['fit_rows']:,}"
        )
    print("PHASE 9.4 FINAL REFIT COMPLETE ✓")
    print("Commit/freeze this state before one-time TEST evaluation.")


if __name__ == "__main__":
    main()
