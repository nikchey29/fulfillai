"""Delivery V2 one-time TEST evaluation of frozen models."""
import argparse
from src.fulfillai.ml.modeling.common_binary import (
    evaluate_frozen_test_task,
    print_test_result,
    require_clean_git,
)

TASKS = ("late_delivery", "delivery_exception")
FINAL_PHASE = "9V2.4"
TEST_PHASE = "9V2.5"
GROUP = "delivery_v2"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--confirm-one-time-test",
        action="store_true",
        help="Acknowledge that the Delivery V2 TEST will be opened exactly once.",
    )
    args = parser.parse_args()
    if not args.confirm_one_time_test:
        raise SystemExit(
            "V2 TEST remains locked. Add --confirm-one-time-test only after source is frozen."
        )

    commit = require_clean_git()
    for task_name in TASKS:
        result = evaluate_frozen_test_task(
            task_name,
            final_phase=FINAL_PHASE,
            test_phase=TEST_PHASE,
            group=GROUP,
            confirm_one_time_test=True,
            source_commit=commit,
        )
        print_test_result(result)

    print("\nDELIVERY V2 TEST COMPLETE ✓")
    print("No post-test V2 model changes are allowed.")


if __name__ == "__main__":
    main()
