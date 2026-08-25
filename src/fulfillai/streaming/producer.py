"""Publish FulfillAI order events to a Kafka-compatible Redpanda topic."""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_EVENTS = PROJECT_ROOT / "data" / "raw" / "synthetic" / "order_events.csv"


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser()
    p.add_argument("--bootstrap", default=os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:19092"))
    p.add_argument("--topic", default=os.getenv("FULFILLAI_EVENT_TOPIC", "fulfillai.order_events"))
    p.add_argument("--events", type=Path, default=DEFAULT_EVENTS)
    p.add_argument("--limit", type=int, default=500)
    p.add_argument("--sleep", type=float, default=0.01)
    return p


def normalize(row: dict) -> dict:
    payload = row.get("payload", {})
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            payload = {"raw": payload}
    return {
        "event_key": str(row.get("event_key", "")),
        "order_id": int(row.get("order_id", 0)),
        "warehouse_id": int(row.get("warehouse_id", 0)) if pd.notna(row.get("warehouse_id")) else None,
        "event_type": str(row.get("event_type", "unknown")),
        "event_ts": str(row.get("event_ts", pd.Timestamp.utcnow().isoformat())),
        "source": str(row.get("source", "fulfillai")),
        "payload": payload,
    }


def main() -> None:
    args = parser().parse_args()
    try:
        from kafka import KafkaProducer
    except ImportError as exc:
        raise RuntimeError("Install platform dependencies: pip install -r requirements-platform.txt") from exc

    if not args.events.exists():
        raise FileNotFoundError(
            f"Event source not found: {args.events}. Run the FulfillAI generator first."
        )
    frame = pd.read_csv(args.events).head(args.limit)
    producer = KafkaProducer(
        bootstrap_servers=args.bootstrap,
        value_serializer=lambda value: json.dumps(value, default=str).encode("utf-8"),
        key_serializer=lambda value: value.encode("utf-8"),
        acks="all",
    )
    sent = 0
    for row in frame.to_dict(orient="records"):
        event = normalize(row)
        producer.send(args.topic, key=event["event_key"], value=event)
        sent += 1
        if args.sleep:
            time.sleep(args.sleep)
    producer.flush()
    producer.close()
    print(f"Published {sent:,} events to {args.topic} via {args.bootstrap}")


if __name__ == "__main__":
    main()
