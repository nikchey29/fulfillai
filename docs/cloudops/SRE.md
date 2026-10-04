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

Alert metadata includes severity, service ownership, a human-readable description, and a runbook URL. SLO-based alerting and Alertmanager routing are handled as separate validation phases so routing is not claimed until a real receiver is configured and tested.

## Multi-window burn-rate alerting

FulfillAI uses two HTTP error-budget burn alerts for the 99.9% lab SLO.

`FulfillAIFastSLOBurn` uses a 14.4x burn threshold and requires both a 1-hour and 5-minute breach.

`FulfillAISlowSLOBurn` uses a 6x burn threshold and requires both a 6-hour and 30-minute breach.

Both alerts are stored in the application Helm chart and delivered through the GitOps path. Alertmanager notification routing remains a separate requirement and is not considered complete until a real receiver is configured and tested.


## Slack notification routing

FulfillAI alert notifications use an AlertmanagerConfig resource delivered through the application Helm chart and Argo CD.

The Slack incoming webhook itself is not stored in Git. It is bootstrapped as the `fulfillai-slack-webhook` Kubernetes Secret in the `fulfillai` namespace, and the AlertmanagerConfig references only the Secret name and key.

The Alertmanager route selects alerts with `service=fulfillai`. FulfillAI SLO expressions retain the `namespace` label so the Prometheus Operator namespace-matching safety model can route them correctly.

Notification routing is considered verified only when Alertmanager has loaded the receiver and a synthetic FulfillAI alert produces a successful Slack notification without increasing the failed-notification counter.
