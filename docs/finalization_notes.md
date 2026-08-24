# Finalization Notes

This pass converts the repository from a development-phase snapshot into a portfolio-ready source package.

## Changes in this finalization pass

- rewrote the outdated README that still reported "Phase 0";
- documented the completed architecture and ML scope;
- recorded final model results in source-controlled documentation;
- documented the leakage-safe / chronological evaluation methodology;
- added recruiter, resume, LinkedIn, and interview material;
- added a concise roadmap that separates completed work from optional future features;
- added source-level verification tooling and lightweight tests;
- populated the Makefile with repeatable developer commands;
- added missing ML/Parquet runtime dependencies to `requirements.txt`;
- removed a duplicate top-level `fulfillment:` YAML block while preserving the effective configuration values from the canonical block.

## What was intentionally not changed

- final model results;
- frozen thresholds;
- model architectures selected by completed experiments;
- SQL leakage contracts;
- generated datasets or model artifacts;
- one-time final-test code semantics.

## Scientific record

Delivery V1 results remain part of the project history. Delivery V2 is documented as a separately versioned correction to the synthetic data-generating process, not as a retuned version of the V1 final test.
