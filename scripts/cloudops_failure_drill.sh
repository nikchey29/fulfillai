#!/usr/bin/env bash
set -euo pipefail

NAMESPACE="${NAMESPACE:-fulfillai}"
DEPLOYMENT="${DEPLOYMENT:-fulfillai}"

if [[ "${CONFIRM_FAILURE_DRILL:-}" != "YES" ]]; then
  echo "This intentionally creates a failed rollout in the FulfillAI lab."
  echo "Run again with: CONFIRM_FAILURE_DRILL=YES bash scripts/cloudops_failure_drill.sh"
  exit 1
fi

echo "== Healthy starting state =="
kubectl rollout status "deployment/${DEPLOYMENT}"   -n "$NAMESPACE" --timeout=5m

echo "== Inject bad image =="
kubectl set image "deployment/${DEPLOYMENT}"   fulfillai=does-not-exist.invalid/fulfillai:broken   -n "$NAMESPACE"

sleep 10

echo "== Diagnose =="
kubectl get pods -n "$NAMESPACE" || true
kubectl get events -n "$NAMESPACE"   --sort-by=.lastTimestamp | tail -n 25 || true

echo "== Roll back =="
kubectl rollout undo "deployment/${DEPLOYMENT}" -n "$NAMESPACE"
kubectl rollout status "deployment/${DEPLOYMENT}"   -n "$NAMESPACE" --timeout=5m

echo "== Recovery state =="
kubectl get pods -n "$NAMESPACE"
