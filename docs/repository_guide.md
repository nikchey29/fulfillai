# Repository and Reproduction Guide

This guide is the shortest safe path for working with FulfillAI without accidentally violating the project’s train/validation/test discipline.

## 1. What is version-controlled

Tracked source includes:

- configuration;
- PostgreSQL schema;
- SQL models and analytics;
- Python data-generation and validation code;
- feature-contract and materialization code;
- ML training / validation / final-test code;
- documentation and source-level tests.

Generated data and trained artifacts are deliberately ignored.

## 2. What is intentionally not in Git

```text
data/raw/synthetic/*
data/processed/synthetic/*
data/processed/features/*
artifacts/*
models/*
```

This prevents large datasets and binary model files from bloating the repository and reduces the chance of accidentally publishing a final-test artifact.

## 3. Environment setup

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Set PostgreSQL credentials in `.env`.

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

It does **not** train models or open Parquet test partitions.

## 5. Data pipeline

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

## 6. SQL layer

`make sql-models` applies the SQL model files in lexical order. It expects `.env` to define the same PostgreSQL database/user used by Docker Compose.

To inspect business analytics separately, run the query files under `sql/analytics/` with `psql` or a SQL client.

## 7. Feature artifacts

Feature materialization produces three datasets:

```text
demand_forecasting/
delivery_prediction/
inventory_risk/
```

Each contains chronological Train, Validation, and Test Parquet partitions plus metadata. Predictor selection comes from the metadata / feature contract rather than ad-hoc notebook column selection.

## 8. Modeling source

### Demand

The demand folder intentionally retains the experiment lineage rather than deleting earlier stages:

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

This makes the reasoning auditable but means not every script should be run blindly in sequence after the final test has already been completed.

### Delivery and inventory

The shared `ml/modeling/common_binary.py` layer handles candidate selection, threshold selection, final refit, and guarded one-time test evaluation.

Delivery V2 has its own namespace so the original V1 experiment remains historically intact.

## 9. Final-test safety

Do not rerun completed one-time test evaluations simply to obtain a different number.

For a genuinely new experiment:

1. create a versioned architecture / feature change;
2. make all choices using train + validation only;
3. freeze the source;
4. use a new untouched holdout or a clearly versioned benchmark protocol;
5. record results without modifying the model because of the test score.

## 10. Public repository checklist

Before pushing a portfolio update:

```bash
make verify
git diff --check
git status --short
```

Also verify manually that no `.env`, Parquet, Joblib, raw CSV, or credential file is staged.

## 11. Recommended GitHub presentation

Keep the repository landing page focused on:

- what problem the system solves;
- architecture diagram;
- the data/ML engineering decisions;
- final metrics;
- leakage and temporal evaluation discipline;
- quick-start instructions;
- honest limitations.

Do not bury the strongest result behind a long phase-by-phase development diary. The phase history belongs in source comments and supporting docs; the README should explain the finished system.
