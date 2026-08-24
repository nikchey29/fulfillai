# FulfillAI Roadmap

The **core data + ML portfolio scope is complete**. Future work is optional extension work, not required to justify the current project.

## Completed core

- deterministic synthetic e-commerce fulfillment simulation;
- comprehensive data validation;
- PostgreSQL operational schema and atomic load;
- SQL analytical models and KPI queries;
- leakage-safe feature contracts;
- chronological Parquet train/validation/test materialization;
- zero-inflated demand forecasting;
- Delivery V1 scientific diagnosis and preserved benchmark;
- Delivery V2 redesigned benchmark;
- 7-day stockout and reorder-breach risk modeling;
- frozen final refits and one-time test evaluation;
- documented final results.

## Optional extension A — prediction API

Build a small FastAPI service that:

- loads frozen model bundles once at startup;
- validates request schemas;
- exposes `/predict/demand`, `/predict/delivery`, and `/predict/inventory` endpoints;
- returns model version / threshold metadata;
- logs latency and request counts.

## Optional extension B — BI dashboard

Create a dashboard over PostgreSQL for:

- fulfillment KPIs;
- carrier performance;
- warehouse throughput;
- late-delivery risk queues;
- stockout / reorder alerts;
- demand forecast vs actual trends.

## Optional extension C — event streaming

Use Kafka/Redpanda for `order_events` and `inventory_movements`, with consumers that update operational state and feature aggregates.

## Optional extension D — MLOps

Add:

- experiment registry;
- CI source tests;
- Dockerized model service;
- scheduled retraining;
- model/data drift monitoring;
- prediction logging;
- calibration monitoring;
- threshold changes controlled by validation rather than production test feedback.

## Optional extension E — real-data adaptation

The most valuable next scientific step is replacing synthetic data with a public or enterprise-like fulfillment dataset and rerunning the same leakage-safe evaluation structure.
