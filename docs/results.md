# Final Model Results

This file records the completed FulfillAI model evaluations observed in the final project run. Large generated JSON/Joblib/Parquet artifacts are intentionally excluded from Git, so this document provides a compact durable summary.

## 1. Demand forecasting — frozen Phase 8 final test

**Test rows:** 63,501
**Test window:** 2026-06-01 → 2026-07-31
**Architecture:** hurdle model
**Frozen occurrence threshold:** 0.925

### Forecast metrics

| Model | MAE | RMSE | WAPE | sMAPE |
|---|---:|---:|---:|---:|
| **Hurdle** | **0.266097** | 0.933770 | **69.588383%** | **24.146230%** |
| Rolling 28-day average | 0.337432 | **0.836723** | 88.243349% | 150.477220% |

**WAPE improvement:** +18.654966 percentage points
**Relative WAPE improvement:** **21.14%**

The hurdle model wins on the primary business metric (WAPE) and MAE, while the rolling baseline has lower RMSE. That disagreement is worth preserving rather than hiding: large-error sensitivity and aggregate weighted error are measuring different aspects of performance.

### Occurrence classifier diagnostics

| Metric | Value |
|---|---:|
| PR-AUC | 0.589171 |
| ROC-AUC | 0.820941 |
| Precision | 0.979257 |
| Recall | 0.132577 |
| F1 | 0.233536 |
| F2 | 0.160295 |
| Brier score | 0.081009 |
| True positives | 1,133 |
| False positives | 24 |
| True negatives | 54,931 |
| False negatives | 7,413 |

The frozen threshold favors extremely high precision at the cost of recall. The final forecast is **hard-gated**: rows below the 0.925 occurrence threshold receive a zero forecast, while rows above the threshold receive the magnitude model's positive-demand prediction.

---

## 2. Delivery V1 — preserved original benchmark

V1 is retained as the original clean experiment. Its final test exposed that the synthetic target-generation process contained little learnable signal for leakage-safe predictors.

| Task | Final PR-AUC | Interpretation |
|---|---:|---|
| Late delivery V1 | 0.099390 | weak / near prevalence-level signal |
| Delivery exception V1 | 0.045577 | weak / near prevalence-level signal |

No post-test tuning was performed on V1. Instead, the synthetic benchmark was versioned and redesigned as Delivery V2.

---

## 3. Delivery V2 — redesigned learnable benchmark

### Validation results

| Task | Validation PR-AUC | Prevalence baseline | Lift | Winner | Frozen threshold |
|---|---:|---:|---:|---|---:|
| Late delivery | 0.293560 | 0.088089 | 3.33× | balanced logistic regression | 0.6300 |
| Delivery exception | 0.155647 | 0.039333 | 3.96× | balanced logistic regression | 0.6900 |

### One-time final test

#### Late delivery V2

**Population:** delivered shipments only
**Rows:** 7,625
**Positive rows:** 705

| Metric | Value |
|---|---:|
| **PR-AUC** | **0.303115** |
| ROC-AUC | 0.755719 |
| Precision | 0.255760 |
| Recall | 0.472340 |
| F1 | 0.331839 |
| F2 | 0.403930 |
| Lift @ 1% | 6.742194 |
| PR-AUC / prevalence | **3.28×** |

#### Delivery exception V2

**Population:** all eligible dispatched shipments
**Rows:** 7,947
**Positive rows:** 322

| Metric | Value |
|---|---:|
| **PR-AUC** | **0.167229** |
| ROC-AUC | 0.796958 |
| Precision | 0.163243 |
| Recall | 0.468944 |
| F1 | 0.242181 |
| F2 | 0.341166 |
| Lift @ 1% | 8.021040 |
| PR-AUC / prevalence | **4.13×** |

### V1 → V2 comparison

| Task | V1 PR-AUC | V2 PR-AUC | Absolute gain | Relative gain |
|---|---:|---:|---:|---:|
| Late delivery | 0.099390 | **0.303115** | +0.203725 | +204.98% |
| Delivery exception | 0.045577 | **0.167229** | +0.121652 | +266.92% |

These gains must be interpreted correctly: V2 is a **new data-generating benchmark** with learnable shipment-time signal, not a post-test retuning of the original V1 benchmark.

---

## 4. Inventory risk — frozen Phase 10 final tests

### Stockout risk — next 7 days

**Final model:** random forest

| Metric | Value |
|---|---:|
| **PR-AUC** | **0.359567** |
| ROC-AUC | 0.992886 |
| Precision | 0.321289 |
| Recall | 0.832911 |
| F1 | 0.463707 |

The high recall is operationally useful for a stockout-warning use case where missing a true upcoming stockout can be expensive.

### Reorder-breach risk — next 7 days

**Final model:** random forest

| Metric | Value |
|---|---:|
| **PR-AUC** | **0.998317** |
| ROC-AUC | 0.999642 |
| Precision | 0.965487 |
| Recall | 0.986339 |
| F1 | 0.975801 |

The near-perfect result should be described with appropriate caution because this is synthetic data. It shows that the generated reorder target is highly predictable from prior inventory/demand state; it is not evidence that a real production reorder system would achieve the same score.

---

## 5. Result interpretation principles

1. **Do not compare metrics across unrelated tasks as if they measure the same difficulty.**
2. **PR-AUC must be interpreted relative to target prevalence.**
3. **Synthetic-data scores demonstrate pipeline and modeling behavior, not real-world business accuracy.**
4. **Final test results are frozen records.** Any later model redesign should be versioned as a new experiment with a new untouched test protocol rather than tuning against these results.
