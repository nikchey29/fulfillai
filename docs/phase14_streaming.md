# Phase 14 — Redpanda + PySpark Structured Streaming

Architecture: Python producer → Redpanda (Kafka API) → PySpark Structured Streaming → explicit JSON schema → malformed-record filtering → event-time watermark → 1-minute warehouse/event windows → checkpointed artifacts.

The demo runs two rounds against the same Spark checkpoint to demonstrate restart/resume behavior. Java runs inside the Spark Docker image; no local Java installation is required. Frozen ML test partitions are not opened.
