# FulfillAI Roadmap

The **core data + ML benchmark is complete and frozen**. The current working phase is a production/platform expansion that adds demonstrable engineering skills without changing historical final-test results.

## Completed core benchmark

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

## Platform expansion — source implemented, hands-on verification in progress

### Phase 12 — MLOps / serving
- FastAPI frozen-model serving layer;
- Docker API container;
- MLflow frozen-result tracking;
- machine-readable frozen-result manifest.

### Phase 13 — analytics engineering
- dbt PostgreSQL sources;
- staging models;
- fulfillment fact mart;
- warehouse-day KPI mart;
- dbt schema tests.

### Phase 14 — streaming
- Redpanda/Kafka-compatible event broker;
- order-event producer;
- PySpark Structured Streaming consumer;
- watermarking and 5-minute operational windows.

### Phase 15 — DevOps / cloud
- GitHub Actions source CI;
- tagged Docker image build/push to GHCR;
- Azure Container Apps Bicep deployment template.

### Phase 16 — BI
- Tableau-ready dbt marts;
- one-page operational dashboard to be built/published interactively.

## Resume rule

A technology becomes a resume skill only after its verification gate has been run successfully. See `docs/platform_engineering.md`.

## Future scientific extension

The most valuable later scientific step is replacing synthetic data with a public or enterprise-like fulfillment dataset and rerunning the leakage-safe evaluation structure as a new benchmark version.
