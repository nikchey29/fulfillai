# FulfillAI Platform / MLOps Expansion

This layer expands the frozen data/ML benchmark into a demonstrable data-platform and MLOps portfolio system without altering the historical final-test results.

## Implemented code surfaces

- **dbt + PostgreSQL:** source declarations, schema tests, staging views, fulfillment fact mart, warehouse-day KPI mart.
- **FastAPI:** health, frozen-results, model-discovery, and frozen-artifact inference endpoints.
- **Docker:** reproducible API container plus composable infrastructure services.
- **MLflow:** immutable frozen benchmark metrics can be logged as an experiment/evidence run without retraining.
- **Redpanda/Kafka API:** event producer for FulfillAI order events.
- **PySpark Structured Streaming:** Kafka consumer with watermarking and 5-minute warehouse/event windows.
- **GitHub Actions:** source CI and API image build/push workflow.
- **Azure Container Apps IaC:** Bicep template for deploying the API image.
- **Tableau-ready marts:** dbt models and a concrete dashboard build plan.

## Scientific boundary

The V1/V2 frozen model scores remain historical evidence. Platform work wraps those artifacts; it does not tune models against already-seen test data.

## Resume-claim policy

A technology should be listed as hands-on only after the corresponding local or cloud verification has actually been run:

| Technology | Evidence required before resume claim |
|---|---|
| dbt | `dbt build` succeeds against FulfillAI PostgreSQL |
| FastAPI | local `/health`, `/v1/results`, and one artifact-backed `/predict` request |
| Docker | API image builds and container serves successfully |
| MLflow | a visible FulfillAI experiment/run is created |
| Redpanda | producer publishes events to the local topic |
| PySpark | Structured Streaming consumes and produces windowed output |
| Tableau | dashboard workbook is built from dbt marts |
| Azure | API is actually deployed and `/health` responds from Azure |
