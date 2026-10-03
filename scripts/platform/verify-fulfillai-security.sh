#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -u)" -eq 0 ]; then
    SUDO=()
else
    SUDO=(sudo -n)
fi

echo "[1/9] SELinux enforcing"
getenforce | grep -qx "Enforcing"

echo "[2/9] systemd service active"
systemctl is-active --quiet fulfillai

echo "[3/9] systemd service enabled"
systemctl is-enabled --quiet fulfillai

echo "[4/9] SELinux module installed"
"${SUDO[@]}" semodule -l | grep -q "^fulfillai"

echo "[5/9] fulfillai_t enforcing"
if "${SUDO[@]}" semanage permissive -l | grep -qx "fulfillai_t"; then
    echo "ERROR: fulfillai_t is still permissive"
    exit 1
fi

echo "[6/9] Uvicorn process confined"
ps -eZ | grep "[u]vicorn" | grep -q "system_u:system_r:fulfillai_t:s0"

echo "[7/9] TCP 8000 SELinux mapping"
"${SUDO[@]}" semanage port -l | grep "^fulfillai_port_t" | grep -qw "8000"

echo "[8/9] health endpoint"
test "$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/health)" = "200"

echo "[9/9] metrics endpoint"
test "$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/metrics)" = "200"

echo "FULFILLAI_SECURITY_CHECK=PASS"
