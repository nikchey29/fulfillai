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

PG_USER="$(docker exec fulfillai-postgres printenv POSTGRES_USER)"
PG_DB="$(docker exec fulfillai-postgres printenv POSTGRES_DB)"
PG_PASSWORD="$(docker exec fulfillai-postgres printenv POSTGRES_PASSWORD)"

if [ -z "$PG_PASSWORD" ]; then
  echo "ERROR: POSTGRES_PASSWORD was empty."
  exit 1
fi

export FULFILLAI_PG_PASSWORD="$PG_PASSWORD"

echo "================================================"
echo "PHASE 14B — STREAMING → POSTGRESQL"
echo "IDEMPOTENT UPSERT SINK | ML TESTS UNTOUCHED"
echo "================================================"

echo "[1/6] Building Spark runtime with PostgreSQL client..."
"${DC[@]}" build phase14-spark >/tmp/fulfillai_phase14b_build.log 2>&1

echo "[2/6] Resetting Phase 14 evidence only..."
rm -rf artifacts/streaming/checkpoints artifacts/streaming/aggregates artifacts/streaming/quality
mkdir -p artifacts/streaming

docker exec fulfillai-postgres sh -c "
  psql -v ON_ERROR_STOP=1 -U '$PG_USER' -d '$PG_DB' <<'SQL'
create schema if not exists streaming;
create table if not exists streaming.fulfillment_window_metrics (
    window_start timestamptz not null,
    window_end timestamptz not null,
    warehouse_id integer not null,
    event_type text not null,
    event_count bigint not null,
    avg_processing_seconds double precision,
    units_processed bigint,
    source_topic text not null,
    spark_batch_id bigint not null,
    processed_at timestamptz not null default now(),
    primary key (window_start, window_end, warehouse_id, event_type)
);
truncate table streaming.fulfillment_window_metrics;
SQL
" >/dev/null

echo "[3/6] Resetting topic and producing round 1..."
docker exec fulfillai-redpanda \
  rpk topic delete fulfillment.events -X brokers=127.0.0.1:9092 \
  >/dev/null 2>&1 || true

docker exec fulfillai-redpanda \
  rpk topic create fulfillment.events -X brokers=127.0.0.1:9092 \
  -p 3 -r 1 >/dev/null

python scripts/phase14_producer.py \
  --bootstrap localhost:19092 \
  --count 120 \
  --malformed 5 \
  --round round1 >/tmp/fulfillai_phase14b_producer1.log

echo "[4/6] Spark round 1 → PostgreSQL..."
"${DC[@]}" run --rm \
  -e FULFILLAI_PG_PASSWORD="$PG_PASSWORD" \
  -e PG_PASSWORD="$PG_PASSWORD" \
  -e RESET_STREAMING_PG=0 \
  phase14-spark \
  --packages org.apache.spark:spark-sql-kafka-0-10_2.13:4.0.4 \
  --conf spark.jars.ivy=/tmp/.ivy2 \
  scripts/phase14_spark_job.py \
  >/tmp/fulfillai_phase14b_spark1.log 2>&1

echo "[5/6] Round 2 + checkpoint restart..."
python scripts/phase14_producer.py \
  --bootstrap localhost:19092 \
  --count 60 \
  --malformed 2 \
  --seed 84 \
  --round round2 >/tmp/fulfillai_phase14b_producer2.log

"${DC[@]}" run --rm \
  -e FULFILLAI_PG_PASSWORD="$PG_PASSWORD" \
  -e PG_PASSWORD="$PG_PASSWORD" \
  -e RESET_STREAMING_PG=0 \
  phase14-spark \
  --packages org.apache.spark:spark-sql-kafka-0-10_2.13:4.0.4 \
  --conf spark.jars.ivy=/tmp/.ivy2 \
  scripts/phase14_spark_job.py \
  >/tmp/fulfillai_phase14b_spark2.log 2>&1

echo "[6/6] Verifying PostgreSQL reconciliation..."

DB_STATS="$(docker exec fulfillai-postgres sh -c "
psql -U '$PG_USER' -d '$PG_DB' -Atc \"
select count(*) || '|' || coalesce(sum(event_count),0)::bigint
from streaming.fulfillment_window_metrics;
\"
")"

DB_ROWS="${DB_STATS%%|*}"
DB_EVENTS="${DB_STATS##*|}"

QUALITY_STATS="$(python - <<'PY'
import json
from pathlib import Path
total = valid = rejected = 0
rounds = set()
for p in sorted(Path("artifacts/streaming/quality").glob("batch_*.json")):
    d = json.loads(p.read_text())
    total += int(d.get("records_seen", 0))
    valid += int(d.get("valid_records", 0))
    rejected += int(d.get("rejected_records", 0))
    rounds.update(d.get("round_ids", []))
print(f"{total}|{valid}|{rejected}|{','.join(sorted(rounds))}")
PY
)"

SEEN="$(echo "$QUALITY_STATS" | cut -d'|' -f1)"
VALID="$(echo "$QUALITY_STATS" | cut -d'|' -f2)"
REJECTED="$(echo "$QUALITY_STATS" | cut -d'|' -f3)"
ROUNDS="$(echo "$QUALITY_STATS" | cut -d'|' -f4)"

echo ""
echo "================================================"
echo "PHASE 14B COMPACT SUMMARY"
echo "================================================"
echo "postgres_schema       : streaming"
echo "postgres_table        : fulfillment_window_metrics"
echo "records_seen          : $SEEN"
echo "valid_records         : $VALID"
echo "rejected_records      : $REJECTED"
echo "rounds_seen           : $ROUNDS"
echo "postgres_rows         : $DB_ROWS"
echo "postgres_event_sum    : $DB_EVENTS"
echo "checkpoint_present    : $(test -d artifacts/streaming/checkpoints && echo True || echo False)"
echo "sink_semantics        : IDEMPOTENT UPSERT"
echo "frozen_ml_test_access : NO"

STATUS="PASS"
if [ "$SEEN" != "187" ] || \
   [ "$VALID" != "180" ] || \
   [ "$REJECTED" != "7" ] || \
   [ "$ROUNDS" != "round1,round2" ] || \
   [ "$DB_EVENTS" != "180" ] || \
   [ "$DB_ROWS" -le 0 ]; then
  STATUS="CHECK"
fi

echo "PHASE_14B_STATUS      : $STATUS"

echo ""
echo "SAMPLE POSTGRES ROWS:"
docker exec fulfillai-postgres sh -c "
psql -U '$PG_USER' -d '$PG_DB' -P pager=off -c \"
select
  window_start,
  warehouse_id,
  event_type,
  event_count,
  avg_processing_seconds
from streaming.fulfillment_window_metrics
order by window_start, warehouse_id, event_type
limit 5;
\"
"

unset FULFILLAI_PG_PASSWORD
