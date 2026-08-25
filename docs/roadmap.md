# Things I Still Want to Explore

FulfillAI is complete enough to run as a coherent batch + platform project, but there are several directions I still find interesting. This file is a list of questions I would like to investigate, not a checklist of tools to add.

## 1. Replace part of the synthetic world

The synthetic generator is useful because every event and label can be traced back to known rules. The tradeoff is that synthetic relationships can become cleaner than real operations.

A useful next experiment would be to replace one part of the system with a public fulfillment, logistics, inventory, or retail dataset and keep the same leakage-safe evaluation structure. I am especially interested in seeing which feature assumptions fail first.

## 2. Monitoring after inference

The current project is careful before and during evaluation, but it does not yet have a full monitoring loop after predictions are served.

I would like to add:

- feature-distribution drift checks;
- prediction-distribution monitoring;
- segment-level metrics by warehouse / carrier / product family;
- latency and error-rate monitoring for the API;
- alerts that distinguish data-quality failures from model-quality changes.

## 3. Bring batch and streaming closer together

The batch and streaming paths currently share the same domain but remain separate execution modes.

A deeper version of the project would define a clearer contract between them: which metrics are computed in real time, which are reconciled in batch, and how late events or replayed events change the operational state.

## 4. Deploy the API for real

The repository includes Azure Container Apps Bicep, but I have intentionally left it described as infrastructure code rather than a completed deployment.

A future pass would build and publish the container, deploy it, verify the public health and inference endpoints, and then document the actual runtime behavior rather than the intended one.

## 5. Cost-sensitive decisions

The classification thresholds are currently selected from validation metrics. A more operational treatment would attach explicit costs to false positives and false negatives and choose thresholds from those costs.

That would make the decision layer easier to connect to questions such as expediting a shipment, reallocating inventory, or triggering a manual review.

## 6. Better uncertainty for demand

The demand model currently produces point forecasts. I would like to explore prediction intervals or quantile forecasts so downstream inventory decisions can distinguish between a stable forecast and one with large uncertainty.
