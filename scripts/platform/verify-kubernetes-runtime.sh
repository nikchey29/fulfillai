#!/usr/bin/env bash
set -euo pipefail
NS=fulfillai
DEPLOY=fulfillai
CHART=deploy/helm/fulfillai

kubectl config use-context kind-fulfillai-dev >/dev/null 2>&1
helm lint "$CHART" >/dev/null
helm template fulfillai "$CHART" -n "$NS" >/dev/null
kubectl -n "$NS" rollout status deployment/"$DEPLOY" --timeout=120s >/dev/null

DESIRED="$(kubectl -n "$NS" get deploy "$DEPLOY" -o jsonpath='{.spec.replicas}')"
READY="$(kubectl -n "$NS" get deploy "$DEPLOY" -o jsonpath='{.status.readyReplicas}')"
AVAILABLE="$(kubectl -n "$NS" get deploy "$DEPLOY" -o jsonpath='{.status.availableReplicas}')"
POD="$(kubectl -n "$NS" get pods -l app.kubernetes.io/name=fulfillai -o jsonpath='{.items[0].metadata.name}')"
NONROOT="$(kubectl -n "$NS" get deploy "$DEPLOY" -o jsonpath='{.spec.template.spec.securityContext.runAsNonRoot}')"
UIDCFG="$(kubectl -n "$NS" get deploy "$DEPLOY" -o jsonpath='{.spec.template.spec.securityContext.runAsUser}')"
GIDCFG="$(kubectl -n "$NS" get deploy "$DEPLOY" -o jsonpath='{.spec.template.spec.securityContext.runAsGroup}')"
PRIV="$(kubectl -n "$NS" get deploy "$DEPLOY" -o jsonpath='{.spec.template.spec.containers[0].securityContext.allowPrivilegeEscalation}')"
DROP="$(kubectl -n "$NS" get deploy "$DEPLOY" -o jsonpath='{.spec.template.spec.containers[0].securityContext.capabilities.drop[*]}')"
HEALTH="$(kubectl -n "$NS" exec "$POD" -- python -c 'import urllib.request;print(urllib.request.urlopen("http://127.0.0.1:8000/health",timeout=5).status)' 2>/dev/null || echo 000)"
METRICS="$(kubectl -n "$NS" exec "$POD" -- python -c 'import urllib.request;print(urllib.request.urlopen("http://127.0.0.1:8000/metrics",timeout=5).status)' 2>/dev/null || echo 000)"
RUNTIME_UID="$(kubectl -n "$NS" exec "$POD" -- id -u 2>/dev/null || echo UNKNOWN)"
PDB="$(kubectl -n "$NS" get pdb fulfillai -o jsonpath='{.spec.minAvailable}')"
HPA_MIN="$(kubectl -n "$NS" get hpa fulfillai -o jsonpath='{.spec.minReplicas}')"
HPA_MAX="$(kubectl -n "$NS" get hpa fulfillai -o jsonpath='{.spec.maxReplicas}')"

RESULT=FAIL
if [ "$DESIRED" = 2 ] && [ "$READY" = 2 ] && [ "$AVAILABLE" = 2 ] && [ "$NONROOT" = true ] && [ "$UIDCFG" = 10001 ] && [ "$GIDCFG" = 10001 ] && [ "$PRIV" = false ] && printf '%s\n' "$DROP" | grep -q ALL && [ "$HEALTH" = 200 ] && [ "$METRICS" = 200 ] && [ "$RUNTIME_UID" = 10001 ] && [ "$PDB" = 1 ] && [ "$HPA_MIN" = 2 ] && [ "$HPA_MAX" = 5 ]; then
  RESULT=PASS
fi

printf '%s\n' "KubernetesRuntimeVerification=$RESULT" "Desired=$DESIRED" "Ready=$READY" "Available=$AVAILABLE" "RunAsNonRoot=$NONROOT" "RunAsUser=$UIDCFG" "RunAsGroup=$GIDCFG" "AllowPrivilegeEscalation=$PRIV" "CapabilitiesDrop=$DROP" "HealthHTTP=$HEALTH" "MetricsHTTP=$METRICS" "RuntimeUID=$RUNTIME_UID" "PDBMinAvailable=$PDB" "HPAMin=$HPA_MIN" "HPAMax=$HPA_MAX"
[ "$RESULT" = PASS ]
