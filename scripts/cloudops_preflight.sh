#!/usr/bin/env bash
set -euo pipefail

required=(git docker gcloud terraform kubectl helm curl)
optional=(argocd ansible trivy)

echo "FulfillAI CloudOps preflight"
echo "============================"

missing=0
for cmd in "${required[@]}"; do
  if command -v "$cmd" >/dev/null 2>&1; then
    printf "OK   %-12s %s\n" "$cmd" "$(command -v "$cmd")"
  else
    printf "MISS %-12s\n" "$cmd"
    missing=1
  fi
done

echo
echo "Optional tooling"
for cmd in "${optional[@]}"; do
  if command -v "$cmd" >/dev/null 2>&1; then
    printf "OK   %-12s %s\n" "$cmd" "$(command -v "$cmd")"
  else
    printf "INFO %-12s not installed yet\n" "$cmd"
  fi
done

if [[ "$missing" -ne 0 ]]; then
  echo
  echo "Install the missing required tools before deployment."
  exit 1
fi

if ! docker info >/dev/null 2>&1; then
  echo "Docker is installed but the daemon is not running."
  exit 1
fi

echo
echo "Terraform validation"
terraform -chdir=infra/gcp/terraform fmt -recursive
terraform -chdir=infra/gcp/terraform init -backend=false
terraform -chdir=infra/gcp/terraform validate

echo
echo "Helm validation"
helm lint deploy/helm/fulfillai
helm template fulfillai deploy/helm/fulfillai \
  --namespace fulfillai \
  --set image.repository=example.invalid/fulfillai-api \
  --set image.tag=validation >/tmp/fulfillai-rendered.yaml

echo
echo "Docker build validation"
docker build -f docker/Dockerfile.api -t fulfillai-api:preflight .

echo
echo "Preflight complete."
