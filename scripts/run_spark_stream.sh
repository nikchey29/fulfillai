#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
SPARK_VERSION="$(python - <<'PY'
import pyspark
print(pyspark.__version__)
PY
)"

echo "Starting FulfillAI Structured Streaming with Spark ${SPARK_VERSION}"
spark-submit \
  --packages "org.apache.spark:spark-sql-kafka-0-10_2.12:${SPARK_VERSION}" \
  src/fulfillai/streaming/spark_pipeline.py "$@"
