# FulfillAI SELinux Confinement

FulfillAI runs on Rocky Linux with SELinux globally enforcing.

## Runtime

- systemd-managed FastAPI/Uvicorn service
- dedicated non-login fulfillai Unix account
- dedicated SELinux process domain: fulfillai_t
- dedicated executable type: fulfillai_exec_t
- dedicated TCP port type for port 8000
- systemd sandboxing enabled independently of SELinux

## Verification

The regression test checks:

- SELinux is Enforcing
- FulfillAI systemd service is active
- service is enabled for boot
- FulfillAI SELinux policy module exists
- fulfillai_t is not permissive
- Uvicorn executes under fulfillai_t
- TCP port 8000 uses fulfillai_port_t
- /health returns HTTP 200
- /metrics returns HTTP 200

## Persistence

The complete Lima Rocky Linux VM is stopped and restarted to verify that the systemd service, SELinux policy, labels, port mapping, and application survive a fresh boot.
