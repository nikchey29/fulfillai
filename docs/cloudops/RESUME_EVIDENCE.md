# Resume Evidence Gate

> **Version note:** This file records the earlier `main` implementation baseline. The completed Platform Engineering V2 evidence supersedes its open-status wording; start with [V2 overview](V2_OVERVIEW.md) and the linked V2 implementation. V2 has not been merged into `main`.

| Claim | Minimum evidence |
|---|---|
| Terraform/GCP | terraform plan plus successful apply/resources |
| GKE/Kubernetes | running pods/service plus successful /health |
| Helm | successful Helm release |
| ArgoCD | application exists and sync succeeds |
| Prometheus/Grafana | FulfillAI application metrics visible |
| SRE troubleshooting | completed failure drill and recovery |
| Jenkins | actual Jenkins pipeline run |
| Ansible | playbook executed against a host |
| OpenShift | workload and Route running |

After the core deployment is verified:

> Extended FulfillAI into a cloud-native GCP/GKE deployment using Terraform, Kubernetes, Helm and GitOps, with GitHub Actions CI, Prometheus/Grafana observability, RBAC/network controls, autoscaling and documented failure/rollback exercises.

Do not claim enterprise production traffic, 24/7 on-call ownership, or measured cost/reliability improvements without evidence.
