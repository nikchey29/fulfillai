"""Phase 10.4 — final inventory refit on TRAIN + VALIDATION."""
from src.fulfillai.ml.modeling.common_binary import final_refit_task, require_clean_git

TASKS = ("stockout_risk", "reorder_breach_risk")
VALIDATION_PHASE = "10.1-10.3"
FINAL_PHASE = "10.4"
GROUP = "inventory"


def main() -> None:
    commit = require_clean_git()
    print("FULFILLAI PHASE 10.4 — INVENTORY FINAL REFIT")
    print(f"SOURCE COMMIT: {commit}")
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
    print("PHASE 10.4 FINAL REFIT COMPLETE ✓")
    print("Commit/freeze this state before one-time TEST evaluation.")


if __name__ == "__main__":
    main()
