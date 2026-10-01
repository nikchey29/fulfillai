# Bad Release / Image Failure

## Detect

```bash
kubectl get pods -n fulfillai
kubectl get events -n fulfillai --sort-by=.lastTimestamp
kubectl describe pod -n fulfillai POD_NAME
```

## Roll back

```bash
kubectl rollout history deployment/fulfillai -n fulfillai
kubectl rollout undo deployment/fulfillai -n fulfillai
kubectl rollout status deployment/fulfillai -n fulfillai
```

Record detection, impact, root cause, rollback, verification, and preventive action.
