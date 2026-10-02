#!/usr/bin/env bash
set -euo pipefail

NAMESPACE="${NAMESPACE:-fulfillai}"
DEPLOYMENT="${DEPLOYMENT:-fulfillai}"
ARGO_NAMESPACE="${ARGO_NAMESPACE:-argocd}"
ARGO_APPLICATION="${ARGO_APPLICATION:-fulfillai}"

if [[ "${CONFIRM_FAILURE_DRILL:-}" != "YES" ]]; then
  echo "This intentionally creates a failed rollout in the FulfillAI lab."
  echo "Run again with: CONFIRM_FAILURE_DRILL=YES bash scripts/cloudops_failure_drill.sh"
  exit 1
fi

restore_gitops() {
  kubectl patch application "$ARGO_APPLICATION" -n "$ARGO_NAMESPACE" \
    --type merge \
    -p '{"spec":{"syncPolicy":{"automated":{"prune":true,"selfHeal":true}}}}' \
    >/dev/null 2>&1 || true
}
trap restore_gitops EXIT

echo "== Healthy starting state =="
kubectl rollout status "deployment/${DEPLOYMENT}" -n "$NAMESPACE" --timeout=5m
kubectl get application "$ARGO_APPLICATION" -n "$ARGO_NAMESPACE" \
  -o jsonpath='{.status.sync.status}{"  "}{.status.health.status}{"\n"}'

echo "== Temporarily pause ArgoCD self-heal for manual rollback exercise =="
kubectl patch application "$ARGO_APPLICATION" -n "$ARGO_NAMESPACE" \
  --type merge \
  -p '{"spec":{"syncPolicy":{"automated":{"prune":true,"selfHeal":false}}}}'

echo "== Inject bad image =="
kubectl set image "deployment/${DEPLOYMENT}" \
  fulfillai=does-not-exist.invalid/fulfillai:broken \
  -n "$NAMESPACE"

sleep 15

echo "== Diagnose =="
kubectl get pods -n "$NAMESPACE" || true
kubectl get events -n "$NAMESPACE" --sort-by=.lastTimestamp | tail -n 30 || true

echo "== Roll back manually =="
kubectl rollout undo "deployment/${DEPLOYMENT}" -n "$NAMESPACE"
kubectl rollout status "deployment/${DEPLOYMENT}" -n "$NAMESPACE" --timeout=5m

echo "== Re-enable ArgoCD self-heal =="
restore_gitops

echo "== Recovery state =="
kubectl get pods -n "$NAMESPACE"
kubectl get application "$ARGO_APPLICATION" -n "$ARGO_NAMESPACE" \
  -o jsonpath='{.status.sync.status}{"  "}{.status.health.status}{"\n"}'

echo "Failure drill completed. Record detection, impact, diagnosis, rollback, verification, and prevention in incidents/INC-002-bad-release.md."
