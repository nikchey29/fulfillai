# FulfillAI Pod Restart Runbook

## Alert

`FulfillAIHighPodRestartRate`

## Purpose

This runbook is for the FulfillAI learning/platform environment when Kubernetes reports repeated container restarts in the `fulfillai` namespace.

The alert fires when the restart counter increases by more than two within 15 minutes and that condition remains true for 5 minutes.

## Expected impact

Repeated restarts can reduce available capacity, delay rollouts, hide application failures behind controller retries, or indicate probe, dependency, resource, or image problems.

## First checks

1. Confirm the alert is current and identify the affected pod and container.
2. Check Deployment rollout state and replica health.
3. Inspect pod status, restart count, recent Kubernetes events, and the previous container log.
4. Check readiness and liveness probe failures.
5. Compare the running immutable image digest with the GitOps desired state.
6. Check recent Argo CD sync history and the commit that introduced the active image or configuration.

## Useful commands

```bash
kubectl -n fulfillai get deployment fulfillai
kubectl -n fulfillai get pods -l app.kubernetes.io/name=fulfillai -o wide
kubectl -n fulfillai describe pod POD_NAME
kubectl -n fulfillai logs POD_NAME -c fulfillai --previous
kubectl -n fulfillai get events --sort-by=.lastTimestamp
kubectl -n argocd get application fulfillai
```

## Investigation guide

Check for these common causes:

- application exception during startup
- failed dependency or database connectivity
- readiness or liveness probe failures
- CPU or memory pressure
- invalid environment/configuration
- bad immutable image release
- repeated rollout or controller reconciliation
- node or scheduling instability

Correlate the restart time with Grafana, Prometheus, Kubernetes events, Argo CD history, and the Git
commit history before deciding on remediation.

## Mitigation

Prefer GitOps remediation. Correct the source configuration or image reference in Git and allow the normal GitHub Actions and Argo CD path to reconcile the cluster.

Do not use an ad-hoc direct Deployment patch or manual Helm upgrade as the normal incident fix. Emergency manual action should be documented separately and followed by reconciliation back to Git.

If the most recent release is confirmed bad, revert the responsible Git change or restore the previously verified immutable image through the GitOps path.

## Recovery verification

Recovery is complete only when:

- the Deployment is fully available
- replacement pods remain Ready
- restart counts stop increasing
- `/health` returns HTTP 200
- `/metrics` returns HTTP 200
- Argo CD reports `Synced` and `Healthy`
- the alert returns to inactive/resolved
- the running image matches GitOps desired state

## Evidence to capture

Record:

- alert start and resolution time
- affected pod/container
- restart count
- relevant Kubernetes events
- previous container log excerpt
- active image digest
- Argo CD revision
- Git source commit
- mitigation/revert commit, if any
- final health and alert state

## Escalation

Escalate when restarts continue after rollback/reconciliation, multiple replicas fail simultaneously, the service cannot maintain healthy capacity, or the cause involves infrastructure outside the application team's control.

## Scope note

This runbook documents a controlled learning/platform environment. SLO and alert results from this environment are operational test evidence, not claims of historical production availability.
