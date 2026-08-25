# Phase 14 — Redpanda + PySpark Structured Streaming

This is the compact local verification path for FulfillAI's event stream.

```text
Python producer
   ↓
Redpanda (Kafka API)
   ↓
PySpark Structured Streaming
   ↓
explicit JSON schema
   ↓
malformed-record filtering
   ↓
event-time watermark
   ↓
1-minute warehouse/event windows
   ↓
checkpointed output
```

The verification runs two rounds against the same Spark checkpoint. I wanted restart/resume behavior to be something the project actually exercises rather than a property assumed from the framework.

Java runs inside the Spark Docker image, so the local machine does not need a separate Java setup. The script also checks that the frozen ML test partitions are not opened while the streaming path runs.

The reusable library pipeline in `src/fulfillai/streaming/spark_pipeline.py` uses a longer five-minute window by default; this phase script keeps one-minute windows so the local verification completes quickly.
