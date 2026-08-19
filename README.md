# FulfillAI

**E-Commerce Operations Intelligence Platform**

FulfillAI is an end-to-end Data & AI project for analyzing e-commerce fulfillment operations and developing predictive tools for operational decision support.

The project is being built incrementally to combine data engineering, SQL analytics, machine learning, APIs and business intelligence in one reproducible system.

## Project Goals

- Model customers, products, orders, warehouses, inventory and shipments.
- Process historical and event-driven operational data.
- Build analytics-ready datasets for fulfillment KPIs.
- Predict orders at risk of delayed fulfillment.
- Expose analytical and predictive functionality through APIs.
- Build operational dashboards for business users.

## Current Status

Phase 0 — engineering foundation and repository setup.

## Planned Architecture

See [docs/architecture.md](docs/architecture.md).

## Repository Structure

```text
fulfillai/
├── configs/
├── data/
├── docker/
├── docs/
├── models/
├── notebooks/
├── sql/
├── src/fulfillai/
├── tests/
├── .env.example
├── .gitignore
├── Makefile
├── requirements.txt
└── requirements-dev.txt
```

## Development

The project currently uses Python 3.11.

Additional infrastructure and dependencies will be introduced only as their corresponding components are implemented.
