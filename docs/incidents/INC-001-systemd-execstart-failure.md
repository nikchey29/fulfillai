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
