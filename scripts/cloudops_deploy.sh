#!/usr/bin/env bash
set -euo pipefail

: "${GCP_PROJECT_ID:?Set GCP_PROJECT_ID before running this script.}"

REGION="${GCP_REGION:-europe-west3}"
CLUSTER_NAME="${GKE_CLUSTER_NAME:-fulfillai-gke}"
IMAGE_TAG="${IMAGE_TAG:-$(git rev-parse --short HEAD)}"
REPOSITORY="fulfillai"
IMAGE_REPOSITORY="${REGION}-docker.pkg.dev/${GCP_PROJECT_ID}/${REPOSITORY}/fulfillai-api"
TF_DIR="infra/gcp/terraform"

if ! command -v gcloud >/dev/null 2>&1; then
  echo "gcloud is required."
  exit 1
fi

if [[ -z "$(gcloud auth list --filter=status:ACTIVE --format='value(account)' | head -n 1)" ]]; then
  echo "No active gcloud account. Run: gcloud auth login"
  exit 1
fi

echo "== Project =="
gcloud config set project "$GCP_PROJECT_ID"

cat >"${TF_DIR}/terraform.tfvars" <<EOF
project_id   = "$GCP_PROJECT_ID"
region       = "$REGION"
cluster_name = "$CLUSTER_NAME"
EOF

echo "== Terraform =="
terraform -chdir="$TF_DIR" init
terraform -chdir="$TF_DIR" fmt -recursive
terraform -chdir="$TF_DIR" validate
terraform -chdir="$TF_DIR" plan -out=tfplan
terraform -chdir="$TF_DIR" apply tfplan

echo "== GKE credentials =="
gcloud container clusters get-credentials "$CLUSTER_NAME" \
  --region "$REGION" \
  --project "$GCP_PROJECT_ID"

kubectl get nodes

echo "== Artifact Registry authentication =="
gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet

echo "== Build and push API image =="
docker build -f docker/Dockerfile.api -t "${IMAGE_REPOSITORY}:${IMAGE_TAG}" .
docker tag "${IMAGE_REPOSITORY}:${IMAGE_TAG}" "${IMAGE_REPOSITORY}:latest"
docker push "${IMAGE_REPOSITORY}:${IMAGE_TAG}"
docker push "${IMAGE_REPOSITORY}:latest"

echo "== Helm deployment =="
helm upgrade --install fulfillai deploy/helm/fulfillai \
  --namespace fulfillai \
  --create-namespace \
  --set image.repository="$IMAGE_REPOSITORY" \
  --set image.tag="$IMAGE_TAG"

kubectl rollout status deployment/fulfillai -n fulfillai --timeout=5m
kubectl get pods,svc,hpa -n fulfillai

echo "== Health and metrics smoke check =="
kubectl port-forward service/fulfillai 18000:80 -n fulfillai >/tmp/fulfillai-port-forward.log 2>&1 &
PF_PID=$!
trap 'kill "$PF_PID" >/dev/null 2>&1 || true' EXIT

for _ in {1..30}; do
  if curl --fail --silent http://127.0.0.1:18000/health >/tmp/fulfillai-health.json; then
    break
  fi
  sleep 2
done

cat /tmp/fulfillai-health.json
curl --fail --silent http://127.0.0.1:18000/metrics | head -n 10

echo
echo "Deployment verified."
echo "Image: ${IMAGE_REPOSITORY}:${IMAGE_TAG}"
echo "Next: install monitoring and ArgoCD using docs/cloudops/README.md."
