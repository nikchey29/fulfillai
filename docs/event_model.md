# FulfillAI Event Model

FulfillAI models an e-commerce fulfillment system using two complementary
event datasets:

1. `inventory_movements`
2. `order_events`

These datasets convert the static transactional model into an auditable
event-driven fulfillment simulation.

---

# 1. Order Lifecycle

Every order begins with:

order_created

The path taken afterward depends on whether the order is fulfilled,
cancelled, delivered, or encounters a delivery exception.

---

## Successful Order

Typical lifecycle:

order_created
    ↓
payment_confirmed
    ↓
inventory_reserved
    ↓
processing_started
    ↓
order_packed
    ↓
shipment_created
    ↓
order_shipped
    ↓
order_delivered

All event timestamps must be monotonically increasing.

---

## Late but Delivered Order

The lifecycle is the same as a successful order:

order_created
    ↓
payment_confirmed
    ↓
inventory_reserved
    ↓
processing_started
    ↓
order_packed
    ↓
shipment_created
    ↓
order_shipped
    ↓
order_delivered

The difference is:

delivered_at > expected_delivery_at

Late delivery is therefore derived from timestamps instead of represented
as a separate terminal order state.

---

## Delivery Exception

order_created
    ↓
payment_confirmed
    ↓
inventory_reserved
    ↓
processing_started
    ↓
order_packed
    ↓
shipment_created
    ↓
order_shipped
    ↓
delivery_exception

The shipment remains in an exception state and does not receive an
`order_delivered` event.

---

# 2. Cancellation Paths

Cancelled orders can terminate at different points in the order lifecycle.

This produces more realistic operational behavior than cancelling every
order immediately after creation.

---

## Pre-Payment Cancellation

order_created
    ↓
order_cancelled

No inventory reservation is created.

---

## Post-Payment Cancellation

order_created
    ↓
payment_confirmed
    ↓
order_cancelled

No inventory reservation is created.

---

## Post-Reservation Cancellation

order_created
    ↓
payment_confirmed
    ↓
inventory_reserved
    ↓
order_cancelled

Inventory that had been reserved must subsequently be released.

Inventory movement:

reservation
    ↓
release

No shipment is created.

---

# 3. Inventory Movement Model

The `inventory_movements` dataset provides an auditable history of
inventory activity.

Supported movement types:

- receipt
- reservation
- release
- shipment
- adjustment
- return

Not every movement type must be generated in the initial implementation.

---

## Receipt

Represents inventory entering a warehouse.

quantity_change > 0

Initial inventory positions will receive an opening receipt before the
simulation begins.

Example:

receipt +250

---

## Reservation

Represents inventory being allocated to an order.

quantity_change < 0

Reservation affects inventory availability but does not represent a
physical shipment from the warehouse.

Example:

reservation -2

---

## Release

Reverses an existing reservation when fulfillment does not continue.

quantity_change > 0

Example:

reservation -2
release +2

This commonly occurs when an order is cancelled after inventory has
already been reserved.

---

## Shipment

Represents physical inventory leaving a warehouse.

quantity_change < 0

Example:

shipment -2

Shipment movements are generated only for orders that actually ship.

---

## Return

Represents previously shipped inventory entering inventory again.

quantity_change > 0

Returns are supported by the schema but are outside the initial Phase 3.7
implementation.

---

## Adjustment

Represents a manual or operational correction.

quantity_change may be positive or negative.

Examples:

adjustment +3
adjustment -2

Adjustments are supported by the schema but are outside the initial
Phase 3.7 implementation.

---

# 4. Inventory Accounting Semantics

`quantity_change` must be interpreted together with `movement_type`.

There are two inventory concepts represented by the event stream:

### Physical inventory

Affected by:

- receipt
- shipment
- return
- adjustment

### Available / reserved inventory

Affected by:

- reservation
- release

Therefore, summing every movement type together is not a valid measure of
physical on-hand inventory.

Physical inventory reconciliation should use only physical inventory
movement types.

---

# 5. Opening Inventory

Each warehouse-product inventory position receives an opening receipt
before the simulation begins.

The opening quantity is calculated so that subsequent shipment movements
can reconcile back to the final inventory snapshot.

Conceptually:

opening_inventory
    -
shipped_quantity
    =
ending_on_hand_inventory

The existing `inventory.csv` dataset represents the ending inventory
snapshot.

---

# 6. Inventory Movement Relationships

Every inventory movement contains:

- movement_id
- warehouse_id
- product_id
- order_id
- movement_type
- quantity_change
- event_ts
- created_at

Opening receipts have:

order_id = NULL

Order-related movements reference the originating order.

---

# 7. Order Event Relationships

Every lifecycle event contains:

- event_id
- event_key
- order_id
- warehouse_id
- event_type
- event_ts
- source
- payload
- ingested_at

The event key must be deterministic and globally unique.

Example:

ORD-00000001:order_created

or:

ORD-00000001:shipment_created

---

# 8. Event Source

Synthetic events generated by FulfillAI use:

source = synthetic_generator

The source field keeps origin separate from event type. The synthetic generator uses `synthetic_generator`, while downstream producers can preserve or map that origin when the same events move through the streaming path.

---

# 9. Event Payload

The JSON payload can store context specific to an event.

Examples:

order_created
{
  "shipping_method": "express"
}

shipment_created
{
  "shipment_id": 12345,
  "carrier": "DHL"
}

delivery_exception
{
  "shipment_id": 12345,
  "carrier": "DHL",
  "reason": "carrier_delay"
}

order_cancelled
{
  "cancellation_stage": "post_reservation"
}

---

# 10. Temporal Integrity Rules

For fulfilled orders:

order_created
<
payment_confirmed
<
inventory_reserved
<
processing_started
<
order_packed
<
shipment_created
<=
order_shipped

For delivered orders:

order_shipped
<
order_delivered

For delivery exceptions:

order_shipped
<
delivery_exception

For post-reservation cancellations:

inventory_reserved
<
order_cancelled

and:

reservation_ts
<
release_ts

---

# 11. Referential Integrity

Every `order_events.order_id` must exist in `orders`.

Every non-null `inventory_movements.order_id` must exist in `orders`.

Every inventory movement product must exist in `products`.

Every inventory movement warehouse must exist in `warehouses`.

Every event warehouse must match the warehouse assigned to its order.

Every shipment lifecycle event must reference an order that has a
shipment.

Cancelled orders must never receive shipment lifecycle events.

---

# 12. Determinism

Event generation must use FulfillAI's configured random seed.

Regenerating the same configuration must produce byte-identical:

- inventory_movements.csv
- order_events.csv

along with the existing synthetic datasets.

---

# 13. Generated event outputs

The generator writes two event-oriented datasets locally:

```text
data/raw/synthetic/inventory_movements.csv
data/raw/synthetic/order_events.csv
```

They are generated artifacts and are not committed to Git.

The operational sequence represented by the model is:

```text
Master data
    ↓
Inventory snapshot
    ↓
Orders
    ↓
Order items
    ↓
Shipments
    ↓
Inventory movement ledger
    ↓
Order lifecycle event stream
```

The same event layer now feeds several parts of FulfillAI:

- SQL operational analytics and warehouse KPIs;
- inventory and fulfillment-latency analysis;
- delivery-performance analysis;
- forecasting and risk-model feature construction;
- Redpanda/Kafka-compatible streaming through the event producer;
- PySpark windowed streaming metrics;
- downstream API and dashboard views through the analytical layer.

Anomaly detection is still an open extension rather than a completed component.