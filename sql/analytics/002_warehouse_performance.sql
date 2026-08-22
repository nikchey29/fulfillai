-- ============================================================
-- FulfillAI
-- Warehouse Performance Analytics
-- ============================================================
--
-- Purpose:
--   Compare fulfillment performance across warehouses using
--   order volume, cancellations, shipment performance,
--   delivery latency, shipping cost, and inventory health.
--
-- Source tables:
--   warehouses
--   orders
--   order_items
--   shipments
--   inventory
--
-- ============================================================


WITH order_metrics AS (

    SELECT
        warehouse_id,

        COUNT(*) AS total_orders,

        COUNT(*) FILTER (
            WHERE order_status = 'cancelled'
        ) AS cancelled_orders,

        COUNT(*) FILTER (
            WHERE order_status <> 'cancelled'
        ) AS non_cancelled_orders,

        ROUND(
            100.0
            * COUNT(*) FILTER (
                WHERE order_status = 'cancelled'
            )
            / NULLIF(COUNT(*), 0),
            2
        ) AS cancellation_rate_pct,

        ROUND(
            SUM(total_amount),
            2
        ) AS gross_order_value,

        ROUND(
            AVG(total_amount),
            2
        ) AS average_order_value

    FROM orders

    GROUP BY warehouse_id
),


item_metrics AS (

    SELECT
        o.warehouse_id,

        COUNT(oi.order_item_id)
            AS order_item_lines,

        SUM(oi.quantity)
            AS units_ordered,

        ROUND(
            SUM(oi.quantity)::numeric
            / NULLIF(
                COUNT(DISTINCT o.order_id),
                0
            ),
            2
        ) AS average_units_per_order

    FROM orders AS o

    JOIN order_items AS oi
        ON oi.order_id = o.order_id

    GROUP BY o.warehouse_id
),


shipment_metrics AS (

    SELECT
        s.warehouse_id,

        COUNT(*) AS total_shipments,

        COUNT(*) FILTER (
            WHERE s.shipment_status = 'delivered'
        ) AS delivered_shipments,

        COUNT(*) FILTER (
            WHERE s.shipment_status = 'exception'
        ) AS exception_shipments,

        COUNT(*) FILTER (
            WHERE
                s.shipment_status = 'delivered'
                AND s.delivered_at > s.expected_delivery_at
        ) AS late_deliveries,

        ROUND(
            100.0
            * COUNT(*) FILTER (
                WHERE s.shipment_status = 'delivered'
            )
            / NULLIF(COUNT(*), 0),
            2
        ) AS delivery_success_rate_pct,

        ROUND(
            100.0
            * COUNT(*) FILTER (
                WHERE s.shipment_status = 'exception'
            )
            / NULLIF(COUNT(*), 0),
            2
        ) AS exception_rate_pct,

        ROUND(
            100.0
            * COUNT(*) FILTER (
                WHERE
                    s.shipment_status = 'delivered'
                    AND s.delivered_at > s.expected_delivery_at
            )
            / NULLIF(
                COUNT(*) FILTER (
                    WHERE s.shipment_status = 'delivered'
                ),
                0
            ),
            2
        ) AS late_delivery_rate_pct,

        ROUND(
            (
                AVG(
                    EXTRACT(
                        EPOCH FROM (
                            s.shipped_at - o.order_ts
                        )
                    ) / 3600.0
                )
            )::numeric,
            2
        ) AS average_fulfillment_hours,

        ROUND(
            (
                AVG(
                    EXTRACT(
                        EPOCH FROM (
                            s.delivered_at - s.shipped_at
                        )
                    ) / 3600.0
                )
                FILTER (
                    WHERE
                        s.shipment_status = 'delivered'
                        AND s.delivered_at IS NOT NULL
                )
            )::numeric,
            2
        ) AS average_transit_hours,

        ROUND(
            SUM(
                COALESCE(
                    s.shipping_cost,
                    0
                )
            ),
            2
        ) AS total_shipping_cost,

        ROUND(
            AVG(
                COALESCE(
                    s.shipping_cost,
                    0
                )
            ),
            2
        ) AS average_shipping_cost

    FROM shipments AS s

    JOIN orders AS o
        ON o.order_id = s.order_id

    GROUP BY s.warehouse_id
),


inventory_metrics AS (

    SELECT
        warehouse_id,

        COUNT(*) AS inventory_positions,

        SUM(on_hand_qty)
            AS on_hand_units,

        SUM(reserved_qty)
            AS reserved_units,

        COUNT(*) FILTER (
            WHERE on_hand_qty <= reorder_point
        ) AS low_stock_positions,

        ROUND(
            100.0
            * COUNT(*) FILTER (
                WHERE on_hand_qty <= reorder_point
            )
            / NULLIF(COUNT(*), 0),
            2
        ) AS low_stock_rate_pct

    FROM inventory

    GROUP BY warehouse_id
)


SELECT

    w.warehouse_id,

    w.warehouse_code,

    w.warehouse_name,

    w.city,

    w.country_code,

    w.capacity_units,

    -- --------------------------------------------------------
    -- Order performance
    -- --------------------------------------------------------

    COALESCE(
        om.total_orders,
        0
    ) AS total_orders,

    COALESCE(
        om.non_cancelled_orders,
        0
    ) AS non_cancelled_orders,

    COALESCE(
        om.cancelled_orders,
        0
    ) AS cancelled_orders,

    COALESCE(
        om.cancellation_rate_pct,
        0
    ) AS cancellation_rate_pct,

    COALESCE(
        om.gross_order_value,
        0
    ) AS gross_order_value,

    COALESCE(
        om.average_order_value,
        0
    ) AS average_order_value,

    -- --------------------------------------------------------
    -- Basket / demand
    -- --------------------------------------------------------

    COALESCE(
        im.order_item_lines,
        0
    ) AS order_item_lines,

    COALESCE(
        im.units_ordered,
        0
    ) AS units_ordered,

    COALESCE(
        im.average_units_per_order,
        0
    ) AS average_units_per_order,

    -- --------------------------------------------------------
    -- Shipment performance
    -- --------------------------------------------------------

    COALESCE(
        sm.total_shipments,
        0
    ) AS total_shipments,

    COALESCE(
        sm.delivered_shipments,
        0
    ) AS delivered_shipments,

    COALESCE(
        sm.exception_shipments,
        0
    ) AS exception_shipments,

    COALESCE(
        sm.late_deliveries,
        0
    ) AS late_deliveries,

    COALESCE(
        sm.delivery_success_rate_pct,
        0
    ) AS delivery_success_rate_pct,

    COALESCE(
        sm.exception_rate_pct,
        0
    ) AS exception_rate_pct,

    COALESCE(
        sm.late_delivery_rate_pct,
        0
    ) AS late_delivery_rate_pct,

    COALESCE(
        sm.average_fulfillment_hours,
        0
    ) AS average_fulfillment_hours,

    COALESCE(
        sm.average_transit_hours,
        0
    ) AS average_transit_hours,

    COALESCE(
        sm.total_shipping_cost,
        0
    ) AS total_shipping_cost,

    COALESCE(
        sm.average_shipping_cost,
        0
    ) AS average_shipping_cost,

    -- --------------------------------------------------------
    -- Inventory health
    -- --------------------------------------------------------

    COALESCE(
        iv.inventory_positions,
        0
    ) AS inventory_positions,

    COALESCE(
        iv.on_hand_units,
        0
    ) AS on_hand_units,

    COALESCE(
        iv.reserved_units,
        0
    ) AS reserved_units,

    COALESCE(
        iv.low_stock_positions,
        0
    ) AS low_stock_positions,

    COALESCE(
        iv.low_stock_rate_pct,
        0
    ) AS low_stock_rate_pct

FROM warehouses AS w

LEFT JOIN order_metrics AS om
    ON om.warehouse_id = w.warehouse_id

LEFT JOIN item_metrics AS im
    ON im.warehouse_id = w.warehouse_id

LEFT JOIN shipment_metrics AS sm
    ON sm.warehouse_id = w.warehouse_id

LEFT JOIN inventory_metrics AS iv
    ON iv.warehouse_id = w.warehouse_id

ORDER BY
    total_orders DESC,
    w.warehouse_id;