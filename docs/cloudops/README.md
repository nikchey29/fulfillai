# FulfillAI CloudOps / Platform Engineering V2

Completed controlled platform implementation around the FulfillAI FastAPI service. The Data/ML foundation remains central.

## Read this first

- [Verified architecture and evidence](V2_OVERVIEW.md)
- [Closure checklist](COMPLETION_CHECKLIST.md)
- [Resume-safe claims](RESUME_EVIDENCE.md)
- [SRE and routing](SRE.md)
- [Kubernetes operations: local kind scope](../platform/KUBERNETES_OPERATIONS.md)
- [SELinux: separate Linux lab](../security/SELINUX.md)
- [Restart runbook](../runbooks/FULFILLAI_POD_RESTARTS.md)
- [SLO burn runbook](../runbooks/FULFILLAI_SLO_BURN.md)
- [Bad-release incident](../../incidents/INC-002-bad-release.md)

## Ownership and delivery

Terraform provisions/reconciles GCP resources, including networking, Artifact Registry, GKE Autopilot, identity and remote state. GitHub Actions validates Terraform and Helm, tests/builds/scans the API image, authenticates through OIDC/WIF and promotes an exact digest to Git. Argo CD reconciles Git-backed Helm desired state and owns normal workload deployment.

The normal path is **source -> validated/scanned image -> Artifact Registry -> guarded desired-state commit -> Argo CD -> GKE API**. A successful delivery run is linked in the overview. Do not run a direct Helm upgrade/Deployment patch alongside Argo CD for routine delivery.

## Local source validation

```bash
terraform -chdir=infra/gcp/terraform fmt -check
terraform -chdir=infra/gcp/terraform init -backend=false
terraform -chdir=infra/gcp/terraform validate
helm lint deploy/helm/fulfillai
helm template fulfillai deploy/helm/fulfillai -f deploy/helm/fulfillai/values-gitops.yaml
docker build -f docker/Dockerfile.api -t fulfillai-api:local .
```

These checks validate source/configuration; they do not provision resources or independently prove live runtime state. The implementation is already closed; this presentation refresh does not restart infrastructure.

## Scope

Health/metrics, GitOps recovery, monitoring, burn rules and Secret-backed Slack alert delivery were verified in controlled exercises. Jenkins/Ansible/ELK/OpenShift are secondary hands-on labs. The 99.9% SLO is a lab target. See the overview for synthetic-data, inference, NetworkPolicy and autoscaling boundaries.
