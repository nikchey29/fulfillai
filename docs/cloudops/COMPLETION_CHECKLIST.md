# CloudOps Completion Checklist - Platform Engineering V2

**Closure snapshot:** [`d8362db`](https://github.com/nikchey29/fulfillai/commit/d8362dbafd87d703f0f8358a792f55b7d7a07dd6). This supersedes the earlier unchecked checklist on the V2 branch. See [V2 overview](V2_OVERVIEW.md) for evidence links and environment boundaries. Completed checks refer to recorded exercises, not a re-run during the documentation refresh.

## Application and container

- [x] FastAPI /health and /metrics exercised
- [x] Frozen-model serving boundary retained
- [x] Docker build and container HEALTHCHECK
- [x] Non-root UID/GID 10001, security context and resource settings
- [x] Exact immutable image digest recorded and delivered

## GCP/Terraform and identity

- [x] Project/billing setup and required APIs
- [x] Custom VPC/subnet and secondary Pod/Service ranges
- [x] Artifact Registry and GKE Autopilot
- [x] Secret Manager resource/IAM work and GCS remote state
- [x] Existing-resource import/state reconciliation and deletion-protection drift review
- [x] Dedicated deployer ServiceAccount and repository-restricted GitHub OIDC/WIF
- [x] Keyless authentication, without a long-lived GCP key in GitHub

## CI and normal GitOps delivery

- [x] Source compile/contracts and pytest
- [x] Terraform fmt/init/validate and Helm lint/render
- [x] Docker build and Trivy HIGH/CRITICAL policy gate
- [x] Artifact Registry publish and keyless read smoke
- [x] Digest resolution, stale-promotion checks and desired-state commit
- [x] Argo CD automated sync/prune/self-heal and rollout verification
- [x] Intentional drift correction observed
- [x] CI builds/promotes; Argo CD deploys; no normal CI helm-upgrade/Deployment patch

## Kubernetes runtime and controls

- [x] GKE API Deployment/Service, ready workload and successful /health /metrics
- [x] Startup/readiness/liveness probes and resource controls
- [x] Runtime UID 10001, dropped capabilities and no privilege escalation
- [x] Local kind HPA object (2-5 replicas), PDB and read-only RBAC checks
- [x] Local application ServiceAccount unable to read Secrets
- [x] NetworkPolicy object and selector/port intent verified
- [x] Local rolling restart/Pod replacement and post-recovery health verified

HPA object verification is not load-tested autoscaling. NetworkPolicy packet-level enforcement is outside the verified claim. Detailed HPA/PDB/RBAC evidence is the [local kind record](../platform/KUBERNETES_OPERATIONS.md).

## Observability, SLO and routing

- [x] kube-prometheus-stack, API metrics and monitoring path verified
- [x] Live PromQL/metric-label validation
- [x] Versioned Grafana SRE dashboard provisioned through ConfigMap/sidecar
- [x] Restart PrometheusRule and runbook metadata
- [x] 99.9% lab-SLO target and 0.1% error budget documented
- [x] Fast burn: 14.4x; 1h and 5m; critical
- [x] Slow burn: 6x; 6h and 30m; warning
- [x] Secret-backed Slack receiver and service=fulfillai route loaded
- [x] Synthetic alert delivered to Slack end to end
- [x] Phase 13 PASS; SLOAlertingGap=CLOSED; AlertmanagerRoutingGap=CLOSED

## Reliability and separate Linux lab

- [x] Deliberate invalid-image drill and ErrImagePull/ImagePullBackOff diagnosis
- [x] Known-good rollback and Argo CD Synced/Healthy recovery
- [x] Self-heal restored after the manual drill
- [x] Incident report, restart runbook and SLO-burn runbook
- [x] Rocky Linux systemd restart/hardening and SELinux enforcing/custom-domain verification
- [x] Linux reboot/persistence verification

## Secondary executed tools - additional lab exposure

- [x] Successful Jenkins CI pipeline
- [x] Ansible Linux configuration and second-run changed=0 idempotency
- [x] Local ELK structured-log ingestion/inspection
- [x] OpenShift native build, Deployment/Service/TLS Route and /health

This is a controlled learning implementation, not an enterprise deployment, SLA or on-call history. Azure/Bicep remains undeployed.
