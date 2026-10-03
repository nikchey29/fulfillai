# FulfillAI systemd Deployment

This directory contains the systemd configuration used to operate the
FulfillAI FastAPI service on Rocky Linux.

## Files

- `fulfillai.service` — main systemd service definition.
- `fulfillai.service.d/10-restart-policy.conf` — restart-rate protection.

## Runtime

The application runs:

- as the non-login `fulfillai` service account;
- from `/opt/fulfillai/app`;
- using the Python virtual environment at `/opt/fulfillai/venv`;
- with Uvicorn bound to `127.0.0.1:8000`.

## Reliability Policy

The application is configured with:

- `Restart=on-failure`
- `RestartSec=3`
- `StartLimitIntervalSec=60`
- `StartLimitBurst=5`

A temporary application failure can therefore recover automatically, while a
persistent failure is prevented from producing an unlimited restart loop.

This behavior was validated through controlled failure testing documented in:

`docs/incidents/INC-001-systemd-execstart-failure.md`

## Verification

Useful operational commands:

```bash
systemctl status fulfillai --no-pager
systemctl is-enabled fulfillai
systemctl show fulfillai -p ActiveState -p SubState -p Result -p NRestarts
sudo journalctl -u fulfillai -n 50 --no-pager
sudo ss -lntp | grep ':8000'
curl -i http://127.0.0.1:8000/health
curl -s http://127.0.0.1:8000/metrics | head
