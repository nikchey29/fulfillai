#!/usr/bin/env bash
set -euo pipefail

cd "${1:-$(pwd)}"

if [[ ! -d src/fulfillai ]]; then
  echo "ERROR: run this from the FulfillAI repository root (or pass it as argument 1)."
  exit 1
fi

if [[ -n "$(git status --porcelain)" ]]; then
  echo "ERROR: Git working tree must be clean before the one-time V2 test."
  git status --short
  exit 1
fi

if [[ ! -f artifacts/models/delivery_v2/late_delivery_9V2_4_final.joblib ]] || \
   [[ ! -f artifacts/models/delivery_v2/delivery_exception_9V2_4_final.joblib ]]; then
  echo "ERROR: frozen Delivery V2 final models are missing. Run the pre-test workflow first."
  exit 1
fi

echo "This will open the Delivery V2 TEST partition exactly once."
echo "No model/feature/threshold changes are allowed afterward for this V2 benchmark."
printf "Type OPEN-DELIVERY-V2-TEST to continue: "
read -r answer

if [[ "$answer" != "OPEN-DELIVERY-V2-TEST" ]]; then
  echo "Cancelled. TEST remains locked."
  exit 0
fi

python -m src.fulfillai.ml.delivery_v2.evaluate_test --confirm-one-time-test
python scripts/summarize_delivery_v2.py
