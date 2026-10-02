#!/usr/bin/env bash
set -euo pipefail

PROJECT="${OPENSHIFT_PROJECT:-fulfillai-dev}"

if ! command -v oc >/dev/null 2>&1; then
  echo "OpenShift CLI 'oc' is required. On macOS: brew install openshift-cli"
  exit 1
fi

if ! oc whoami >/dev/null 2>&1; then
  echo "Not logged in to an OpenShift cluster."
  echo "Use the login command supplied by your OpenShift cluster / Developer Sandbox."
  exit 1
fi

echo "== Project =="
oc new-project "$PROJECT" >/dev/null 2>&1 || oc project "$PROJECT"

echo "== Native OpenShift build =="
oc apply -f ops/openshift/buildconfig.yaml
oc start-build fulfillai-api --follow --wait

echo "== Application =="
if ! oc get deployment fulfillai >/dev/null 2>&1; then
  oc new-app --image-stream=fulfillai-api:latest --name=fulfillai
fi

oc set env deployment/fulfillai APP_ENV=production LOG_LEVEL=INFO
oc set probe deployment/fulfillai --readiness --get-url=http://:8000/health   --initial-delay-seconds=5 --period-seconds=10
oc set probe deployment/fulfillai --liveness --get-url=http://:8000/health   --initial-delay-seconds=15 --period-seconds=20

echo "== Route =="
oc apply -f ops/openshift/route.yaml

echo "== Rollout =="
oc rollout status deployment/fulfillai --timeout=5m
oc get pods,svc,route

HOST="$(oc get route fulfillai -o jsonpath='{.spec.host}')"
echo
echo "Route: https://$HOST"
echo "Health check:"
curl --fail --silent --show-error "https://$HOST/health"
echo
echo "OpenShift deployment verified."
