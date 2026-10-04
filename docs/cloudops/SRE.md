# SRE Lab Notes

## SLI

Successful HTTP requests divided by total HTTP requests.

## SLO

Lab target: 99.9% successful requests over the selected evaluation window.

## Error budget

0.1% unsuccessful requests over the same window.

These are learning-lab objectives, not historical production guarantees.

## Required exercises
- failed image rollout and rollback
- pod restart investigation
- readiness/liveness behavior
- database-unavailable runbook review
- metrics and alert inspection

## Alerting and incident response

FulfillAI alert rules are delivered through the application Helm chart and reconciled by Argo CD so alerting configuration follows the same GitOps ownership model as the workload.

The current restart alert is `FulfillAIHighPodRestartRate`. Its response procedure is documented in `docs/runbooks/FULFILLAI_POD_RESTARTS.md`.

Alert metadata includes severity, service ownership, a human-readable description, and a runbook URL. SLO-based alerting and Alertmanager routing were completed as separate validation phases. Phase 13 recorded PASS and both gaps CLOSED after a synthetic FulfillAI alert reached the Secret-backed Slack receiver.

## Multi-window burn-rate alerting

FulfillAI uses two HTTP error-budget burn alerts for the 99.9% lab SLO.

`FulfillAIFastSLOBurn` uses a 14.4x burn threshold and requires both a 1-hour and 5-minute breach.

`FulfillAISlowSLOBurn` uses a 6x burn threshold and requires both a 6-hour and 30-minute breach.

Both alerts are stored in the application Helm chart and delivered through the GitOps path. Alertmanager notification routing is complete in the lab: the receiver was loaded and a synthetic alert reached Slack. This proves the routing path, not historical production availability.


## Slack notification routing

FulfillAI alert notifications use an AlertmanagerConfig resource delivered through the application Helm chart and Argo CD.

The Slack incoming webhook itself is not stored in Git. It is bootstrapped as the `fulfillai-slack-webhook` Kubernetes Secret in the `fulfillai` namespace, and the AlertmanagerConfig references only the Secret name and key.

The Alertmanager route selects alerts with `service=fulfillai`. FulfillAI SLO expressions retain the `namespace` label so the Prometheus Operator namespace-matching safety model can route them correctly.

Notification routing is considered verified only when Alertmanager has loaded the receiver and a synthetic FulfillAI alert produces a successful Slack notification without increasing the failed-notification counter.

## Closure and metric scope

See [V2 overview](V2_OVERVIEW.md) for closure commit/run links. The SLI's implemented success criterion is HTTP 2xx divided by all instrumented request rates, aggregated by namespace. It includes the instrumented namespace traffic and is not restricted to business prediction endpoints. Fast burn uses 0.0144 error ratio with a 2m persistence; slow burn uses 0.006 with a 10m persistence. Both windows must breach. The restart rule is more than two container restarts in 15m, persisting for 5m.

The dashboard is version-controlled at `deploy/helm/fulfillai/dashboards/fulfillai-sre-overview.json` and provisioned through a labeled ConfigMap/Grafana sidecar. Namespace labels are retained in SLO expressions for Operator routing. The Slack webhook value remains outside Git; only its Secret name/key is referenced.
