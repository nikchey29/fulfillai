-- ============================================================
-- FulfillAI
-- Fulfillment Funnel & Order Lifecycle Analytics
-- ============================================================
--
-- Purpose:
--   Reconstruct each order's lifecycle from the order_events
--   event stream and measure:
--
--     - Funnel progression
--     - Stage conversion
--     - Operational latency
--     - Warehouse lifecycle performance
--     - Cancellation stages
--     - Event consistency
--
-- Source tables:
--   orders
--   order_events
--   warehouses
--
-- ============================================================


-- ============================================================
-- TEMPORARY ORDER-LIFECYCLE VIEW
-- ============================================================
--
-- One row per order.
--
-- The event stream is pivoted into lifecycle timestamps.
-- Using orders as the base guarantees all 50,000 orders remain
-- visible even if an event were unexpectedly missing.
-- ============================================================


DROP VIEW IF EXISTS lifecycle_order_summary;


CREATE TEMP VIEW lifecycle_order_summary AS

SELECT

    o.order_id,
    o.order_external_id,
    o.warehouse_id,
    o.order_status,
    o.shipping_method,
    o.payment_method,
    o.order_ts,

    MIN(e.event_ts) FILTER (
        WHERE e.event_type = 'order_created'
    ) AS order_created_ts,

    MIN(e.event_ts) FILTER (
        WHERE e.event_type = 'payment_confirmed'
    ) AS payment_confirmed_ts,

    MIN(e.event_ts) FILTER (
        WHERE e.event_type = 'inventory_reserved'
    ) AS inventory_reserved_ts,

    MIN(e.event_ts) FILTER (
        WHERE e.event_type = 'processing_started'
    ) AS processing_started_ts,

    MIN(e.event_ts) FILTER (
        WHERE e.event_type = 'order_packed'
    ) AS order_packed_ts,

    MIN(e.event_ts) FILTER (
        WHERE e.event_type = 'shipment_created'
    ) AS shipment_created_ts,

    MIN(e.event_ts) FILTER (
        WHERE e.event_type = 'order_shipped'
    ) AS order_shipped_ts,

    MIN(e.event_ts) FILTER (
        WHERE e.event_type = 'order_delivered'
    ) AS order_delivered_ts,

    MIN(e.event_ts) FILTER (
        WHERE e.event_type = 'delivery_exception'
    ) AS delivery_exception_ts,

    MIN(e.event_ts) FILTER (
        WHERE e.event_type = 'order_cancelled'
    ) AS order_cancelled_ts,


    COUNT(*) FILTER (
        WHERE e.event_type = 'order_created'
    ) AS order_created_events,

    COUNT(*) FILTER (
        WHERE e.event_type = 'payment_confirmed'
    ) AS payment_confirmed_events,

    COUNT(*) FILTER (
        WHERE e.event_type = 'inventory_reserved'
    ) AS inventory_reserved_events,

    COUNT(*) FILTER (
        WHERE e.event_type = 'processing_started'
    ) AS processing_started_events,

    COUNT(*) FILTER (
        WHERE e.event_type = 'order_packed'
    ) AS order_packed_events,

    COUNT(*) FILTER (
        WHERE e.event_type = 'shipment_created'
    ) AS shipment_created_events,

    COUNT(*) FILTER (
        WHERE e.event_type = 'order_shipped'
    ) AS order_shipped_events,

    COUNT(*) FILTER (
        WHERE e.event_type = 'order_delivered'
    ) AS order_delivered_events,

    COUNT(*) FILTER (
        WHERE e.event_type = 'delivery_exception'
    ) AS delivery_exception_events,

    COUNT(*) FILTER (
        WHERE e.event_type = 'order_cancelled'
    ) AS order_cancelled_events


FROM orders AS o

LEFT JOIN order_events AS e
    ON e.order_id = o.order_id

GROUP BY

    o.order_id,
    o.order_external_id,
    o.warehouse_id,
    o.order_status,
    o.shipping_method,
    o.payment_method,
    o.order_ts;



-- ============================================================
-- 1. GLOBAL FULFILLMENT FUNNEL
-- ============================================================


SELECT

    COUNT(*) AS total_orders,

    COUNT(*) FILTER (
        WHERE order_created_ts IS NOT NULL
    ) AS created,

    COUNT(*) FILTER (
        WHERE payment_confirmed_ts IS NOT NULL
    ) AS payment_confirmed,

    COUNT(*) FILTER (
        WHERE inventory_reserved_ts IS NOT NULL
    ) AS inventory_reserved,

    COUNT(*) FILTER (
        WHERE processing_started_ts IS NOT NULL
    ) AS processing_started,

    COUNT(*) FILTER (
        WHERE order_packed_ts IS NOT NULL
    ) AS packed,

    COUNT(*) FILTER (
        WHERE shipment_created_ts IS NOT NULL
    ) AS shipment_created,

    COUNT(*) FILTER (
        WHERE order_shipped_ts IS NOT NULL
    ) AS shipped,

    COUNT(*) FILTER (
        WHERE order_delivered_ts IS NOT NULL
    ) AS delivered,

    COUNT(*) FILTER (
        WHERE delivery_exception_ts IS NOT NULL
    ) AS delivery_exceptions,

    COUNT(*) FILTER (
        WHERE order_cancelled_ts IS NOT NULL
    ) AS cancelled,


    ROUND(
        100.0
        * COUNT(*) FILTER (
            WHERE payment_confirmed_ts IS NOT NULL
        )
        / NULLIF(COUNT(*), 0),
        2
    ) AS payment_conversion_pct,


    ROUND(
        100.0
        * COUNT(*) FILTER (
            WHERE inventory_reserved_ts IS NOT NULL
        )
        / NULLIF(COUNT(*), 0),
        2
    ) AS reservation_conversion_pct,


    ROUND(
        100.0
        * COUNT(*) FILTER (
            WHERE shipment_created_ts IS NOT NULL
        )
        / NULLIF(COUNT(*), 0),
        2
    ) AS shipment_conversion_pct,


    ROUND(
        100.0
        * COUNT(*) FILTER (
            WHERE order_delivered_ts IS NOT NULL
        )
        / NULLIF(COUNT(*), 0),
        2
    ) AS delivery_conversion_pct,


    ROUND(
        100.0
        * COUNT(*) FILTER (
            WHERE order_cancelled_ts IS NOT NULL
        )
        / NULLIF(COUNT(*), 0),
        2
    ) AS cancellation_rate_pct


FROM lifecycle_order_summary;



-- ============================================================
-- 2. GLOBAL LIFECYCLE TIMING
-- ============================================================


SELECT

    ROUND(
        (
            AVG(
                EXTRACT(
                    EPOCH FROM (
                        payment_confirmed_ts
                        - order_created_ts
                    )
                ) / 60.0
            ) FILTER (
                WHERE
                    order_created_ts IS NOT NULL
                    AND payment_confirmed_ts IS NOT NULL
            )
        )::numeric,
        2
    ) AS avg_created_to_payment_minutes,


    ROUND(
        (
            AVG(
                EXTRACT(
                    EPOCH FROM (
                        inventory_reserved_ts
                        - payment_confirmed_ts
                    )
                ) / 60.0
            ) FILTER (
                WHERE
                    payment_confirmed_ts IS NOT NULL
                    AND inventory_reserved_ts IS NOT NULL
            )
        )::numeric,
        2
    ) AS avg_payment_to_reservation_minutes,


    ROUND(
        (
            AVG(
                EXTRACT(
                    EPOCH FROM (
                        processing_started_ts
                        - inventory_reserved_ts
                    )
                ) / 60.0
            ) FILTER (
                WHERE
                    inventory_reserved_ts IS NOT NULL
                    AND processing_started_ts IS NOT NULL
            )
        )::numeric,
        2
    ) AS avg_reservation_to_processing_minutes,


    ROUND(
        (
            AVG(
                EXTRACT(
                    EPOCH FROM (
                        order_packed_ts
                        - processing_started_ts
                    )
                ) / 3600.0
            ) FILTER (
                WHERE
                    processing_started_ts IS NOT NULL
                    AND order_packed_ts IS NOT NULL
            )
        )::numeric,
        2
    ) AS avg_processing_to_packed_hours,


    ROUND(
        (
            AVG(
                EXTRACT(
                    EPOCH FROM (
                        shipment_created_ts
                        - order_packed_ts
                    )
                ) / 60.0
            ) FILTER (
                WHERE
                    order_packed_ts IS NOT NULL
                    AND shipment_created_ts IS NOT NULL
            )
        )::numeric,
        2
    ) AS avg_packed_to_shipment_creation_minutes,


    ROUND(
        (
            AVG(
                EXTRACT(
                    EPOCH FROM (
                        order_shipped_ts
                        - shipment_created_ts
                    )
                ) / 60.0
            ) FILTER (
                WHERE
                    shipment_created_ts IS NOT NULL
                    AND order_shipped_ts IS NOT NULL
            )
        )::numeric,
        2
    ) AS avg_shipment_creation_to_shipped_minutes,


    ROUND(
        (
            AVG(
                EXTRACT(
                    EPOCH FROM (
                        order_delivered_ts
                        - order_shipped_ts
                    )
                ) / 3600.0
            ) FILTER (
                WHERE
                    order_shipped_ts IS NOT NULL
                    AND order_delivered_ts IS NOT NULL
            )
        )::numeric,
        2
    ) AS avg_shipping_to_delivery_hours,


    ROUND(
        (
            AVG(
                EXTRACT(
                    EPOCH FROM (
                        order_delivered_ts
                        - order_created_ts
                    )
                ) / 3600.0
            ) FILTER (
                WHERE
                    order_created_ts IS NOT NULL
                    AND order_delivered_ts IS NOT NULL
            )
        )::numeric,
        2
    ) AS avg_end_to_end_fulfillment_hours


FROM lifecycle_order_summary;



-- ============================================================
-- 3. WAREHOUSE LIFECYCLE PERFORMANCE
-- ============================================================


SELECT

    w.warehouse_id,
    w.warehouse_code,
    w.warehouse_name,
    w.city,
    w.country_code,

    COUNT(*) AS orders,

    COUNT(*) FILTER (
        WHERE l.order_cancelled_ts IS NOT NULL
    ) AS cancelled_orders,

    COUNT(*) FILTER (
        WHERE l.shipment_created_ts IS NOT NULL
    ) AS shipments,

    COUNT(*) FILTER (
        WHERE l.order_delivered_ts IS NOT NULL
    ) AS delivered_orders,

    COUNT(*) FILTER (
        WHERE l.delivery_exception_ts IS NOT NULL
    ) AS delivery_exceptions,


    ROUND(
        100.0
        * COUNT(*) FILTER (
            WHERE l.order_cancelled_ts IS NOT NULL
        )
        / NULLIF(
            COUNT(*),
            0
        ),
        2
    ) AS cancellation_rate_pct,


    ROUND(
        100.0
        * COUNT(*) FILTER (
            WHERE l.delivery_exception_ts IS NOT NULL
        )
        / NULLIF(
            COUNT(*) FILTER (
                WHERE l.shipment_created_ts IS NOT NULL
            ),
            0
        ),
        2
    ) AS exception_rate_pct,


    ROUND(
        100.0
        * COUNT(*) FILTER (
            WHERE l.order_delivered_ts IS NOT NULL
        )
        / NULLIF(
            COUNT(*) FILTER (
                WHERE l.shipment_created_ts IS NOT NULL
            ),
            0
        ),
        2
    ) AS delivery_success_rate_pct,


    ROUND(
        (
            AVG(
                EXTRACT(
                    EPOCH FROM (
                        l.payment_confirmed_ts
                        - l.order_created_ts
                    )
                ) / 60.0
            ) FILTER (
                WHERE
                    l.order_created_ts IS NOT NULL
                    AND l.payment_confirmed_ts IS NOT NULL
            )
        )::numeric,
        2
    ) AS avg_payment_minutes,


    ROUND(
        (
            AVG(
                EXTRACT(
                    EPOCH FROM (
                        l.inventory_reserved_ts
                        - l.payment_confirmed_ts
                    )
                ) / 60.0
            ) FILTER (
                WHERE
                    l.payment_confirmed_ts IS NOT NULL
                    AND l.inventory_reserved_ts IS NOT NULL
            )
        )::numeric,
        2
    ) AS avg_reservation_minutes,


    ROUND(
        (
            AVG(
                EXTRACT(
                    EPOCH FROM (
                        l.order_packed_ts
                        - l.processing_started_ts
                    )
                ) / 3600.0
            ) FILTER (
                WHERE
                    l.processing_started_ts IS NOT NULL
                    AND l.order_packed_ts IS NOT NULL
            )
        )::numeric,
        2
    ) AS avg_packing_hours,


    ROUND(
        (
            AVG(
                EXTRACT(
                    EPOCH FROM (
                        l.order_delivered_ts
                        - l.order_shipped_ts
                    )
                ) / 3600.0
            ) FILTER (
                WHERE
                    l.order_shipped_ts IS NOT NULL
                    AND l.order_delivered_ts IS NOT NULL
            )
        )::numeric,
        2
    ) AS avg_transit_hours,


    ROUND(
        (
            AVG(
                EXTRACT(
                    EPOCH FROM (
                        l.order_delivered_ts
                        - l.order_created_ts
                    )
                ) / 3600.0
            ) FILTER (
                WHERE
                    l.order_created_ts IS NOT NULL
                    AND l.order_delivered_ts IS NOT NULL
            )
        )::numeric,
        2
    ) AS avg_end_to_end_hours


FROM lifecycle_order_summary AS l

JOIN warehouses AS w
    ON w.warehouse_id = l.warehouse_id

GROUP BY

    w.warehouse_id,
    w.warehouse_code,
    w.warehouse_name,
    w.city,
    w.country_code

ORDER BY
    avg_end_to_end_hours DESC NULLS LAST,
    w.warehouse_id;



-- ============================================================
-- 4. CANCELLATION STAGE ANALYSIS
-- ============================================================
--
-- The synthetic generator supports:
--
--   pre_payment
--   post_payment
--   post_reservation
--
-- Rather than relying on a label, derive the stage from events.
-- ============================================================


WITH cancelled_orders AS (

    SELECT

        *,

        CASE

            WHEN payment_confirmed_ts IS NULL
                THEN 'pre_payment'

            WHEN inventory_reserved_ts IS NULL
                THEN 'post_payment'

            ELSE 'post_reservation'

        END AS cancellation_stage

    FROM lifecycle_order_summary

    WHERE order_status = 'cancelled'
)


SELECT

    cancellation_stage,

    COUNT(*) AS cancelled_orders,

    ROUND(
        100.0
        * COUNT(*)
        / SUM(COUNT(*)) OVER (),
        2
    ) AS cancelled_order_share_pct,

    ROUND(
        (
            AVG(
                EXTRACT(
                    EPOCH FROM (
                        order_cancelled_ts
                        - order_created_ts
                    )
                ) / 60.0
            )
        )::numeric,
        2
    ) AS avg_minutes_until_cancellation

FROM cancelled_orders

GROUP BY
    cancellation_stage

ORDER BY

    CASE cancellation_stage
        WHEN 'pre_payment' THEN 1
        WHEN 'post_payment' THEN 2
        WHEN 'post_reservation' THEN 3
        ELSE 4
    END;



-- ============================================================
-- 5. EVENT CONSISTENCY / DATA QUALITY AUDIT
-- ============================================================


SELECT

    COUNT(*) FILTER (
        WHERE order_created_events <> 1
    ) AS invalid_order_created_counts,

    COUNT(*) FILTER (
        WHERE payment_confirmed_events > 1
    ) AS duplicate_payment_events,

    COUNT(*) FILTER (
        WHERE inventory_reserved_events > 1
    ) AS duplicate_inventory_reservation_events,

    COUNT(*) FILTER (
        WHERE shipment_created_events > 1
    ) AS duplicate_shipment_created_events,

    COUNT(*) FILTER (
        WHERE order_shipped_events > 1
    ) AS duplicate_order_shipped_events,

    COUNT(*) FILTER (
        WHERE order_delivered_events > 1
    ) AS duplicate_order_delivered_events,

    COUNT(*) FILTER (
        WHERE order_cancelled_events > 1
    ) AS duplicate_order_cancelled_events,


    COUNT(*) FILTER (
        WHERE
            order_status = 'cancelled'
            AND order_cancelled_ts IS NULL
    ) AS cancelled_orders_missing_cancel_event,


    COUNT(*) FILTER (
        WHERE
            order_status <> 'cancelled'
            AND order_cancelled_ts IS NOT NULL
    ) AS non_cancelled_orders_with_cancel_event,


    COUNT(*) FILTER (
        WHERE
            shipment_created_ts IS NOT NULL
            AND order_packed_ts IS NULL
    ) AS shipment_without_pack_event,


    COUNT(*) FILTER (
        WHERE
            order_shipped_ts IS NOT NULL
            AND shipment_created_ts IS NULL
    ) AS shipped_without_shipment_created,


    COUNT(*) FILTER (
        WHERE
            order_delivered_ts IS NOT NULL
            AND order_shipped_ts IS NULL
    ) AS delivered_without_shipped_event,


    COUNT(*) FILTER (
        WHERE
            payment_confirmed_ts IS NOT NULL
            AND payment_confirmed_ts < order_created_ts
    ) AS payment_before_creation,


    COUNT(*) FILTER (
        WHERE
            inventory_reserved_ts IS NOT NULL
            AND payment_confirmed_ts IS NOT NULL
            AND inventory_reserved_ts < payment_confirmed_ts
    ) AS reservation_before_payment,


    COUNT(*) FILTER (
        WHERE
            processing_started_ts IS NOT NULL
            AND inventory_reserved_ts IS NOT NULL
            AND processing_started_ts < inventory_reserved_ts
    ) AS processing_before_reservation,


    COUNT(*) FILTER (
        WHERE
            order_packed_ts IS NOT NULL
            AND processing_started_ts IS NOT NULL
            AND order_packed_ts < processing_started_ts
    ) AS packed_before_processing,


    COUNT(*) FILTER (
        WHERE
            shipment_created_ts IS NOT NULL
            AND order_packed_ts IS NOT NULL
            AND shipment_created_ts < order_packed_ts
    ) AS shipment_created_before_packed,


    COUNT(*) FILTER (
        WHERE
            order_shipped_ts IS NOT NULL
            AND shipment_created_ts IS NOT NULL
            AND order_shipped_ts < shipment_created_ts
    ) AS shipped_before_shipment_created,


    COUNT(*) FILTER (
        WHERE
            order_delivered_ts IS NOT NULL
            AND order_shipped_ts IS NOT NULL
            AND order_delivered_ts < order_shipped_ts
    ) AS delivered_before_shipped

FROM lifecycle_order_summary;