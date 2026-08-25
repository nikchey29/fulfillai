# Changelog

## Platform and documentation pass — 2026-08-25

- Added dbt sources, staging models, marts, and tests around the PostgreSQL analytical layer.
- Added FastAPI serving and MLflow tracking around frozen model artifacts.
- Added Redpanda + PySpark Structured Streaming and a checkpointed PostgreSQL sink.
- Added Docker images, Compose profiles, source/container workflows, and Azure Container Apps Bicep.
- Published the Tableau operations dashboard and linked it from the project documentation.
- Reworked the documentation so the repository reads as a build record: decisions, failures, boundaries, and next questions are kept with the technical work.
- Kept the historical frozen model results unchanged.

## Model / repository stabilization — 2026-08-24

- Reframed the original scaffold around the completed data and ML system.
- Recorded final ML results, methodology, architecture, and reproduction notes.
- Added source verification and lightweight configuration tests.
- Added missing scikit-learn, Joblib, and PyArrow runtime dependencies.
- Added repeatable Makefile commands for the data, SQL, and feature workflow.
- Removed a duplicate `fulfillment` mapping from the YAML configuration without changing the active delivery settings.
- Preserved all frozen final-test results and model-selection decisions.
