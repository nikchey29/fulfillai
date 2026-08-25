#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ ! -f .env ]]; then
  echo "Missing .env. Copy .env.example to .env and set POSTGRES_PASSWORD first."
  exit 1
fi

python scripts/platform_preflight.py

docker compose --profile platform up -d postgres mlflow api

echo "Waiting for FastAPI..."
for _ in $(seq 1 30); do
  if curl -fsS http://localhost:8000/health >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

curl -fsS http://localhost:8000/health || {
  echo "API did not become healthy. Run: docker compose logs api"
  exit 1
}

echo
echo "FulfillAI platform services are running:"
echo "  API docs : http://localhost:8000/docs"
echo "  Results  : http://localhost:8000/v1/results"
echo "  MLflow   : http://localhost:5001"
echo
echo "Next: make mlflow-log"
