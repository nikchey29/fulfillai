# Resume-safe evidence map

The completed V2 implementation is independent engineering and a controlled GCP/GKE platform lab. See [V2 overview](V2_OVERVIEW.md) for the closure snapshot, successful CI run and exact source links.

| Safe claim | Evidence | Limit |
|---|---|---|
| Built a synthetic 50K-order data/ML platform; demand WAPE 88.24% -> 69.59% | [Results](../results.md), frozen chronological evaluation | Synthetic benchmark, not a real customer outcome |
| Provisioned GCP/GKE with Terraform and reconciled live resources/state | infra/gcp/terraform; recorded closure | Controlled lab, no enterprise fleet ownership |
| Automated keyless CI using Actions OIDC/WIF, scanning and exact digest promotion | [Delivery run](https://github.com/nikchey29/fulfillai/actions/runs/37233814366); .github/workflows/cloudops.yml | Trivy uses its configured severity/exception policy; not a zero-vulnerability claim |
| Delivered Helm desired state through Argo CD sync/prune/self-heal | deploy/argocd and values-gitops.yaml; successful rollout and drift drill | CI owns build/promotion; Argo CD owns deployment |
| Verified Prometheus/Grafana and Alertmanager-to-Slack delivery | observability; chart dashboard/rules/routing; Phase 13 synthetic alert | 99.9% is a lab SLO target, not observed uptime or an SLA |
| Diagnosed ImagePullBackOff and verified rollback/recovery | incidents/INC-002-bad-release.md and runbooks | Deliberate lab incident, not customer outage/on-call experience |
| Verified Kubernetes HPA/PDB/RBAC objects and permissions | docs/platform/KUBERNETES_OPERATIONS.md | Detailed proof is local kind; no load-tested GKE autoscaling |
| Configured NetworkPolicy | Object/selector verification in the local record | Packet-level enforcement not proved |
| Practised Linux/systemd/SELinux | docs/security/SELINUX.md; separate Rocky lab | Custom policy and hardening exercise, not audited enterprise security |
| Used Jenkins, Ansible, ELK and OpenShift | Successful CI; changed=0; local logs; TLS Route /health | Additional hands-on exposure, not expert production ownership |

## Suggested project description

> Built forecasting and risk pipelines for a synthetic 50K-order e-commerce platform, then extended its API into a verified Terraform/GCP/GKE lab with keyless CI, immutable Argo CD GitOps delivery, Prometheus/Grafana, lab-SLO alerting and documented recovery drills.

Never claim enterprise traffic, millions of served users, historical 99.9% availability, an SLA, 24/7 on-call, years of professional DevOps, or measured cost/reliability improvement without separate evidence. API health/metrics verification does not establish every model's inference or all data services running in GKE.
