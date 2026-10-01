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

- [ ] GCP project selected with billing enabled
- [ ] Terraform apply succeeds
- [ ] VPC/subnet created
- [ ] Artifact Registry created
- [ ] GKE Autopilot cluster created
- [ ] API image pushed to Artifact Registry
- [ ] Helm release installed in GKE
- [ ] pods ready
- [ ] HPA visible
- [ ] /health returns 200
- [ ] /metrics returns Prometheus metrics

## Observability / GitOps

- [ ] kube-prometheus-stack installed
- [ ] ServiceMonitor discovered
- [ ] Prometheus target healthy
- [ ] Grafana dashboard inspected
- [ ] alert rule loaded
- [ ] ArgoCD installed
- [ ] FulfillAI ArgoCD Application synced
- [ ] GitOps self-heal observed

## Reliability / security

- [ ] RBAC objects verified
- [ ] NetworkPolicy verified
- [ ] readiness/liveness probes verified
- [ ] guarded bad-release drill executed
- [ ] rollback succeeds
- [ ] INC-002 incident template completed

## Secondary JD tools

- [ ] Jenkins pipeline executed
- [ ] Ansible playbook executed against a Linux host
- [ ] OpenShift workload + Route verified
- [ ] centralized logging exercise completed (ELK or Datadog)

Only completed items should be described as completed hands-on work on the resume.
