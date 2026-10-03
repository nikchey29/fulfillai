# FulfillAI systemd Security Hardening

## Objective

Reduce the privileges and operating-system attack surface available to the
FulfillAI FastAPI service while preserving application functionality.

The service runs on Rocky Linux using a dedicated non-login `fulfillai`
account and is managed by systemd.

## Validation Method

After each hardening phase the following were revalidated:

- systemd service state
- Uvicorn process
- TCP listener on `127.0.0.1:8000`
- `/health`
- `/metrics`
- SELinux AVC logs

The hardening posture was measured using:

`systemd-analyze security fulfillai`

## Measured Progression

| Stage | Exposure |
|---|---:|
| Initial baseline | 9.2 |
| Privilege-escalation controls | 8.8 |
| Kernel and host protection | 7.3 |
| Filesystem isolation | 6.8 |
| Capability minimization | 4.8 |
| Address-family restriction | 4.4 |
| Additional process/host restrictions | 3.8 |
| Final hardened policy | 1.5 |

## Implemented Controls

The final service policy includes:

- `NoNewPrivileges=true`
- `RestrictSUIDSGID=true`
- `LockPersonality=true`
- `ProtectKernelTunables=true`
- `ProtectKernelModules=true`
- `ProtectKernelLogs=true`
- `ProtectControlGroups=true`
- `PrivateDevices=true`
- `ProtectClock=true`
- `ProtectHostname=true`
- `RestrictRealtime=true`
- `PrivateTmp=true`
- `ProtectHome=true`
- `ProtectSystem=strict`
- `UMask=0077`
- empty `CapabilityBoundingSet`
- empty `AmbientCapabilities`
- `RestrictAddressFamilies=AF_UNIX AF_INET`
- `ProtectProc=invisible`
- `ProcSubset=pid`
- `RestrictNamespaces=true`
- `RemoveIPC=true`
- `SystemCallArchitectures=native`
- `SystemCallFilter=@system-service`
- `SystemCallErrorNumber=EPERM`

## Capability Verification

The running Uvicorn process was verified to have zero Linux capabilities:

`CapInh`, `CapPrm`, `CapEff`, `CapBnd`, and `CapAmb` were all zero.

## Application Verification

Following hardening:

- FulfillAI remained `active (running)`.
- Uvicorn continued listening on `127.0.0.1:8000`.
- `/health` returned HTTP 200.
- `/metrics` remained available.
- No unexpected SELinux AVC denials were observed.

## Important Distinction

The systemd sandbox significantly reduces the privileges available to the
service process, but it is separate from SELinux mandatory access control.

At this stage SELinux remains enforcing globally, while the FulfillAI process
still runs under `unconfined_service_t`.

Dedicated SELinux confinement is therefore a separate security improvement.
