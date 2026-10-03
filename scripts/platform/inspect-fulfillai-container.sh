#!/usr/bin/env bash
set -uo pipefail

cd "$(git rev-parse --show-toplevel)"

SERVICE="${1:-api}"

echo "============================================================"
echo "        FulfillAI Container Runtime Inspection"
echo "============================================================"
echo

CID="$(docker compose --profile platform ps -q "$SERVICE" 2>/dev/null || true)"

if [ -z "$CID" ]; then
    echo "Service=$SERVICE"
    echo "ContainerPresent=NO"
    echo "ContainerRunning=NO"
    exit 1
fi

RUNNING="$(docker inspect -f "{{.State.Running}}" "$CID")"
HEALTH="$(docker inspect -f "{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}" "$CID")"
RESTART_COUNT="$(docker inspect -f "{{.RestartCount}}" "$CID")"
RESTART_POLICY="$(docker inspect -f "{{.HostConfig.RestartPolicy.Name}}" "$CID")"
RESTART_MAX="$(docker inspect -f "{{.HostConfig.RestartPolicy.MaximumRetryCount}}" "$CID")"
READONLY="$(docker inspect -f "{{.HostConfig.ReadonlyRootfs}}" "$CID")"
CAPDROP="$(docker inspect -f "{{json .HostConfig.CapDrop}}" "$CID")"
SECURITYOPT="$(docker inspect -f "{{json .HostConfig.SecurityOpt}}" "$CID")"
MEMORY="$(docker inspect -f "{{.HostConfig.Memory}}" "$CID")"
CPU="$(docker inspect -f "{{.HostConfig.NanoCpus}}" "$CID")"
PIDS="$(docker inspect -f "{{.HostConfig.PidsLimit}}" "$CID")"
ARCH="$(docker inspect -f "{{.Architecture}}" "$(docker inspect -f "{{.Image}}" "$CID")" 2>/dev/null || uname -m)"

HEALTH_HTTP="$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 http://127.0.0.1:8000/health || printf 000)"
METRICS_HTTP="$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 http://127.0.0.1:8000/metrics || printf 000)"

echo "=== IDENTITY ==="
echo "Service=$SERVICE"
echo "ContainerID=${CID:0:12}"
echo "Architecture=$ARCH"
echo
echo "=== AVAILABILITY ==="
echo "Running=$RUNNING"
echo "DockerHealth=$HEALTH"
echo "HealthHTTP=$HEALTH_HTTP"
echo "MetricsHTTP=$METRICS_HTTP"
echo
echo "=== RELIABILITY ==="
echo "RestartPolicy=$RESTART_POLICY"
echo "RestartMaxRetries=$RESTART_MAX"
echo "RestartCount=$RESTART_COUNT"
echo
echo "=== SECURITY ==="
echo "ReadOnlyRootFS=$READONLY"
echo "CapDrop=$CAPDROP"
echo "SecurityOpt=$SECURITYOPT"
echo
echo "=== RESOURCE LIMITS ==="
echo "MemoryLimitBytes=$MEMORY"
echo "NanoCPUs=$CPU"
echo "PidsLimit=$PIDS"
echo
echo "=== RUNTIME RESOURCE SNAPSHOT ==="
docker stats --no-stream --format "Name={{.Name}} CPU={{.CPUPerc}} Memory={{.MemUsage}} PIDs={{.PIDs}}" "$CID"
echo
echo "=== LAST 15 APPLICATION LOG LINES ==="
docker logs --tail 15 "$CID" 2>&1
