"""PySpark Structured Streaming consumer for FulfillAI Redpanda events."""
from __future__ import annotations

import argparse
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser()
    p.add_argument("--bootstrap", default=os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:19092"))
    p.add_argument("--topic", default=os.getenv("FULFILLAI_EVENT_TOPIC", "fulfillai.order_events"))
    p.add_argument("--checkpoint", default=str(PROJECT_ROOT / "data" / "streaming" / "checkpoints" / "event_kpis"))
    return p


def main() -> None:
    args = parser().parse_args()
    try:
        from pyspark.sql import SparkSession
        from pyspark.sql.functions import col, from_json, to_timestamp, window
        from pyspark.sql.types import LongType, StringType, StructField, StructType
    except ImportError as exc:
        raise RuntimeError("PySpark is not installed. Run: pip install -r requirements-platform.txt") from exc

    spark = SparkSession.builder.appName("FulfillAIStreaming").getOrCreate()
    spark.sparkContext.setLogLevel("WARN")
    schema = StructType(
        [
            StructField("event_key", StringType(), False),
            StructField("order_id", LongType(), False),
            StructField("warehouse_id", LongType(), True),
            StructField("event_type", StringType(), False),
            StructField("event_ts", StringType(), False),
            StructField("source", StringType(), True),
        ]
    )
    raw = (
        spark.readStream.format("kafka")
        .option("kafka.bootstrap.servers", args.bootstrap)
        .option("subscribe", args.topic)
        .option("startingOffsets", "earliest")
        .load()
    )
    events = (
        raw.selectExpr("CAST(value AS STRING) AS json")
        .select(from_json(col("json"), schema).alias("event"))
        .select("event.*")
        .withColumn("event_time", to_timestamp("event_ts"))
        .withWatermark("event_time", "10 minutes")
    )
    kpis = (
        events.groupBy(window(col("event_time"), "5 minutes"), col("warehouse_id"), col("event_type"))
        .count()
        .orderBy("window")
    )
    query = (
        kpis.writeStream.outputMode("complete")
        .format("console")
        .option("truncate", "false")
        .option("checkpointLocation", args.checkpoint)
        .start()
    )
    print("FulfillAI PySpark stream running. Ctrl-C to stop.")
    query.awaitTermination()


if __name__ == "__main__":
    main()
