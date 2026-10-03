# FulfillAI Container Operations

## Purpose

FulfillAI provides a reusable runtime-inspection command for the API container.
The goal is to make application availability, Docker health, restart behavior,
security controls, resource limits, and recent logs visible from one command.

## Runtime inspection

Run:

```bash
./scripts/platform/inspect-fulfillai-container.sh
```

The inspection reports:

- container identity and architecture
- running state
- Docker health status
- `/health` HTTP status
- `/metrics` HTTP status
- restart policy and restart count
- read-only root filesystem state
- dropped Linux capabilities
- no-new-privileges configuration
- memory, CPU and PID limits
- current Docker resource consumption
- recent application logs

## Reliability configuration

The Compose-managed API uses an on-failure restart policy with a bounded retry count.
Controlled failure testing verified that Docker can recover the workload after a genuine
non-zero container exit.

## Security configuration

The container runs as a non-root user and uses:

- read-only root filesystem
- writable isolated temporary filesystem
- all Linux capabilities dropped
- no-new-privileges
- explicit memory limit
- explicit CPU limit
- explicit PID limit

## Health and metrics

The API exposes:

- `/health` for application health
- `/metrics` for Prometheus-compatible runtime metrics

These endpoints are checked during operational verification and container regression testing.

## Troubleshooting workflow

1. Confirm the container exists and is running.
2. Inspect Docker health status.
3. Test `/health`.
4. Test `/metrics`.
5. Inspect restart count and restart policy.
6. Inspect recent application logs.
7. Inspect runtime resource consumption.
8. Verify container security controls.
