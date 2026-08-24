# ML Methodology and Scientific Integrity

This document explains the evaluation rules behind FulfillAI. These rules are as important as the model classes themselves because the project contains time-dependent forecasting and rare-event classification.

## 1. Core principle

**Validation is used to make decisions. Test is used once to estimate the performance of already-frozen decisions.**

The repository deliberately separates:

1. training;
2. validation-based model / threshold selection;
3. temporal robustness checks where applicable;
4. final refit on train + validation;
5. source freeze;
6. one-time final test.

Post-test tuning is not allowed for the corresponding frozen experiment.

## 2. Chronological partitioning

The feature layer uses the following default boundaries:

| Partition | Dates | Purpose |
|---|---|---|
| Train | 2025-08-01 → 2026-04-30 | fit models and preprocessors |
| Validation | 2026-05-01 → 2026-05-31 | model selection and threshold selection |
| Test | 2026-06-01 → 2026-07-31 | one final unbiased evaluation |

The repository explicitly rejects random splitting for these time-dependent datasets.

## 3. Leakage prevention

### Demand forecasting

The demand view contains both useful historical context and same-day realized outcomes. Prediction-time contracts exclude same-day demand, transaction outcomes, and current/static inventory snapshots that would leak information into historical predictions.

Safe signals include lags and historical windows whose endpoints are before the prediction date, such as:

- 1/7/14/21/28/35-day demand lags;
- rolling 7-day and 28-day history;
- historical nonzero-day counts and demand frequency;
- days since last positive demand;
- historical volatility and coefficient of variation;
- previous-period trend and acceleration;
- same-weekday historical behavior.

### Delivery prediction

Outcome and post-outcome columns are excluded from predictors:

- `is_late_delivery`
- `is_delivery_exception`
- `is_delivered`
- `shipment_status`
- `delivered_at`
- `actual_transit_hours`
- `delivery_delay_hours`
- technical identifiers used only for grain / joins

Shipment-time estimates such as promised service windows or carrier expected-delivery estimates may remain valid when they are known before the outcome occurs.

### Inventory risk

The inventory feature view predicts a future seven-day window. It excludes:

- future-window label-construction fields;
- current-day realized inventory state;
- current-day realized demand;
- technical identifiers.

The model instead uses prior-day inventory state and historical demand windows.

## 4. Population eligibility

Classification population definitions are explicit.

### Late delivery

`is_late_delivery` is meaningful only when the shipment has an observable delivered outcome. Therefore:

```text
population = delivered shipments only
label      = delivered_at > expected_delivery_at
```

Delivery exceptions are excluded from the late-delivery population rather than silently labeled as `0`.

### Delivery exception

The exception task uses all eligible dispatched shipments:

```text
population = dispatched shipments
label      = shipment_status == exception
```

This separation prevents two different operational questions from being mixed into the same label semantics.

## 5. Metrics

### Demand

Primary metric: **WAPE**.

Supporting metrics include MAE, RMSE, and sMAPE. Because demand is highly intermittent, the project also inspects zero-demand vs positive-demand error separately.

### Rare-event classification

Primary metric: **PR-AUC**.

PR-AUC is preferred to plain accuracy because several targets are rare. ROC-AUC, precision, recall, F1/F2, Brier score, and top-k lift are supporting diagnostics depending on the task.

A useful reference for rare-event tasks is the positive-class prevalence: a non-informative ranking has expected PR-AUC close to that prevalence.

## 6. Threshold selection

Probability ranking and classification threshold are treated as separate decisions.

- Model candidates are ranked on validation PR-AUC.
- The classification threshold is chosen on validation according to the configured task objective.
- The selected threshold is frozen before the final refit and final test.

Examples in the completed run:

- Late Delivery V2: threshold `0.63`, F1-oriented.
- Delivery Exception V2: threshold `0.69`, F1-oriented.
- Stockout Risk: threshold `0.77`, recall-oriented proxy.
- Reorder Breach Risk: threshold `0.50`, F1-oriented.

## 7. Demand hurdle model

Daily warehouse/product demand is heavily zero-inflated. A single regressor can obtain deceptively favorable aggregate error by predicting values close to zero for most rows.

The final architecture explicitly separates two questions:

1. **Occurrence:** will demand be positive?
2. **Magnitude:** if demand is positive, how many units are expected?

The final prediction is the combination of the two components. Threshold calibration and temporal robustness were performed before the one-time test.

## 8. Delivery V1 → V2 redesign

Delivery V1 produced weak but scientifically valid final-test results. The reason was not simply insufficient model tuning. The synthetic generator sampled late/exception outcomes almost independently of leakage-safe predictor variables, so there was little learnable signal available to a legitimate prediction-time model.

The project therefore preserved V1 and created a **new benchmark version** rather than modifying V1 after seeing the test results.

Delivery V2 changes the synthetic data-generating process so event risk depends on shipment-time-safe information such as:

- carrier;
- shipping method;
- warehouse;
- processing/service pressure;
- calendar effects.

The same validation → freeze → final-refit → one-time-test discipline was then rerun on V2.

This distinction matters in interviews: the improvement is not presented as "we tuned until test PR-AUC increased." It is presented as "the original simulation had no predictive signal; we diagnosed the data-generating process, versioned the benchmark, and reran a clean experiment."

## 9. Test-lock implementation

The shared classification evaluator enforces several safeguards:

- explicit one-time-test confirmation;
- clean Git working tree before test access;
- frozen model artifact must already exist;
- frozen feature-column contract must match test features;
- final metric artifact must not already exist;
- preprocessing is transform-only on test;
- no fit, model selection, or threshold tuning occurs on test;
- output explicitly records that post-test model changes are not allowed.

The Phase 8 demand evaluator implements the same scientific idea with additional model-bundle and contract checks.

## 10. Reproducibility boundaries

Source code and configuration are version-controlled. Large generated data and model artifacts are ignored by Git.

A reproducible rerun therefore depends on:

- the exact source commit;
- `configs/data_generation.yaml`;
- Python/package environment;
- PostgreSQL schema and SQL models;
- feature metadata generated during materialization;
- the frozen selection / model artifacts generated locally.

Final published metrics should be treated as records of the completed experiment, not as values that every new random or dependency environment is guaranteed to reproduce bit-for-bit unless all environment details are also frozen.
