# Repository and Reproduction Guide

This is the shortest safe path for working with FulfillAI without accidentally breaking the train/validation/test boundaries that the completed experiments depend on.

## 1. What is version-controlled

Tracked source includes:

- configuration;
- PostgreSQL schema;
- SQL and dbt models;
- Python data-generation and validation code;
- feature-contract and materialization code;
- ML training / validation / final-test code;
- API, MLOps, and streaming code;
- infrastructure definitions;
- documentation and source-level tests.

Generated data and trained artifacts are deliberately ignored.

## 2. What is intentionally not in Git

```text
data/raw/synthetic/*
data/processed/synthetic/*
data/processed/features/*
artifacts/*
models/*
mlruns/*
dbt/target/*
dbt/logs/*
```

This keeps generated data and binary artifacts out of source control and reduces the chance of accidentally committing credentials or final-test outputs.

## 3. Environment setup

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Set local PostgreSQL credentials in `.env`.

## 4. Fast source verification

Before generating data or touching a database:

```bash
make verify
```

This checks:

- Python syntax;
- importability of core configuration modules;
- dataset and task registries;
- chronological split ordering;
- target exclusion from feature contracts;
- duplicate YAML keys;
- required repository files.

It does **not** train models or open generated Parquet test partitions.

## 5. Batch data path

```bash
make db-up
make generate
make validate-data
make db-preflight
make db-load
make sql-models
make build-features
```

Equivalent raw commands are documented in the root README.

## 6. SQL and dbt

`make sql-models` applies the hand-written SQL model files in lexical order.

The dbt project under `dbt/` provides a second analytical layer with sources, staging views, marts, and schema tests. Local dbt credentials belong in ignored local configuration rather than in the repository.

## 7. Feature artifacts

Feature materialization produces three datasets:

```text
demand_forecasting/
delivery_prediction/
inventory_risk/
```

Each contains chronological Train, Validation, and Test Parquet partitions plus metadata. Predictor selection comes from the feature contract rather than ad-hoc column selection inside a notebook.

## 8. Modeling source

### Demand

The demand folder intentionally keeps the experiment lineage:

- baselines;
- Poisson;
- HistGradientBoosting;
- feature enrichment;
- tuning;
- temporal backtesting;
- hurdle training;
- frozen validation;
- final refit;
- one-time final test.

Earlier experiments remain because they explain the path to the final architecture. They should not all be rerun blindly after the frozen test has already been completed.

### Delivery and inventory

The shared `ml/modeling/common_binary.py` layer handles candidate comparison, threshold selection, final refit, and guarded one-time test evaluation.

Delivery V2 has its own namespace so the original V1 experiment remains intact.

## 9. Final-test safety

Do not rerun a completed one-time test simply to see whether a small code change improves the number.

For a genuinely new experiment:

1. create a versioned architecture or feature change;
2. make decisions using Train and Validation only;
3. freeze the source and model configuration;
4. use a new untouched holdout or clearly versioned benchmark protocol;
5. record the result without tuning back against that holdout.

## 10. Platform verification

The local platform pieces can be checked independently of the frozen test set:

- `dbt build` for analytics engineering;
- Docker Compose configuration and service health;
- FastAPI `/health` and model-discovery endpoints;
- MLflow service availability;
- the Phase 14 streaming verification script;
- the Phase 14B PostgreSQL sink reconciliation script;
- the Tableau Public link and local screenshot reference.

See [`platform_engineering.md`](platform_engineering.md) for the current state of each component.

## 11. Before pushing changes

```bash
make verify
git diff --check
git status --short
```

Also check that local credentials, generated Parquet/CSV files, model binaries, dbt build output, MLflow state, and temporary backups are not staged.

I prefer keeping the repository small enough that the source, assumptions, and experiment history are easy to inspect without downloading generated data.
