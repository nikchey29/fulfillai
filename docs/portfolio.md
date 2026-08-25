# FulfillAI Portfolio and Interview Guide

This file turns the technical project into recruiter-facing and interview-ready language without overstating what was built.

## 1. One-line project description

**FulfillAI is an end-to-end e-commerce operations intelligence platform that generates realistic fulfillment data, models it in PostgreSQL, builds leakage-safe time-series features, and evaluates demand, delivery, and inventory ML models with chronological frozen-test protocols.**

## 2. 30-second interview pitch

I built FulfillAI to practice the complete path from operational data to trustworthy ML rather than only training models in a notebook. I generated a year of reproducible e-commerce fulfillment events, validated and loaded them into PostgreSQL, created analytical and ML feature views, then built chronological train/validation/test datasets. The ML layer covers zero-inflated demand forecasting, delivery risk, stockout risk, and reorder risk. The part I focused on most was scientific integrity: explicit leakage contracts, validation-only model and threshold selection, Git freeze gates, and one-time final test evaluation.

## 3. 90-second technical pitch

FulfillAI simulates customers, products, warehouses, inventory, orders, shipments, inventory movements, and order lifecycle events. The data generator is deterministic and produces a one-year operating history. I validate relational and temporal consistency before an atomic PostgreSQL load, then use SQL views to create analytics and ML feature layers.

For machine learning, I deliberately use chronological splits. Demand is highly intermittent, so after baseline and gradient-boosting experiments I moved to a hurdle model that separates demand occurrence from positive-demand magnitude. The frozen final hurdle model reduced WAPE from 88.24% for the rolling-28 baseline to 69.59%, a 21.14% relative improvement.

Delivery prediction taught me a different lesson. The first synthetic benchmark produced PR-AUC close to prevalence because the outcomes were almost random with respect to leakage-safe features. Instead of tuning against the test set, I preserved that result, corrected the synthetic data-generating process in a separately versioned Delivery V2 benchmark, and reran the full validation/freeze/test process. V2 reached PR-AUC 0.303 for late delivery and 0.167 for delivery exceptions. I also built 7-day stockout and reorder-risk models, with final PR-AUC 0.360 and 0.998 respectively.

The main thing I would emphasize is that the repository treats data contracts, leakage control, and evaluation discipline as part of the system—not just model accuracy.

## 4. Resume bullets

Use 2–3 bullets depending on available space.

- Built **FulfillAI**, an end-to-end Python/PostgreSQL e-commerce operations platform spanning deterministic synthetic event generation, relational modeling, SQL analytics, leakage-safe feature engineering, and five forecasting/classification tasks.
- Designed chronological ML evaluation with explicit feature contracts, validation-only model/threshold selection, frozen final refits, Git cleanliness gates, and one-time test execution; improved zero-inflated demand forecasting from **88.24% to 69.59% WAPE (21.14% relative)** using a hurdle architecture.
- Diagnosed an unlearnable synthetic delivery benchmark and versioned a corrected data-generating process rather than tuning on test data; Delivery V2 achieved **0.303 PR-AUC** for late delivery and **0.167 PR-AUC** for delivery exceptions, while 7-day inventory models achieved **0.360 / 0.998 PR-AUC** for stockout/reorder risk.

## 5. Short GitHub description

**End-to-end e-commerce Data + ML platform: PostgreSQL analytics, leakage-safe temporal features, hurdle demand forecasting, delivery risk, inventory risk, and frozen one-time test evaluation.**

## 6. LinkedIn project description

Designed and implemented FulfillAI, an end-to-end e-commerce operations intelligence project combining synthetic event generation, PostgreSQL, analytical SQL, reproducible feature engineering, and machine learning. Built chronological train/validation/test pipelines for demand forecasting, delivery risk, stockout prediction, and reorder-risk prediction, with explicit leakage controls and one-time frozen test evaluation. Final experiments included a zero-inflated hurdle demand model with 21.14% relative WAPE improvement over a rolling baseline and versioned Delivery V2 models created after diagnosing a flaw in the original synthetic data-generating process.

## 7. Strong interview stories

### Story A — finding leakage before celebrating a score

**Situation:** Historical demand and inventory tables contained fields that looked predictive but represented same-day or future information.

**Action:** I moved feature eligibility into explicit contracts and SQL definitions, excluded realized outcomes/current snapshots, and enforced chronological windows ending before the prediction date.

**Result:** The models became harder to train, but the evaluation became defensible. The final scores represent prediction-time-safe features rather than accidental access to the answer.

### Story B — why a weaker model result was valuable

**Situation:** Delivery V1 had very weak PR-AUC despite trying reasonable models.

**Diagnosis:** The labels had been generated nearly independently of the allowed predictors. A leakage-safe model therefore had almost nothing to learn.

**Action:** I froze and preserved V1 instead of retuning against its test set. Then I created Delivery V2 as a separately versioned synthetic benchmark where risk depends on shipment-time-safe variables.

**Result:** The new benchmark showed meaningful lift while preserving a clean scientific narrative.

### Story C — choosing a hurdle model

**Situation:** Most warehouse/product/day rows had zero demand.

**Problem:** A single regressor could appear competitive by predicting near-zero values almost everywhere.

**Action:** I separated occurrence probability from positive-demand magnitude and used a frozen hard gate: below the occurrence threshold the forecast is zero; above it the magnitude model supplies the positive-demand forecast.

**Result:** Final WAPE improved by 21.14% relative to the rolling-28 baseline.

## 8. Likely interview questions

### Why PR-AUC instead of accuracy?

The positive class is rare for several operational-risk tasks. Accuracy could be high by predicting the majority class. PR-AUC focuses on the quality of positive-event ranking and has a meaningful baseline close to event prevalence.

### Why not random train/test split?

These are operational time-series problems. Random splitting can leak future behavior into training and exaggerate generalization. The project uses chronological partitions so validation and test occur strictly after training.

### Why is the reorder model almost perfect?

Because the data is synthetic and the future reorder label is strongly determined by prior inventory/demand state. I treat the score as evidence that the pipeline can recover the generated relationship, not as a real-world performance claim.

### Why did RMSE favor the rolling demand baseline while WAPE favored the hurdle model?

RMSE is especially sensitive to large individual errors, while WAPE measures total absolute error relative to total demand. The final model was selected using the predeclared business metric, WAPE, but I preserved the RMSE result because it reveals a real tradeoff instead of hiding it.

### Why not use the test set to choose a better threshold?

That would turn the test set into another validation set and bias the final estimate. Thresholds are chosen on validation and frozen before test access.

### What would you do next with real data?

I would replace the synthetic generator with real operational sources, add data contracts and drift checks around ingestion, retrain using rolling-origin evaluation, calibrate thresholds to business costs, and monitor prediction quality by warehouse/carrier/product segments.

## 9. Honest project limitations

State these confidently when relevant:

- the data is synthetic;
- the repository is batch-first, not a deployed real-time service;
- API, dashboard, streaming, and cloud deployment are future extensions;
- generated model artifacts are intentionally not checked into Git;
- strong inventory results should not be generalized to real operational data;
- Delivery V2 changed the simulation, so V1→V2 gains are not pure model-tuning gains.

These limitations strengthen the project explanation because they show you understand what the experiment can and cannot prove.
