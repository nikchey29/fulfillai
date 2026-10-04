# FulfillAI CloudOps Extension

> **Version note:** This file records the earlier `main` implementation baseline. The completed Platform Engineering V2 evidence supersedes its open-status wording; start with [V2 overview](V2_OVERVIEW.md) and the linked V2 implementation. V2 has not been merged into `main`.

FulfillAI includes a GCP/GKE CloudOps extension for cloud, DevOps, observability, security, and SRE practice.

## Architecture

GitHub Actions -> Docker API image -> Artifact Registry -> GKE -> Helm -> ArgoCD

Terraform provisions:
- required GCP APIs
- VPC and subnet
- Artifact Registry
- GKE Autopilot

Helm/Kubernetes provides:
- Deployment and Service
- readiness/liveness probes
- non-root execution
- resource requests/limits
- HPA
- NetworkPolicy
- read-only operational RBAC role

Observability:
- FastAPI /metrics
- Prometheus ServiceMonitor
- Grafana via kube-prometheus-stack
- restart alert

## Local validation

```bash
terraform -chdir=infra/gcp/terraform init -backend=false
terraform -chdir=infra/gcp/terraform validate
helm lint deploy/helm/fulfillai
helm template fulfillai deploy/helm/fulfillai >/tmp/fulfillai.yaml
docker build -f docker/Dockerfile.api -t fulfillai-api:local .
```

## GCP deployment

```bash
cd infra/gcp/terraform
cp terraform.tfvars.example terraform.tfvars
# set your actual project ID
terraform init
terraform plan
terraform apply
```

Then configure GKE, push the API image to Artifact Registry, and install the chart with Helm.

Do not describe a component as deployed until its verification succeeds.
