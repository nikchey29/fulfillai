from __future__ import annotations
import argparse, json, random, uuid
from datetime import datetime, timezone, timedelta
from kafka import KafkaProducer

STATUSES = ("created", "picked", "packed", "shipped", "exception", "delivered")
EVENT_TYPES = ("order_event", "shipment_event", "inventory_event")

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--bootstrap", default="redpanda:9092")
    p.add_argument("--topic", default="fulfillment.events")
    p.add_argument("--count", type=int, default=120)
    p.add_argument("--malformed", type=int, default=5)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--round", dest="round_id", default="round1")
    a = p.parse_args()
    rng = random.Random(a.seed)
    prod = KafkaProducer(bootstrap_servers=a.bootstrap, key_serializer=lambda x:x.encode(), value_serializer=lambda x:json.dumps(x).encode(), acks="all", retries=10)
    for i in range(a.count):
        event = {
            "event_id": str(uuid.uuid4()), "round_id": a.round_id,
            "event_type": rng.choice(EVENT_TYPES),
            "event_ts": (datetime.now(timezone.utc)-timedelta(seconds=rng.randint(0,90))).isoformat(),
            "order_id": 100000+i, "shipment_id": 200000+i,
            "warehouse_id": rng.randint(1,5), "status": rng.choice(STATUSES),
            "processing_seconds": round(rng.uniform(8,420),2), "units": rng.randint(1,12),
        }
        prod.send(a.topic, key=event["event_id"], value=event)
    for i in range(a.malformed):
        bad={"event_id":f"malformed-{a.round_id}-{i}","round_id":a.round_id,"event_type":"shipment_event","event_ts":None,"warehouse_id":None,"processing_seconds":"bad"}
        prod.send(a.topic, key=bad["event_id"], value=bad)
    prod.flush(); prod.close()
    print(f"PRODUCED_VALID={a.count}")
    print(f"PRODUCED_MALFORMED={a.malformed}")
    print(f"ROUND={a.round_id}")
    print("PRODUCER_COMPLETE=YES")

if __name__ == "__main__": main()
