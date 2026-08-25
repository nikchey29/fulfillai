# FulfillAI Platform Layer

The first version of FulfillAI was batch-first: generate operational data, load PostgreSQL, build features, train models, and freeze the results. Once that path was stable, I added a platform layer around the same data and model artifacts to see how they behave when serving, analytics engineering, streaming, and orchestration enter the picture.

None of these additions change the historical frozen-test results.

## Components

- **dbt + PostgreSQL** — source declarations, schema tests, staging views, a fulfillment fact mart, and a warehouse-day KPI mart.
- **FastAPI** — health, frozen-results, model-discovery, and frozen-artifact inference endpoints.
- **Docker** — reproducible containers for the API, MLflow, and Spark workloads.
- **MLflow** — records frozen benchmark metrics as experiment runs without retraining the models.
- **Redpanda / Kafka API** — carries FulfillAI order events.
- **PySpark Structured Streaming** — consumes events, applies watermarking, and builds warehouse/event windows. The reusable library pipeline defaults to five-minute windows; the compact Phase 14 verification script uses one-minute windows to keep the local run short.
- **PostgreSQL streaming sink** — persists windowed streaming metrics with idempotent upsert behavior.
- **GitHub Actions** — source checks plus an API container build workflow.
- **Tableau** — an executive operations dashboard built from the analytical export.
- **Azure Container Apps IaC** — a Bicep template for a future API deployment.

## Verification notes

The local platform path has been exercised end to end for the parts that can run locally:

| Component | What was checked |
|---|---|
| dbt | build completed against FulfillAI PostgreSQL with the model/tests passing |
| FastAPI | service started and returned model metadata from the frozen artifacts |
| Docker | Compose configurations validated and the API / MLflow services ran locally |
| MLflow | local service responded successfully |
| Redpanda | broker and console started as part of the streaming stack |
| PySpark | two streaming rounds completed against the same checkpoint |
| PostgreSQL sink | streaming aggregates reconciled back to PostgreSQL |
| Tableau | dashboard built, cross-filtered, and published to Tableau Public |
| Azure | template exists; deployment has not been completed |

I keep the last row explicit because infrastructure code and a verified deployment are different things.

## Boundary around the frozen experiments

The platform code consumes frozen model artifacts and recorded metrics. It does not reopen the historical test partitions or retune a model because a serving or streaming component was added later.

That separation lets the project evolve operationally without quietly changing what the original model results mean.
