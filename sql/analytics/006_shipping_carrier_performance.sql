-- ============================================================
-- FulfillAI
-- Shipping & Carrier Performance Analytics
-- ============================================================
--
-- Purpose:
--
--   Analyze fulfillment-carrier performance across:
--
--     - shipment volume
--     - delivery success
--     - delivery exceptions
--     - late delivery
--     - transit time
--     - shipping cost
--     - shipping method
--     - warehouse/carrier combinations
--
-- Source tables:
--
--   shipments
--   orders
--   warehouses
--
-- ============================================================



-- ============================================================
-- TEMPORARY ANALYTICAL BASE
-- ============================================================

DROP VIEW IF EXISTS shipping_performance_base;


CREATE TEMP VIEW shipping_performance_base AS

SELECT

    s.shipment_id,
    s.shipment_external_id,

    s.order_id,
    s.warehouse_id,

    w.warehouse_code,
    w.warehouse_name,
    w.city,
    w.country_code,

    s.carrier,

    o.shipping_method,

    s.shipment_status,

    s.created_at AS shipment_created_at,
    s.shipped_at,
    s.expected_delivery_at,
    s.delivered_at,

    s.shipping_cost,

    CASE
        WHEN s.shipment_status = 'delivered'
        THEN 1
        ELSE 0
    END AS delivered_flag,

    CASE
        WHEN s.shipment_status = 'exception'
        THEN 1
        ELSE 0
    END AS exception_flag,

    CASE
        WHEN
            s.shipment_status = 'delivered'
            AND s.delivered_at > s.expected_delivery_at
        THEN 1
        ELSE 0
    END AS late_flag,

    CASE
        WHEN
            s.shipment_status = 'delivered'
            AND s.delivered_at <= s.expected_delivery_at
        THEN 1
        ELSE 0
    END AS on_time_flag,

    CASE
        WHEN
            s.shipped_at IS NOT NULL
            AND s.delivered_at IS NOT NULL
        THEN
            EXTRACT(
                EPOCH FROM (
                    s.delivered_at
                    - s.shipped_at
                )
            ) / 3600.0
        ELSE NULL
    END AS actual_transit_hours,

    CASE
        WHEN
            s.shipped_at IS NOT NULL
            AND s.expected_delivery_at IS NOT NULL
        THEN
            EXTRACT(
                EPOCH FROM (
                    s.expected_delivery_at
                    - s.shipped_at
                )
            ) / 3600.0
        ELSE NULL
    END AS expected_transit_hours,

    CASE
        WHEN
            s.shipment_status = 'delivered'
            AND s.delivered_at > s.expected_delivery_at
        THEN
            EXTRACT(
                EPOCH FROM (
                    s.delivered_at
                    - s.expected_delivery_at
                )
            ) / 3600.0
        ELSE NULL
    END AS delay_hours

FROM shipments AS s

JOIN orders AS o
    ON o.order_id = s.order_id

JOIN warehouses AS w
    ON w.warehouse_id = s.warehouse_id;



-- ============================================================
-- 1. CARRIER PERFORMANCE
-- ============================================================

SELECT

    carrier,

    COUNT(*) AS shipments,

    ROUND(
        COUNT(*) * 100.0
        / SUM(COUNT(*)) OVER (),
        2
    ) AS shipment_share_pct,

    SUM(delivered_flag) AS delivered,

    SUM(exception_flag) AS exceptions,

    ROUND(
        SUM(delivered_flag) * 100.0
        / NULLIF(COUNT(*), 0),
        2
    ) AS delivery_success_rate_pct,

    ROUND(
        SUM(exception_flag) * 100.0
        / NULLIF(COUNT(*), 0),
        2
    ) AS exception_rate_pct,

    SUM(late_flag) AS late_deliveries,

    ROUND(
        SUM(late_flag) * 100.0
        / NULLIF(
            SUM(delivered_flag),
            0
        ),
        2
    ) AS late_delivery_rate_pct,

    SUM(on_time_flag) AS on_time_deliveries,

    ROUND(
        SUM(on_time_flag) * 100.0
        / NULLIF(
            SUM(delivered_flag),
            0
        ),
        2
    ) AS on_time_delivery_rate_pct,

    ROUND(
        AVG(
            actual_transit_hours
        )::numeric,
        2
    ) AS avg_transit_hours,

    ROUND(
        PERCENTILE_CONT(0.5)
        WITHIN GROUP (
            ORDER BY actual_transit_hours
        )::numeric,
        2
    ) AS median_transit_hours,

    ROUND(
        PERCENTILE_CONT(0.95)
        WITHIN GROUP (
            ORDER BY actual_transit_hours
        )::numeric,
        2
    ) AS p95_transit_hours,

    ROUND(
        AVG(
            delay_hours
        )::numeric,
        2
    ) AS avg_late_delay_hours,

    ROUND(
        AVG(
            shipping_cost
        )::numeric,
        2
    ) AS avg_shipping_cost,

    ROUND(
        SUM(
            shipping_cost
        )::numeric,
        2
    ) AS total_shipping_cost

FROM shipping_performance_base

GROUP BY
    carrier

ORDER BY
    shipments DESC;



-- ============================================================
-- 2. SHIPPING METHOD PERFORMANCE
-- ============================================================

SELECT

    shipping_method,

    COUNT(*) AS shipments,

    ROUND(
        COUNT(*) * 100.0
        / SUM(COUNT(*)) OVER (),
        2
    ) AS shipment_share_pct,

    SUM(delivered_flag) AS delivered,

    SUM(exception_flag) AS exceptions,

    SUM(late_flag) AS late_deliveries,

    ROUND(
        SUM(delivered_flag) * 100.0
        / NULLIF(
            COUNT(*),
            0
        ),
        2
    ) AS delivery_success_rate_pct,

    ROUND(
        SUM(exception_flag) * 100.0
        / NULLIF(
            COUNT(*),
            0
        ),
        2
    ) AS exception_rate_pct,

    ROUND(
        SUM(late_flag) * 100.0
        / NULLIF(
            SUM(delivered_flag),
            0
        ),
        2
    ) AS late_delivery_rate_pct,

    ROUND(
        AVG(
            actual_transit_hours
        )::numeric,
        2
    ) AS avg_actual_transit_hours,

    ROUND(
        AVG(
            expected_transit_hours
        )::numeric,
        2
    ) AS avg_expected_transit_hours,

    ROUND(
        AVG(
            shipping_cost
        )::numeric,
        2
    ) AS avg_shipping_cost,

    ROUND(
        SUM(
            shipping_cost
        )::numeric,
        2
    ) AS total_shipping_cost

FROM shipping_performance_base

GROUP BY
    shipping_method

ORDER BY

    CASE shipping_method

        WHEN 'standard'
            THEN 1

        WHEN 'express'
            THEN 2

        WHEN 'same_day'
            THEN 3

        ELSE 4

    END;



-- ============================================================
-- 3. CARRIER × SHIPPING METHOD PERFORMANCE
-- ============================================================

SELECT

    carrier,
    shipping_method,

    COUNT(*) AS shipments,

    ROUND(
        COUNT(*) * 100.0
        /
        SUM(COUNT(*))
        OVER (
            PARTITION BY shipping_method
        ),
        2
    ) AS method_carrier_share_pct,

    SUM(delivered_flag) AS delivered,

    SUM(exception_flag) AS exceptions,

    SUM(late_flag) AS late_deliveries,

    ROUND(
        SUM(exception_flag) * 100.0
        / NULLIF(
            COUNT(*),
            0
        ),
        2
    ) AS exception_rate_pct,

    ROUND(
        SUM(late_flag) * 100.0
        / NULLIF(
            SUM(delivered_flag),
            0
        ),
        2
    ) AS late_delivery_rate_pct,

    ROUND(
        AVG(
            actual_transit_hours
        )::numeric,
        2
    ) AS avg_transit_hours,

    ROUND(
        AVG(
            shipping_cost
        )::numeric,
        2
    ) AS avg_shipping_cost,

    ROUND(
        SUM(
            shipping_cost
        )::numeric,
        2
    ) AS total_shipping_cost

FROM shipping_performance_base

GROUP BY
    carrier,
    shipping_method

ORDER BY

    shipping_method,

    shipments DESC;



-- ============================================================
-- 4. WAREHOUSE × CARRIER PERFORMANCE
-- ============================================================

SELECT

    warehouse_id,
    warehouse_code,
    warehouse_name,
    city,
    country_code,

    carrier,

    COUNT(*) AS shipments,

    SUM(delivered_flag) AS delivered,

    SUM(exception_flag) AS exceptions,

    SUM(late_flag) AS late_deliveries,

    ROUND(
        SUM(delivered_flag) * 100.0
        / NULLIF(
            COUNT(*),
            0
        ),
        2
    ) AS delivery_success_rate_pct,

    ROUND(
        SUM(exception_flag) * 100.0
        / NULLIF(
            COUNT(*),
            0
        ),
        2
    ) AS exception_rate_pct,

    ROUND(
        SUM(late_flag) * 100.0
        / NULLIF(
            SUM(delivered_flag),
            0
        ),
        2
    ) AS late_delivery_rate_pct,

    ROUND(
        AVG(
            actual_transit_hours
        )::numeric,
        2
    ) AS avg_transit_hours,

    ROUND(
        AVG(
            shipping_cost
        )::numeric,
        2
    ) AS avg_shipping_cost,

    ROUND(
        SUM(
            shipping_cost
        )::numeric,
        2
    ) AS total_shipping_cost

FROM shipping_performance_base

GROUP BY

    warehouse_id,
    warehouse_code,
    warehouse_name,
    city,
    country_code,
    carrier

ORDER BY

    warehouse_id,
    shipments DESC;



-- ============================================================
-- 5. CARRIER COST / PERFORMANCE SCORECARD
-- ============================================================

WITH carrier_metrics AS (

    SELECT

        carrier,

        COUNT(*) AS shipments,

        SUM(delivered_flag) AS delivered,

        SUM(exception_flag) AS exceptions,

        SUM(late_flag) AS late_deliveries,

        AVG(
            actual_transit_hours
        ) AS avg_transit_hours,

        AVG(
            shipping_cost
        ) AS avg_shipping_cost

    FROM shipping_performance_base

    GROUP BY
        carrier
)


SELECT

    carrier,

    shipments,

    ROUND(
        delivered * 100.0
        / NULLIF(
            shipments,
            0
        ),
        2
    ) AS delivery_success_rate_pct,

    ROUND(
        exceptions * 100.0
        / NULLIF(
            shipments,
            0
        ),
        2
    ) AS exception_rate_pct,

    ROUND(
        late_deliveries * 100.0
        / NULLIF(
            delivered,
            0
        ),
        2
    ) AS late_delivery_rate_pct,

    ROUND(
        avg_transit_hours::numeric,
        2
    ) AS avg_transit_hours,

    ROUND(
        avg_shipping_cost::numeric,
        2
    ) AS avg_shipping_cost,

    DENSE_RANK()
    OVER (
        ORDER BY
            exceptions * 1.0
            / NULLIF(
                shipments,
                0
            )
    ) AS reliability_rank,

    DENSE_RANK()
    OVER (
        ORDER BY
            avg_transit_hours
            NULLS LAST
    ) AS speed_rank,

    DENSE_RANK()
    OVER (
        ORDER BY
            avg_shipping_cost
            NULLS LAST
    ) AS cost_rank

FROM carrier_metrics

ORDER BY
    reliability_rank,
    speed_rank,
    cost_rank;



-- ============================================================
-- 6. SHIPPING DATA QUALITY AUDIT
-- ============================================================

SELECT

    COUNT(*) FILTER (
        WHERE shipment_id IS NULL
    ) AS null_shipment_ids,

    COUNT(*) - COUNT(
        DISTINCT shipment_id
    ) AS duplicate_shipment_ids,

    COUNT(*) FILTER (
        WHERE order_id IS NULL
    ) AS null_order_references,

    COUNT(*) FILTER (
        WHERE warehouse_id IS NULL
    ) AS null_warehouse_references,

    COUNT(*) FILTER (
        WHERE carrier IS NULL
    ) AS missing_carriers,

    COUNT(*) FILTER (
        WHERE shipping_method IS NULL
    ) AS missing_shipping_methods,

    COUNT(*) FILTER (
        WHERE shipping_cost < 0
    ) AS negative_shipping_costs,

    COUNT(*) FILTER (
        WHERE shipped_at IS NULL
    ) AS missing_shipped_timestamps,

    COUNT(*) FILTER (
        WHERE expected_delivery_at IS NULL
    ) AS missing_expected_delivery_timestamps,

    COUNT(*) FILTER (
        WHERE
            shipment_status = 'delivered'
            AND delivered_at IS NULL
    ) AS delivered_missing_delivery_timestamp,

    COUNT(*) FILTER (
        WHERE
            shipped_at IS NOT NULL
            AND shipment_created_at IS NOT NULL
            AND shipped_at < shipment_created_at
    ) AS shipped_before_shipment_created,

    COUNT(*) FILTER (
        WHERE
            expected_delivery_at IS NOT NULL
            AND shipped_at IS NOT NULL
            AND expected_delivery_at < shipped_at
    ) AS expected_delivery_before_shipment,

    COUNT(*) FILTER (
        WHERE
            delivered_at IS NOT NULL
            AND shipped_at IS NOT NULL
            AND delivered_at < shipped_at
    ) AS delivery_before_shipment

FROM shipping_performance_base;



-- ============================================================
-- 7. GLOBAL SHIPPING RECONCILIATION
-- ============================================================

SELECT

    COUNT(*) AS total_shipments,

    SUM(delivered_flag) AS delivered,

    SUM(exception_flag) AS exceptions,

    SUM(late_flag) AS late_deliveries,

    SUM(on_time_flag) AS on_time_deliveries,

    ROUND(
        SUM(delivered_flag) * 100.0
        / NULLIF(
            COUNT(*),
            0
        ),
        2
    ) AS delivery_success_rate_pct,

    ROUND(
        SUM(exception_flag) * 100.0
        / NULLIF(
            COUNT(*),
            0
        ),
        2
    ) AS exception_rate_pct,

    ROUND(
        SUM(late_flag) * 100.0
        / NULLIF(
            SUM(delivered_flag),
            0
        ),
        2
    ) AS late_delivery_rate_pct,

    ROUND(
        AVG(
            actual_transit_hours
        )::numeric,
        2
    ) AS avg_transit_hours,

    ROUND(
        AVG(
            shipping_cost
        )::numeric,
        2
    ) AS avg_shipping_cost,

    ROUND(
        SUM(
            shipping_cost
        )::numeric,
        2
    ) AS total_shipping_cost

FROM shipping_performance_base;