# FulfillAI SLO Burn-Rate Runbook

## Purpose

This runbook covers FulfillAI HTTP availability SLO burn-rate alerts in the controlled platform environment.

The lab SLO target is 99.9% successful HTTP requests, corresponding to a 0.1% error budget.

## Alerts

### FulfillAIFastSLOBurn

Severity: critical

This alert detects rapid error-budget consumption.

It requires both conditions:

- 1-hour error ratio greater than 1.44%
- 5-minute error ratio greater than 1.44%

The threshold represents a 14.4x burn rate against the 0.1% error budget.

### FulfillAISlowSLOBurn

Severity: warning

This alert detects sustained error-budget consumption.

It requires both conditions:

- 6-hour error ratio greater than 0.60%
- 30-minute error ratio greater than 0.60%

The threshold represents a 6x burn rate against the 0.1% error budget.

## First checks

1. Confirm the alert state and start time in Prometheus or Grafana.
2. Inspect HTTP success and failure rates by handler and status.
3. Check application health and metrics endpoints.
4. Check Deployment desired, updated, ready, and available replica counts.
5. Inspect recent pod restarts and Kubernetes events.
6. Compare the running immutable image with the GitOps desired image.
7. Check the current Argo CD revision and recent GitHub Actions delivery.
8. Correlate the error increase with recent configuration, image, dependency, or infrastructure changes.

## Useful commands

- `kubectl -n fulfillai get deployment fulfillai`
- `kubectl -n fulfillai get pods -o wide`
- `kubectl -n fulfillai get events --sort-by=.lastTimestamp`
- `kubectl -n monitoring get prometheusrule fulfillai-alerts`
- `kubectl -n argocd get application fulfillai`

## Mitigation

Prefer remediation through Git and the normal GitHub Actions and Argo CD delivery path.

Do not use an ad-hoc Deployment patch or manual Helm upgrade as the normal remediation mechanism.

If the alert correlates with a bad release, revert the responsible Git change or restore a previously verified immutable image through GitOps.

If the issue is dependency-related, investigate and restore the dependency before changing application infrastructure.

## Recovery

Recovery evidence should include:

- error ratio below the applicable burn threshold
- alert returned to inactive
- application health endpoint returning HTTP 200
- metrics endpoint returning HTTP 200
- desired replicas equal ready and available replicas
- Argo CD Synced and Healthy
- running immutable image matching GitOps desired state

## Scope

These SLO values are learning-lab objectives and operational validation evidence. They are not claims of historical production availability.
