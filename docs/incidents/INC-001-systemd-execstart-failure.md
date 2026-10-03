# INC-001 — FulfillAI systemd ExecStart Failure

## Summary

A controlled Linux service incident was introduced by changing the
FulfillAI systemd unit's `ExecStart` directive from the valid Uvicorn
executable to a nonexistent executable.

The failure made the API unavailable and caused systemd to repeatedly
attempt automatic recovery because `Restart=on-failure` was configured.

## Environment

- OS: Rocky Linux 9.8
- Architecture: aarch64
- Runtime: Python 3.11 virtual environment
- Application: FulfillAI FastAPI
- Application server: Uvicorn
- Service manager: systemd
- Service account: `fulfillai`
- Application endpoint: `127.0.0.1:8000`

## Healthy State

Before failure injection:

- `fulfillai.service` was active and running.
- The service was enabled for boot.
- Uvicorn was listening on `127.0.0.1:8000`.
- `/health` returned HTTP 200.
- `/metrics` returned Prometheus metrics.

## Failure Injection

The valid executable:

`/opt/fulfillai/venv/bin/uvicorn`

was intentionally changed to:

`/opt/fulfillai/venv/bin/uvicorn-broken`

The updated unit was loaded and restarted:

```bash
sudo systemctl daemon-reload
sudo systemctl restart fulfillai

## Symptoms

The FulfillAI health endpoint became unavailable.

Observed result:

`curl: (7) Failed to connect to 127.0.0.1 port 8000: Connection refused`

No process was listening on TCP port 8000.

## Service State

During the incident, systemd reported:

- `Result=exit-code`
- `ExecMainCode=1`
- `ExecMainStatus=203`
- `ActiveState=activating`
- `SubState=auto-restart`

The service was configured with `Restart=on-failure` and `RestartSec=3`.

Because the configuration error persisted, systemd repeatedly attempted to restart the service. The journal eventually showed the restart counter reaching 145 before the loop was stopped.

## Investigation

`systemctl status fulfillai` showed `status=203/EXEC`.

The systemd journal reported:

`Failed to locate executable /opt/fulfillai/venv/bin/uvicorn-broken: No such file or directory`

and:

`Failed at step EXEC spawning /opt/fulfillai/venv/bin/uvicorn-broken: No such file or directory`

The configured executable was checked with:

`grep '^ExecStart=' /etc/systemd/system/fulfillai.service`

The invalid executable was confirmed absent with:

`ls -l /opt/fulfillai/venv/bin/uvicorn-broken`

The valid executable still existed at:

`/opt/fulfillai/venv/bin/uvicorn`

## Root Cause

The systemd `ExecStart` directive referenced a nonexistent executable.

Systemd therefore failed during the EXEC stage with `status=203/EXEC`.

Because `Restart=on-failure` was enabled, the persistent configuration error also caused a restart loop.

## Resolution

The restart loop was first stopped with:

`sudo systemctl stop fulfillai`

The known-good service definition was restored from:

`/etc/systemd/system/fulfillai.service.good`

Systemd was then refreshed and the service restarted using:

- `sudo systemctl daemon-reload`
- `sudo systemctl reset-failed fulfillai`
- `sudo systemctl start fulfillai`

## Recovery Verification

After recovery, systemd reported:

- `ActiveState=active`
- `SubState=running`
- `Result=success`
- `NRestarts=0`
- `MainPID=2806`

The Uvicorn process was running again under the `fulfillai` service account.

TCP port 8000 was listening again.

The `/health` endpoint returned HTTP 200.

The `/metrics` endpoint returned Prometheus metrics.

Recovery was verified across multiple layers:

1. systemd service state
2. Uvicorn process
3. TCP listening socket
4. FastAPI health endpoint
5. Prometheus metrics
6. systemd journal logs

## Prevention

Potential improvements include:

- Validate systemd unit files before deployment.
- Verify `ExecStart` executables before restarting services.
- Maintain rollback-ready configurations.
- Perform automated post-deployment health checks.
- Monitor service and endpoint availability.
- Add systemd start-rate limiting.
- Test service configuration changes before release.

## Key Learning

The incident demonstrated a layered troubleshooting workflow:

1. Confirm the user-facing failure.
2. Check whether the expected TCP socket exists.
3. Inspect systemd service state.
4. Examine the systemd exit code.
5. Inspect journal logs.
6. Validate the configured `ExecStart`.
7. Verify referenced filesystem resources.
8. Restore the known-good configuration.
9. Verify recovery at service, process, network, application, and observability layers.

The incident also demonstrated that automatic restart policies cannot repair persistent configuration errors.
