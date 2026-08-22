-- ============================================================================
-- FulfillAI
-- Phase 5.1: Executive KPIs
--
-- Purpose:
--   Provide a single executive-level view of order, revenue, basket,
--   shipment, and delivery performance.
--
-- KPI definitions:
--
--   total_orders
--       All orders created during the simulation.
--
--   completed_orders
--       Orders whose shipment reached "delivered".
--
--   cancelled_orders
--       Orders with order_status = 'cancelled'.
--
--   cancellation_rate_pct
--       Cancelled orders / total orders.
--
--   gross_merchandise_value
--       Total order value for non-cancelled orders.
--
--   average_order_value
--       Average value of non-cancelled orders.
--
--   units_sold
--       Quantity of products belonging to non-cancelled orders.
--
--   average_basket_size
--       Average number of units per non-cancelled order.
--
--   total_shipments
--       Number of generated shipments.
--
--   delivery_success_rate_pct
--       Delivered shipments / total shipments.
--
--   exception_rate_pct
--       Exception shipments / total shipments.
--
--   late_delivery_rate_pct
--       Delivered shipments arriving after expected_delivery_at /
--       all delivered shipments.
-- ============================================================================


WITH order_metrics AS (

    SELECT
        COUNT(*) AS total_orders,

        COUNT(*) FILTER (
            WHERE order_status = 'cancelled'
        ) AS cancelled_orders,

        ROUND(
            100.0
            * COUNT(*) FILTER (
                WHERE order_status = 'cancelled'
            )
            / NULLIF(COUNT(*), 0),
            2
        ) AS cancellation_rate_pct,

        ROUND(
            SUM(total_amount) FILTER (
                WHERE order_status <> 'cancelled'
            ),
            2
        ) AS gross_merchandise_value,

        ROUND(
            AVG(total_amount) FILTER (
                WHERE order_status <> 'cancelled'
            ),
            2
        ) AS average_order_value

    FROM orders
),


order_baskets AS (

    SELECT
        o.order_id,
        SUM(oi.quantity) AS units

    FROM orders AS o

    JOIN order_items AS oi
        ON oi.order_id = o.order_id

    WHERE o.order_status <> 'cancelled'

    GROUP BY
        o.order_id
),


basket_metrics AS (

    SELECT
        COALESCE(
            SUM(units),
            0
        )::BIGINT AS units_sold,

        ROUND(
            AVG(units),
            2
        ) AS average_basket_size

    FROM order_baskets
),


shipment_metrics AS (

    SELECT

        COUNT(*) AS total_shipments,

        COUNT(*) FILTER (
            WHERE shipment_status = 'delivered'
        ) AS completed_orders,

        ROUND(
            100.0
            * COUNT(*) FILTER (
                WHERE shipment_status = 'delivered'
            )
            / NULLIF(COUNT(*), 0),
            2
        ) AS delivery_success_rate_pct,

        ROUND(
            100.0
            * COUNT(*) FILTER (
                WHERE shipment_status = 'exception'
            )
            / NULLIF(COUNT(*), 0),
            2
        ) AS exception_rate_pct,

        ROUND(
            100.0
            * COUNT(*) FILTER (
                WHERE shipment_status = 'delivered'
                  AND delivered_at > expected_delivery_at
            )
            / NULLIF(
                COUNT(*) FILTER (
                    WHERE shipment_status = 'delivered'
                ),
                0
            ),
            2
        ) AS late_delivery_rate_pct

    FROM shipments
)


SELECT

    om.total_orders,

    sm.completed_orders,

    om.cancelled_orders,

    om.cancellation_rate_pct,

    om.gross_merchandise_value,

    om.average_order_value,

    bm.units_sold,

    bm.average_basket_size,

    sm.total_shipments,

    sm.delivery_success_rate_pct,

    sm.exception_rate_pct,

    sm.late_delivery_rate_pct

FROM order_metrics AS om

CROSS JOIN basket_metrics AS bm

CROSS JOIN shipment_metrics AS sm;