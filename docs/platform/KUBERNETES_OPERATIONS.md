# FulfillAI Kubernetes Operations

## Scope

This document records the verified local Kubernetes operating model for the FulfillAI API on the `kind-fulfillai-dev` cluster.

The deployment is Helm-managed and runs in the `fulfillai` namespace.

## Verified workload state

- Deployment: `fulfillai`
- Desired replicas: 2
- Ready replicas: 2
- Available replicas: 2
- Service: `fulfillai`
- Service type: `ClusterIP`
- Container port: 8000
- Health endpoint: `/health`
- Metrics endpoint: `/metrics`

## Runtime security

The Kubernetes workload explicitly declares:
- `runAsNonRoot: true`
- `runAsUser: 10001`
- `runAsGroup: 10001`
- `allowPrivilegeEscalation: false`
- Linux capabilities dropped: `ALL`

The live application process was verified as UID `10001` and user `appuser`.

## Reliability evidence

Phase 10F verified rolling replacement and controller self-healing.

- Rolling restart completed successfully.
- Old Pods were replaced.
- Both replicas returned to Ready and Available state.
- One Pod was intentionally deleted.
- The Deployment controller created a replacement Pod.
- Desired, Ready, and Available replicas returned to 2.
- `/health` returned HTTP 200 after recovery.
- `/metrics` returned HTTP 200 after recovery.
- Runtime identity remained UID 10001 after recovery.

## Disruption and scaling controls

- PodDisruptionBudget `fulfillai`
- `minAvailable: 1`
- HorizontalPodAutoscaler `fulfillai`
- minimum replicas: 2
- maximum replicas: 5

HPA scaling behavior depends on a working Kubernetes metrics source.

## RBAC

Verified behavior:
- application ServiceAccount cannot read Secrets
- operations observer ServiceAccount can read workload resources
- operations observer ServiceAccount cannot create Pods

## NetworkPolicy

The chart contains a NetworkPolicy targeting the FulfillAI API workload and TCP port 8000.

The object and selector are verified. Packet-level enforcement is not claimed here because enforcement depends on the cluster CNI implementation.

## Probes

Startup, readiness, and liveness probes use `/health`.

The workload was verified healthy after deployment, rolling restart, and Pod replacement.

## Verification

Run:

`./scripts/platform/verify-kubernetes-runtime.sh`

A successful run ends with:

`KubernetesRuntimeVerification=PASS`

## Boundaries

This phase verifies the local `kind` Kubernetes implementation and Helm chart behavior. It does not claim managed GKE production operation, multi-zone availability, production traffic, or production on-call ownership.
