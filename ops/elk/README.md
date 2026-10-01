# ELK Centralized Logging Lab

This is a localhost-only learning stack for Elasticsearch, Logstash and Kibana.

## Start

```bash
docker compose -f ops/elk/compose.yaml up -d
docker compose -f ops/elk/compose.yaml ps
```

Verify Elasticsearch:

```bash
curl http://localhost:9200
```

Send a structured FulfillAI log through Logstash:

```bash
curl -X POST http://localhost:8081 \
  -H 'Content-Type: application/json' \
  -d '{"service":"fulfillai-api","level":"ERROR","message":"database unavailable","environment":"dev"}'
```

Open Kibana at http://localhost:5601 and create a data view for `fulfillai-*`.

Stop:

```bash
docker compose -f ops/elk/compose.yaml down
```

Security is intentionally disabled for this local lab. Do not expose it publicly.
