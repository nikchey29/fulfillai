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
