# CloudOps Completion Checklist

## Already verified in GitHub Actions

- [x] Existing FulfillAI source contracts
- [x] Existing test suite
- [x] Terraform initialization
- [x] Terraform validation
- [x] Helm lint
- [x] Helm manifest rendering
- [x] API container build
- [x] Trivy HIGH/CRITICAL image scan execution
- [x] FastAPI Prometheus instrumentation added
- [x] non-root API container configuration

## Live GCP/GKE evidence

- [x] GCP project selected with billing enabled
- [x] Terraform apply succeeds
- [x] VPC/subnet created
- [x] Artifact Registry created
- [x] GKE Autopilot cluster created
- [x] API image pushed to Artifact Registry
- [x] Helm release installed in GKE
- [x] pods ready
- [x] Immutable digest-pinned rollout verified
- [ ] HPA visible
- [x] /health returns 200
- [x] /metrics returns Prometheus metrics

## Observability / GitOps

- [x] kube-prometheus-stack installed
- [ ] ServiceMonitor discovered
- [ ] Prometheus target healthy
- [ ] Grafana dashboard inspected
- [ ] alert rule loaded
- [x] ArgoCD installed
- [x] FulfillAI ArgoCD Application synced
- [x] GitOps self-heal observed

## Reliability / security

- [ ] RBAC objects verified
- [ ] NetworkPolicy verified
- [x] readiness/liveness probes verified
- [x] guarded bad-release drill executed
- [x] rollback succeeds
- [x] INC-002 incident template completed

## Secondary JD tools

- [ ] Jenkins pipeline executed
- [ ] Ansible playbook executed against a Linux host
- [ ] OpenShift workload + Route verified
- [ ] centralized logging exercise completed (ELK or Datadog)

Only completed items should be described as completed hands-on work on the resume.
