#!/usr/bin/env bash
set -euo pipefail

NAMESPACE="${NAMESPACE:-fulfillai}"
DEPLOYMENT="${DEPLOYMENT:-fulfillai}"
ARGO_NAMESPACE="${ARGO_NAMESPACE:-argocd}"
ARGO_APPLICATION="${ARGO_APPLICATION:-fulfillai}"

echo "== Starting GitOps state =="
kubectl get application "$ARGO_APPLICATION" -n "$ARGO_NAMESPACE" \
  -o jsonpath='{.status.sync.status}{"  "}{.status.health.status}{"\n"}'

echo "== Introduce safe configuration drift =="
kubectl set env deployment/"$DEPLOYMENT" APP_ENV=drift-test -n "$NAMESPACE"

echo "Live APP_ENV immediately after manual change:"
kubectl get deployment "$DEPLOYMENT" -n "$NAMESPACE" \
  -o jsonpath='{.spec.template.spec.containers[0].env[?(@.name=="APP_ENV")].value}{"\n"}'

echo "== Wait for ArgoCD self-heal =="
for _ in {1..30}; do
  VALUE="$(kubectl get deployment "$DEPLOYMENT" -n "$NAMESPACE" \
    -o jsonpath='{.spec.template.spec.containers[0].env[?(@.name=="APP_ENV")].value}')"
  SYNC="$(kubectl get application "$ARGO_APPLICATION" -n "$ARGO_NAMESPACE" \
    -o jsonpath='{.status.sync.status}')"
  HEALTH="$(kubectl get application "$ARGO_APPLICATION" -n "$ARGO_NAMESPACE" \
    -o jsonpath='{.status.health.status}')"

  printf 'APP_ENV=%s  ArgoCD=%s/%s\n' "$VALUE" "$SYNC" "$HEALTH"

  if [[ "$VALUE" == "production" && "$SYNC" == "Synced" ]]; then
    echo "GitOps self-heal verified."
    exit 0
  fi
  sleep 5
done

echo "ArgoCD did not restore the desired configuration within the expected window."
exit 1
