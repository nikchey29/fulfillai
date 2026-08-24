"""Delivery V2 final refit on TRAIN + VALIDATION after source freeze."""
from src.fulfillai.ml.modeling.common_binary import final_refit_task, require_clean_git

TASKS = ("late_delivery", "delivery_exception")
VALIDATION_PHASE = "9V2.1-9V2.3"
FINAL_PHASE = "9V2.4"
GROUP = "delivery_v2"


def main() -> None:
    commit = require_clean_git()
    print("FULFILLAI DELIVERY V2 — FINAL REFIT")
    print(f"SOURCE COMMIT: {commit}")
    print("TRAIN + VALIDATION ONLY | V2 TEST LOCKED 🔒")
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
    print("DELIVERY V2 FINAL REFIT COMPLETE ✓")
    print("V2 TEST remains locked until explicit one-time evaluation.")


if __name__ == "__main__":
    main()
