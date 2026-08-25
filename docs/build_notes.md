# Notes from Building FulfillAI

FulfillAI started as a demand-forecasting idea and became much larger once I stopped treating the dataset as something that should already exist.

I wanted to know what I would have to build before I could trust a prediction coming out of an operations system. That led me backward from modeling into data generation, event semantics, relational constraints, temporal validation, feature contracts, and only then back into ML.

## Starting with operations instead of a model

The first useful decision was to model the fulfillment process itself. Orders affect inventory. Shipments have a lifecycle. Cancellations can happen at different points. Inventory reservations need releases. Events need timestamps that make sense relative to each other.

Once those rules existed, the ML problems felt less artificial because the targets were connected to a system with state and history rather than a flat table assembled only for modeling.

## The first leakage problem

A few early features looked excellent until I asked a basic question: *would I actually know this value at prediction time?*

That removed several same-day and post-outcome fields that were statistically useful but operationally impossible. I eventually moved those exclusions into explicit feature contracts instead of relying on memory inside each training script.

That change probably influenced the project more than any model choice.

## Why the demand model became a hurdle model

Daily product demand is sparse. A single regressor can look reasonable while mostly learning that many rows are zero.

I tried baselines, Poisson regression, and gradient boosting before separating the task into occurrence and magnitude. The final model asks whether demand is positive first and only predicts a positive amount when the occurrence probability clears a frozen threshold.

The improvement mattered, but the more interesting part was understanding *why* the architecture matched the shape of the data better than another round of parameter tuning.

## The result I decided not to hide

Delivery V1 was weak. Its PR-AUC stayed close to prevalence even when the modeling pipeline was behaving correctly.

My first instinct was to keep searching for a better model. The more useful answer was that the synthetic generator had created outcomes with very little relationship to the leakage-safe variables available at shipment time.

I kept the V1 result in the repository. Then I created Delivery V2 as a separate benchmark where carrier, service level, warehouse pressure, and calendar effects actually influence risk. The validation and frozen-test process was rerun from the beginning.

Keeping V1 is important to me because it shows a failure in the data-generating process instead of rewriting history after the model underperformed.

## Why the test set has guards around it

I found it too easy in local experiments to rerun a test script, look at the number, make a small change, and slowly turn the test set into validation without admitting it.

So I made the workflow slightly annoying on purpose. Final evaluation requires a clean source state, frozen artifacts, matching feature contracts, and no existing final-test result. The code refuses a second run for the same frozen experiment.

It is more ceremony than a small synthetic project strictly needs, but building the guard taught me more than simply writing “do not tune on test” in a note.

## Adding the platform layer

After the batch and ML path was stable, I wanted to see how the same artifacts would behave inside a broader system.

That is why the repository later gained dbt, FastAPI, MLflow, Redpanda, PySpark, Docker, and Tableau. I tried to keep these additions connected to an actual data path rather than adding isolated tool examples:

- dbt models the same PostgreSQL fulfillment data;
- FastAPI serves the frozen artifacts;
- MLflow records the frozen metrics rather than retraining;
- Redpanda carries FulfillAI order events;
- Spark aggregates those events with checkpoints and watermarks;
- the streaming sink writes operational windows back to PostgreSQL;
- Tableau uses a BI export from the analytical layer.

The Azure Bicep template is the one part I have left as infrastructure code rather than claiming a deployment I have not completed.

## What I would change if I started again

I would design the event model and prediction-time contracts earlier. A lot of later cleanup came from decisions that were easy to make when the project was only a generator but became expensive once SQL, features, and models depended on them.

I would also version synthetic benchmarks from the beginning. Delivery V1/V2 eventually became a useful pattern, but I only adopted that discipline after needing it.

## What I want to explore next

The next step that interests me most is not another model. It is replacing part of the synthetic world with a public operational dataset and seeing which assumptions survive contact with messier data.

I also want to add monitoring around feature distributions and prediction drift, then connect the batch and streaming paths more tightly so the system has one clear operational story instead of two parallel execution modes.
