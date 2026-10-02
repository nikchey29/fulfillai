#!/usr/bin/env bash
set -euo pipefail

: "${GCP_PROJECT_ID:?Set GCP_PROJECT_ID before running this script.}"

REGION="${GCP_REGION:-europe-west3}"
IMAGE_REPOSITORY="${REGION}-docker.pkg.dev/${GCP_PROJECT_ID}/fulfillai/fulfillai-api"

echo "== Prometheus / Grafana =="
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts --force-update
helm repo update

helm upgrade --install kube-prometheus-stack   prometheus-community/kube-prometheus-stack   --namespace monitoring   --create-namespace

kubectl rollout status deployment/kube-prometheus-stack-operator   -n monitoring --timeout=5m

kubectl apply -f observability/

kubectl get servicemonitor,prometheusrule -n monitoring

echo "== Resolve current immutable image digest =="
IMAGE_DIGEST="$(gcloud artifacts docker images describe "${IMAGE_REPOSITORY}:latest" --format='value(image_summary.digest)')"
if [[ -z "$IMAGE_DIGEST" ]]; then
  echo "Could not resolve current image digest from Artifact Registry."
  exit 1
fi
echo "Using digest: $IMAGE_DIGEST"

echo "== ArgoCD =="
helm repo add argo https://argoproj.github.io/argo-helm --force-update
helm repo update

helm upgrade --install argocd argo/argo-cd   --namespace argocd   --create-namespace

kubectl rollout status deployment/argocd-server   -n argocd --timeout=5m

sed \
  -e "s/YOUR_GCP_PROJECT_ID/${GCP_PROJECT_ID}/g" \
  -e "s#YOUR_IMAGE_DIGEST#${IMAGE_DIGEST}#g" \
  deploy/argocd/application.yaml | kubectl apply -f -

kubectl get applications -n argocd

echo
echo "CloudOps finishing layer installed."
echo "Grafana: kubectl port-forward svc/kube-prometheus-stack-grafana 3000:80 -n monitoring"
echo "ArgoCD:  kubectl port-forward svc/argocd-server 8080:443 -n argocd"
