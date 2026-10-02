# INC-002 — Bad Release Rollback

Status: COMPLETED LAB INCIDENT

## Summary

A controlled deployment failure was injected into the FulfillAI GKE environment by replacing the application image with the intentionally invalid image `does-not-exist.invalid/fulfillai:broken`.

The new rollout failed with `ErrImagePull` / `ImagePullBackOff`. Existing healthy replicas continued serving while the failed replacement pod could not retrieve the image.

## Detection

The failure was detected through Kubernetes rollout status, pod state, and cluster events.

Observed signals included:
- `ErrImagePull`
- `ImagePullBackOff`
- failed image pull for `does-not-exist.invalid/fulfillai:broken`
- DNS resolution failure / `no such host`

## Impact

The replacement pod failed to start, but existing healthy FulfillAI replicas remained available during the exercise.

## Timeline

1. Verified the healthy starting Deployment.
2. Temporarily disabled ArgoCD self-heal for the manual rollback exercise.
3. Injected the invalid container image.
4. Observed the failed rollout and Kubernetes events.
5. Performed `kubectl rollout undo`.
6. Verified the Deployment rolled out successfully.
7. Re-enabled ArgoCD self-heal.
8. Confirmed ArgoCD returned to `Synced / Healthy`.

## Root cause

The deployment referenced an intentionally invalid container image hostname. Kubernetes could not resolve or pull the image, which caused the replacement pod to enter `ErrImagePull` and then `ImagePullBackOff`.

## Rollback

Executed:

```bash
kubectl rollout undo deployment/fulfillai -n fulfillai
kubectl rollout status deployment/fulfillai -n fulfillai --timeout=5m
```

The previous known-good deployment revision was restored successfully.

## Verification

Post-recovery evidence:
- FulfillAI Deployment successfully rolled out.
- Healthy application replicas returned to `1/1 Running`.
- ArgoCD reported `Synced / Healthy`.
- ArgoCD self-heal was re-enabled after the manual rollback exercise.

## Preventive actions

- Continue using immutable image digests for production-style deployments.
- Preserve readiness/liveness probes so failed replicas do not receive traffic.
- Keep automated GitOps reconciliation enabled during normal operation.
- Maintain deployment runbooks and capture Kubernetes event output during incidents.
- Use CI image validation and vulnerability scanning before release.

## Evidence

Commands used during the exercise included:

```bash
kubectl get pods -n fulfillai
kubectl get events -n fulfillai --sort-by=.lastTimestamp
kubectl rollout undo deployment/fulfillai -n fulfillai
kubectl rollout status deployment/fulfillai -n fulfillai --timeout=5m
kubectl get application fulfillai -n argocd
```
