-- ============================================================
-- FulfillAI
-- Model 001: Order Facts
-- ============================================================
--
-- Grain:
--   One row per order.
--
-- Purpose:
--   Create a reusable analytical foundation combining:
--
--     orders
--     customers
--     warehouses
--     order_items
--     shipments
--     order_events
--
-- This model will later support:
--
--     demand forecasting
--     late-delivery prediction
--     fulfillment-risk modeling
--     warehouse analysis
--     customer/geographic analysis
--     dashboards
--
-- ============================================================


CREATE OR REPLACE VIEW vw_order_facts AS


WITH item_metrics AS (

    SELECT

        oi.order_id,

        COUNT(*) AS order_item_lines,

        SUM(oi.quantity) AS units_ordered,

        COUNT(
            DISTINCT oi.product_id
        ) AS distinct_products,

        ROUND(
            SUM(
                oi.quantity * oi.unit_price
            )::numeric,
            2
        ) AS item_gross_value,

        ROUND(
            AVG(
                oi.unit_price
            )::numeric,
            2
        ) AS average_item_price

    FROM order_items AS oi

    GROUP BY
        oi.order_id
),


shipment_metrics AS (

    SELECT

        s.order_id,

        COUNT(*) AS shipment_count,

        MIN(
            s.shipment_id
        ) AS shipment_id,

        MIN(
            s.shipment_external_id
        ) AS shipment_external_id,

        MIN(
            s.carrier
        ) AS carrier,

        MIN(
            s.shipment_status
        ) AS shipment_status,

        MIN(
            s.shipped_at
        ) AS shipped_at,

        MIN(
            s.expected_delivery_at
        ) AS expected_delivery_at,

        MIN(
            s.delivered_at
        ) AS delivered_at,

        ROUND(
            SUM(
                s.shipping_cost
            )::numeric,
            2
        ) AS shipping_cost

    FROM shipments AS s

    GROUP BY
        s.order_id
),


event_metrics AS (

    SELECT

        oe.order_id,

        COUNT(*) AS lifecycle_event_count,

        MIN(
            oe.event_ts
        ) AS first_event_ts,

        MAX(
            oe.event_ts
        ) AS last_event_ts,

        MIN(oe.event_ts) FILTER (
            WHERE oe.event_type = 'order_created'
        ) AS order_created_event_ts,

        MIN(oe.event_ts) FILTER (
            WHERE oe.event_type = 'payment_confirmed'
        ) AS payment_confirmed_ts,

        MIN(oe.event_ts) FILTER (
            WHERE oe.event_type = 'inventory_reserved'
        ) AS inventory_reserved_ts,

        MIN(oe.event_ts) FILTER (
            WHERE oe.event_type = 'processing_started'
        ) AS processing_started_ts,

        MIN(oe.event_ts) FILTER (
            WHERE oe.event_type = 'order_packed'
        ) AS order_packed_ts,

        MIN(oe.event_ts) FILTER (
            WHERE oe.event_type = 'shipment_created'
        ) AS shipment_created_event_ts,

        MIN(oe.event_ts) FILTER (
            WHERE oe.event_type = 'order_shipped'
        ) AS order_shipped_event_ts,

        MIN(oe.event_ts) FILTER (
            WHERE oe.event_type = 'order_delivered'
        ) AS order_delivered_event_ts,

        MIN(oe.event_ts) FILTER (
            WHERE oe.event_type = 'delivery_exception'
        ) AS delivery_exception_ts,

        MIN(oe.event_ts) FILTER (
            WHERE oe.event_type = 'order_cancelled'
        ) AS order_cancelled_ts

    FROM order_events AS oe

    GROUP BY
        oe.order_id
)


SELECT

    -- ========================================================
    -- ORDER IDENTIFIERS
    -- ========================================================

    o.order_id,
    o.order_external_id,


    -- ========================================================
    -- CUSTOMER
    -- ========================================================

    o.customer_id,

    c.customer_external_id,

    c.country_code AS customer_country_code,

    c.region AS customer_region,


    -- ========================================================
    -- WAREHOUSE
    -- ========================================================

    o.warehouse_id,

    w.warehouse_code,
    w.warehouse_name,

    w.city AS warehouse_city,

    w.country_code AS warehouse_country_code,

    w.capacity_units AS warehouse_capacity_units,


    -- ========================================================
    -- ORDER ATTRIBUTES
    -- ========================================================

    o.order_status,

    o.shipping_method,

    o.payment_method,

    o.destination_country,

    o.destination_region,

    o.order_ts,

    o.promised_delivery_ts,

    o.created_at AS order_record_created_at,

    o.total_amount,


    -- ========================================================
    -- DATE / TIME DIMENSIONS
    -- ========================================================

    o.order_ts::date AS order_date,

    DATE_TRUNC(
        'week',
        o.order_ts
    )::date AS order_week,

    DATE_TRUNC(
        'month',
        o.order_ts
    )::date AS order_month,

    EXTRACT(
        YEAR FROM o.order_ts
    )::integer AS order_year,

    EXTRACT(
        MONTH FROM o.order_ts
    )::integer AS order_month_number,

    EXTRACT(
        ISODOW FROM o.order_ts
    )::integer AS order_day_of_week,

    EXTRACT(
        HOUR FROM o.order_ts
    )::integer AS order_hour,

    CASE

        WHEN EXTRACT(
            ISODOW FROM o.order_ts
        ) IN (6, 7)

        THEN 1

        ELSE 0

    END AS is_weekend,


    -- ========================================================
    -- ORDER ITEM / BASKET METRICS
    -- ========================================================

    COALESCE(
        im.order_item_lines,
        0
    ) AS order_item_lines,

    COALESCE(
        im.units_ordered,
        0
    ) AS units_ordered,

    COALESCE(
        im.distinct_products,
        0
    ) AS distinct_products,

    COALESCE(
        im.item_gross_value,
        0
    ) AS item_gross_value,

    COALESCE(
        im.average_item_price,
        0
    ) AS average_item_price,


    -- ========================================================
    -- SHIPMENT ATTRIBUTES
    -- ========================================================

    COALESCE(
        sm.shipment_count,
        0
    ) AS shipment_count,

    sm.shipment_id,

    sm.shipment_external_id,

    sm.carrier,

    sm.shipment_status,

    sm.shipped_at,

    sm.expected_delivery_at,

    sm.delivered_at,

    COALESCE(
        sm.shipping_cost,
        0
    ) AS shipping_cost,


    -- ========================================================
    -- ORDER FLAGS
    -- ========================================================

    CASE

        WHEN o.order_status = 'cancelled'
        THEN 1

        ELSE 0

    END AS is_cancelled,


    CASE

        WHEN sm.shipment_id IS NOT NULL
        THEN 1

        ELSE 0

    END AS has_shipment,


    CASE

        WHEN sm.shipment_status = 'delivered'
        THEN 1

        ELSE 0

    END AS is_delivered,


    CASE

        WHEN sm.shipment_status = 'exception'
        THEN 1

        ELSE 0

    END AS is_delivery_exception,


    CASE

        WHEN
            sm.shipment_status = 'delivered'
            AND sm.delivered_at
                > sm.expected_delivery_at

        THEN 1

        ELSE 0

    END AS is_late_delivery,


    CASE

        WHEN
            sm.shipment_status = 'delivered'
            AND sm.delivered_at
                <= sm.expected_delivery_at

        THEN 1

        ELSE 0

    END AS is_on_time_delivery,


    -- ========================================================
    -- LIFECYCLE EVENT TIMESTAMPS
    -- ========================================================

    COALESCE(
        em.lifecycle_event_count,
        0
    ) AS lifecycle_event_count,

    em.first_event_ts,

    em.last_event_ts,

    em.order_created_event_ts,

    em.payment_confirmed_ts,

    em.inventory_reserved_ts,

    em.processing_started_ts,

    em.order_packed_ts,

    em.shipment_created_event_ts,

    em.order_shipped_event_ts,

    em.order_delivered_event_ts,

    em.delivery_exception_ts,

    em.order_cancelled_ts,


    -- ========================================================
    -- OPERATIONAL LATENCY FEATURES
    -- ========================================================

    ROUND(
        (
            EXTRACT(
                EPOCH FROM (
                    em.payment_confirmed_ts
                    - em.order_created_event_ts
                )
            )
            / 60.0
        )::numeric,
        2
    ) AS payment_confirmation_minutes,


    ROUND(
        (
            EXTRACT(
                EPOCH FROM (
                    em.inventory_reserved_ts
                    - em.payment_confirmed_ts
                )
            )
            / 60.0
        )::numeric,
        2
    ) AS inventory_reservation_minutes,


    ROUND(
        (
            EXTRACT(
                EPOCH FROM (
                    em.processing_started_ts
                    - em.inventory_reserved_ts
                )
            )
            / 60.0
        )::numeric,
        2
    ) AS processing_start_minutes,


    ROUND(
        (
            EXTRACT(
                EPOCH FROM (
                    em.order_packed_ts
                    - em.processing_started_ts
                )
            )
            / 3600.0
        )::numeric,
        2
    ) AS packing_hours,


    ROUND(
        (
            EXTRACT(
                EPOCH FROM (
                    sm.shipped_at
                    - o.order_ts
                )
            )
            / 3600.0
        )::numeric,
        2
    ) AS order_to_ship_hours,


    ROUND(
        (
            EXTRACT(
                EPOCH FROM (
                    sm.delivered_at
                    - sm.shipped_at
                )
            )
            / 3600.0
        )::numeric,
        2
    ) AS transit_hours,


    ROUND(
        (
            EXTRACT(
                EPOCH FROM (
                    sm.delivered_at
                    - o.order_ts
                )
            )
            / 3600.0
        )::numeric,
        2
    ) AS order_to_delivery_hours,


    ROUND(
        (
            EXTRACT(
                EPOCH FROM (
                    sm.expected_delivery_at
                    - sm.shipped_at
                )
            )
            / 3600.0
        )::numeric,
        2
    ) AS expected_transit_hours,


    ROUND(
        (
            EXTRACT(
                EPOCH FROM (
                    sm.delivered_at
                    - sm.expected_delivery_at
                )
            )
            / 3600.0
        )::numeric,
        2
    ) AS delivery_variance_hours,


    -- ========================================================
    -- CANCELLATION STAGE
    -- ========================================================

    CASE

        WHEN o.order_status <> 'cancelled'
        THEN NULL

        WHEN em.payment_confirmed_ts IS NULL
        THEN 'pre_payment'

        WHEN em.inventory_reserved_ts IS NULL
        THEN 'post_payment'

        ELSE 'post_reservation'

    END AS cancellation_stage


FROM orders AS o


LEFT JOIN customers AS c
    ON c.customer_id = o.customer_id


LEFT JOIN warehouses AS w
    ON w.warehouse_id = o.warehouse_id


LEFT JOIN item_metrics AS im
    ON im.order_id = o.order_id


LEFT JOIN shipment_metrics AS sm
    ON sm.order_id = o.order_id


LEFT JOIN event_metrics AS em
    ON em.order_id = o.order_id
;



-- ============================================================
-- VALIDATION 1
-- Basic row-grain validation
-- ============================================================


SELECT

    COUNT(*) AS rows,

    COUNT(
        DISTINCT order_id
    ) AS distinct_orders,

    COUNT(*) -
    COUNT(
        DISTINCT order_id
    ) AS duplicate_order_rows

FROM vw_order_facts;



-- ============================================================
-- VALIDATION 2
-- Reconcile against known FulfillAI totals
-- ============================================================


SELECT

    COUNT(*) AS total_orders,

    SUM(
        is_cancelled
    ) AS cancelled_orders,

    SUM(
        has_shipment
    ) AS shipments,

    SUM(
        is_delivered
    ) AS delivered_orders,

    SUM(
        is_delivery_exception
    ) AS delivery_exceptions,

    SUM(
        order_item_lines
    ) AS order_item_lines,

    SUM(
        units_ordered
    ) AS units_ordered,

    ROUND(
        SUM(
            total_amount
        )::numeric,
        2
    ) AS total_order_value

FROM vw_order_facts;



-- ============================================================
-- VALIDATION 3
-- Model integrity
-- ============================================================


SELECT

    COUNT(*) FILTER (
        WHERE order_item_lines = 0
    ) AS orders_without_items,

    COUNT(*) FILTER (
        WHERE units_ordered <= 0
    ) AS orders_without_positive_units,

    COUNT(*) FILTER (
        WHERE total_amount < 0
    ) AS negative_order_values,

    COUNT(*) FILTER (
        WHERE shipment_count > 1
    ) AS orders_with_multiple_shipments,

    COUNT(*) FILTER (
        WHERE
            is_cancelled = 1
            AND has_shipment = 1
    ) AS cancelled_orders_with_shipments,

    COUNT(*) FILTER (
        WHERE
            is_cancelled = 0
            AND has_shipment = 0
    ) AS active_orders_without_shipments,

    COUNT(*) FILTER (
        WHERE
            is_delivered = 1
            AND delivered_at IS NULL
    ) AS delivered_orders_missing_timestamp,

    COUNT(*) FILTER (
        WHERE
            is_late_delivery = 1
            AND is_delivered = 0
    ) AS late_but_not_delivered,

    COUNT(*) FILTER (
        WHERE lifecycle_event_count = 0
    ) AS orders_without_events

FROM vw_order_facts;



-- ============================================================
-- VALIDATION 4
-- Cancellation stages
-- ============================================================


SELECT

    cancellation_stage,

    COUNT(*) AS orders,

    ROUND(
        COUNT(*) * 100.0
        /
        NULLIF(
            SUM(COUNT(*))
            OVER (),
            0
        ),
        2
    ) AS cancellation_share_pct

FROM vw_order_facts

WHERE
    is_cancelled = 1

GROUP BY
    cancellation_stage

ORDER BY

    CASE cancellation_stage

        WHEN 'pre_payment'
            THEN 1

        WHEN 'post_payment'
            THEN 2

        WHEN 'post_reservation'
            THEN 3

        ELSE 4

    END
;



-- ============================================================
-- VALIDATION 5
-- Preview model
-- ============================================================


SELECT

    order_id,
    order_external_id,

    customer_country_code,

    warehouse_code,

    order_date,

    order_status,

    shipping_method,

    order_item_lines,
    units_ordered,

    total_amount,

    carrier,

    shipment_status,

    is_cancelled,
    is_delivered,
    is_delivery_exception,
    is_late_delivery,

    order_to_ship_hours,
    transit_hours,
    order_to_delivery_hours,

    cancellation_stage

FROM vw_order_facts

ORDER BY
    order_id

LIMIT 10;