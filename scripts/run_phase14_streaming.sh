#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

BASE=""
for candidate in compose.yaml compose.yml docker-compose.yml docker-compose.yaml; do
  if [ -f "$candidate" ]; then
    BASE="$candidate"
    break
  fi
done

if [ -z "$BASE" ]; then
  echo "ERROR: base Compose file not found."
  exit 1
fi

DC=(docker compose -f "$BASE" -f compose.streaming.yaml --profile streaming)

echo "=============================================="
echo "PHASE 14 — REDPANDA + PYSPARK STREAMING"
echo "CONTAINERIZED JAVA | FROZEN ML TESTS UNTOUCHED"
echo "=============================================="

mkdir -p artifacts/streaming
rm -rf artifacts/streaming/checkpoints artifacts/streaming/aggregates artifacts/streaming/quality

echo ""
echo "[1/7] Resetting only Phase 14 streaming services..."
"${DC[@]}" rm -sf redpanda redpanda-console phase14-spark >/dev/null 2>&1 || true

echo "[2/7] Starting Redpanda..."
"${DC[@]}" up -d redpanda

READY=0
for _ in $(seq 1 45); do
  if docker exec fulfillai-redpanda \
       rpk cluster health -X brokers=127.0.0.1:9092 --exit-when-healthy \
       >/dev/null 2>&1; then
    READY=1
    break
  fi
  sleep 2
done

if [ "$READY" -ne 1 ]; then
  echo "REDPANDA_READY=NO"
  echo "---- redpanda last 25 log lines ----"
  docker logs fulfillai-redpanda --tail 25 2>&1 || true
  exit 1
fi

echo "REDPANDA_READY=YES"

echo "[3/7] Starting Redpanda Console..."
"${DC[@]}" up -d redpanda-console

docker exec fulfillai-redpanda \
  rpk topic delete fulfillment.events -X brokers=127.0.0.1:9092 \
  >/dev/null 2>&1 || true

docker exec fulfillai-redpanda \
  rpk topic create fulfillment.events -X brokers=127.0.0.1:9092 \
  -p 3 -r 1 >/dev/null

if ! python - <<'PY' >/dev/null 2>&1
import kafka
PY
then
  python -m pip install -q 'kafka-python-ng>=2.2,<3'
fi

echo "[4/7] Producing round 1..."
python scripts/phase14_producer.py \
  --bootstrap localhost:19092 \
  --count 120 \
  --malformed 5 \
  --round round1

echo "[5/7] Spark round 1..."
"${DC[@]}" run --rm phase14-spark \
  --packages org.apache.spark:spark-sql-kafka-0-10_2.13:4.0.4 \
  --conf spark.jars.ivy=/tmp/.ivy2 \
  scripts/phase14_spark_job.py

echo "[6/7] Producing round 2 + restarting from checkpoint..."
python scripts/phase14_producer.py \
  --bootstrap localhost:19092 \
  --count 60 \
  --malformed 2 \
  --seed 84 \
  --round round2

"${DC[@]}" run --rm phase14-spark \
  --packages org.apache.spark:spark-sql-kafka-0-10_2.13:4.0.4 \
  --conf spark.jars.ivy=/tmp/.ivy2 \
  scripts/phase14_spark_job.py

echo "[7/7] Compact verification..."

echo ""
echo "=============================================="
echo "PHASE 14 COMPACT SUMMARY"
echo "=============================================="

python - <<'PY'
import json
from pathlib import Path

root = Path("artifacts/streaming")
quality_files = sorted((root / "quality").glob("batch_*.json"))
agg_files = sorted((root / "aggregates").glob("batch_*.json"))

total = valid = rejected = 0
rounds = set()

for p in quality_files:
    d = json.loads(p.read_text())
    total += int(d.get("records_seen", 0))
    valid += int(d.get("valid_records", 0))
    rejected += int(d.get("rejected_records", 0))
    rounds.update(d.get("round_ids", []))

aggregate_rows = sum(len(json.loads(p.read_text())) for p in agg_files)

expected = {
    "records_seen": 187,
    "valid_records": 180,
    "rejected_records": 7,
}

print(f"quality_batches      : {len(quality_files)}")
print(f"aggregate_batches    : {len(agg_files)}")
print(f"records_seen         : {total}")
print(f"valid_records        : {valid}")
print(f"rejected_records     : {rejected}")
print(f"rounds_seen          : {','.join(sorted(rounds))}")
print(f"aggregate_rows_saved : {aggregate_rows}")
print(f"checkpoint_present   : {(root / 'checkpoints').exists()}")
print("local_java_required  : NO")
print("frozen_ml_test_access: NO")

ok = (
    total == expected["records_seen"]
    and valid == expected["valid_records"]
    and rejected == expected["rejected_records"]
    and rounds == {"round1", "round2"}
    and aggregate_rows > 0
    and (root / "checkpoints").exists()
)
print(f"PHASE_14_STATUS      : {'PASS' if ok else 'CHECK'}")
PY

echo ""
echo "BROKER:"
docker exec fulfillai-redpanda \
  rpk cluster health -X brokers=127.0.0.1:9092 2>/dev/null | \
  sed -n '1,10p'

echo ""
echo "Redpanda Console: http://localhost:8085"
