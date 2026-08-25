# Phase 14B — Streaming PostgreSQL Sink

This phase extends the Redpanda + PySpark Structured Streaming pipeline with a
real PostgreSQL sink.

## Data path

Python event producer → Redpanda (Kafka API) → PySpark Structured Streaming →
schema validation → event-time watermark → 1-minute warehouse/event aggregates →
idempotent PostgreSQL UPSERT.

## PostgreSQL object

`streaming.fulfillment_window_metrics`

Primary key:

- `window_start`
- `window_end`
- `warehouse_id`
- `event_type`

Each Spark micro-batch overwrites the latest aggregate for the same logical
window/group instead of adding duplicate rows. This makes repeated micro-batch
processing safe for the materialized aggregate state.

## Validation

The demo performs two producer/Spark rounds with the same checkpoints and checks:

- 187 total input events
- 180 valid events
- 7 rejected events
- both round1 and round2 processed
- PostgreSQL aggregate event sum reconciles to 180
- PostgreSQL rows exist
- checkpoint state exists
- frozen ML test partitions are not accessed
