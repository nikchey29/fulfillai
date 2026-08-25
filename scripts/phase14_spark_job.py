from __future__ import annotations

import json
import os
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from pyspark.sql import SparkSession, functions as F, types as T


BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "redpanda:9092")
TOPIC = os.getenv("KAFKA_TOPIC", "fulfillment.events")
ROOT = Path(os.getenv("STREAMING_ARTIFACT_ROOT", "/opt/fulfillai/artifacts/streaming"))
CHECKPOINT_ROOT = ROOT / "checkpoints"
AGG_OUT = ROOT / "aggregates"
QUALITY_OUT = ROOT / "quality"

PG_HOST = os.getenv("PG_HOST", "postgres")
PG_PORT = int(os.getenv("PG_PORT", "5432"))
PG_USER = os.getenv("PG_USER", "fulfillai")
PG_DB = os.getenv("PG_DB", "fulfillai")
PG_PASSWORD = os.getenv("PG_PASSWORD", "")

for p in (CHECKPOINT_ROOT, AGG_OUT, QUALITY_OUT):
    p.mkdir(parents=True, exist_ok=True)


schema = T.StructType(
    [
        T.StructField("event_id", T.StringType(), True),
        T.StructField("round_id", T.StringType(), True),
        T.StructField("event_type", T.StringType(), True),
        T.StructField("event_ts", T.StringType(), True),
        T.StructField("order_id", T.LongType(), True),
        T.StructField("shipment_id", T.LongType(), True),
        T.StructField("warehouse_id", T.IntegerType(), True),
        T.StructField("status", T.StringType(), True),
        T.StructField("processing_seconds", T.DoubleType(), True),
        T.StructField("units", T.IntegerType(), True),
    ]
)


def pg_connect():
    return psycopg.connect(
        host=PG_HOST,
        port=PG_PORT,
        user=PG_USER,
        dbname=PG_DB,
        password=PG_PASSWORD,
        connect_timeout=10,
        row_factory=dict_row,
    )


def ensure_pg_schema():
    ddl = """
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

    create index if not exists ix_fulfillment_window_metrics_processed_at
        on streaming.fulfillment_window_metrics (processed_at);

    create index if not exists ix_fulfillment_window_metrics_warehouse
        on streaming.fulfillment_window_metrics (warehouse_id, window_start);
    """
    with pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(ddl)
        conn.commit()


def reset_pg_sink():
    with pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("truncate table streaming.fulfillment_window_metrics")
        conn.commit()


def write_json(path: Path, payload):
    path.write_text(json.dumps(payload, indent=2, default=str))


def upsert_postgres(rows: list[dict], batch_id: int):
    if not rows:
        return

    sql = """
    insert into streaming.fulfillment_window_metrics (
        window_start,
        window_end,
        warehouse_id,
        event_type,
        event_count,
        avg_processing_seconds,
        units_processed,
        source_topic,
        spark_batch_id,
        processed_at
    )
    values (
        %(window_start)s,
        %(window_end)s,
        %(warehouse_id)s,
        %(event_type)s,
        %(event_count)s,
        %(avg_processing_seconds)s,
        %(units_processed)s,
        %(source_topic)s,
        %(spark_batch_id)s,
        now()
    )
    on conflict (window_start, window_end, warehouse_id, event_type)
    do update set
        event_count = excluded.event_count,
        avg_processing_seconds = excluded.avg_processing_seconds,
        units_processed = excluded.units_processed,
        source_topic = excluded.source_topic,
        spark_batch_id = excluded.spark_batch_id,
        processed_at = now()
    """

    payload = []
    for row in rows:
        row = dict(row)
        row["source_topic"] = TOPIC
        row["spark_batch_id"] = int(batch_id)
        payload.append(row)

    with pg_connect() as conn:
        with conn.cursor() as cur:
            cur.executemany(sql, payload)
        conn.commit()


def main():
    spark = (
        SparkSession.builder
        .appName("FulfillAI-Phase14-StructuredStreaming")
        .config("spark.sql.shuffle.partitions", "4")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")

    ensure_pg_schema()

    if os.getenv("RESET_STREAMING_PG", "0") == "1":
        reset_pg_sink()

    source = (
        spark.readStream
        .format("kafka")
        .option("kafka.bootstrap.servers", BOOTSTRAP)
        .option("subscribe", TOPIC)
        .option("startingOffsets", "earliest")
        .option("failOnDataLoss", "false")
        .load()
    )

    parsed = (
        source.select(
            F.col("partition").alias("kafka_partition"),
            F.col("offset").alias("kafka_offset"),
            F.col("timestamp").alias("kafka_timestamp"),
            F.col("value").cast("string").alias("raw_json"),
        )
        .withColumn("event", F.from_json("raw_json", schema))
        .select("kafka_partition", "kafka_offset", "kafka_timestamp", "raw_json", "event.*")
        .withColumn("event_time", F.to_timestamp("event_ts"))
    )

    valid_condition = (
        F.col("event_id").isNotNull()
        & F.col("event_time").isNotNull()
        & F.col("warehouse_id").isNotNull()
        & F.col("event_type").isNotNull()
        & F.col("processing_seconds").isNotNull()
    )

    valid = parsed.filter(valid_condition)
    watermarked = valid.withWatermark("event_time", "2 minutes")

    aggregates = (
        watermarked
        .groupBy(
            F.window("event_time", "1 minute"),
            F.col("warehouse_id"),
            F.col("event_type"),
        )
        .agg(
            F.count("*").alias("event_count"),
            F.round(F.avg("processing_seconds"), 2).alias("avg_processing_seconds"),
            F.sum("units").alias("units_processed"),
        )
    )

    def write_aggregates(batch_df, batch_id: int):
        materialized = (
            batch_df.select(
                F.col("window.start").alias("window_start"),
                F.col("window.end").alias("window_end"),
                "warehouse_id",
                "event_type",
                "event_count",
                "avg_processing_seconds",
                "units_processed",
            )
            .orderBy("window_start", "warehouse_id", "event_type")
            .collect()
        )

        rows = [r.asDict(recursive=True) for r in materialized]

        write_json(
            AGG_OUT / f"batch_{batch_id:05d}.json",
            rows,
        )
        upsert_postgres(rows, batch_id)

    def write_quality(batch_df, batch_id: int):
        total = batch_df.count()
        valid_count = batch_df.filter(valid_condition).count()
        invalid_count = total - valid_count
        rounds = [
            r["round_id"]
            for r in batch_df.select("round_id")
            .where(F.col("round_id").isNotNull())
            .distinct()
            .collect()
        ]
        write_json(
            QUALITY_OUT / f"batch_{batch_id:05d}.json",
            {
                "batch_id": batch_id,
                "records_seen": total,
                "valid_records": valid_count,
                "rejected_records": invalid_count,
                "round_ids": sorted(rounds),
            },
        )

    quality_q = (
        parsed.writeStream
        .outputMode("append")
        .foreachBatch(write_quality)
        .option("checkpointLocation", str(CHECKPOINT_ROOT / "quality"))
        .trigger(availableNow=True)
        .start()
    )

    aggregate_q = (
        aggregates.writeStream
        .outputMode("update")
        .foreachBatch(write_aggregates)
        .option("checkpointLocation", str(CHECKPOINT_ROOT / "aggregates"))
        .trigger(availableNow=True)
        .start()
    )

    quality_q.awaitTermination()
    aggregate_q.awaitTermination()

    with pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                select
                    count(*) as rows,
                    coalesce(sum(event_count), 0)::bigint as events
                from streaming.fulfillment_window_metrics
            """)
            pg = cur.fetchone()

    print("SPARK_STREAM_COMPLETE=YES")
    print(f"QUALITY_BATCH_FILES={len(list(QUALITY_OUT.glob('batch_*.json')))}")
    print(f"AGGREGATE_BATCH_FILES={len(list(AGG_OUT.glob('batch_*.json')))}")
    print(f"POSTGRES_STREAMING_ROWS={pg['rows']}")
    print(f"POSTGRES_STREAMING_EVENTS={pg['events']}")
    print(f"CHECKPOINT_ROOT={CHECKPOINT_ROOT}")

    spark.stop()


if __name__ == "__main__":
    main()
