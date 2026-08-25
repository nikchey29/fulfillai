# Phase 14B — Streaming PostgreSQL Sink

Phase 14B takes the checkpointed Redpanda/PySpark path one step further and writes the windowed aggregates back into PostgreSQL.

## Data path

```text
Python event producer
   ↓
Redpanda (Kafka API)
   ↓
PySpark Structured Streaming
   ↓
schema validation + event-time watermark
   ↓
1-minute warehouse/event aggregates
   ↓
idempotent PostgreSQL UPSERT
```

## PostgreSQL object

`streaming.fulfillment_window_metrics`

Primary key:

- `window_start`
- `window_end`
- `warehouse_id`
- `event_type`

Each Spark micro-batch updates the latest aggregate for the same logical window/group rather than appending a duplicate. That makes replaying a processed batch safe for the materialized aggregate state.

## What the verification checks

The script runs two producer/Spark rounds with the same checkpoint and reconciles the result with PostgreSQL:

- 187 input events;
- 180 valid events;
- 7 rejected events;
- both `round1` and `round2` processed;
- PostgreSQL aggregate event sum equals 180;
- persisted aggregate rows exist;
- checkpoint state exists;
- frozen ML test partitions are not accessed.

The point of the second round is not extra volume; it is proving that checkpoint reuse and the sink's upsert semantics behave correctly when the stream resumes.
