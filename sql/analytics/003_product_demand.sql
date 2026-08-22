-- ============================================================
-- FulfillAI
-- Product & Demand Analytics
-- ============================================================
--
-- Purpose:
--   Analyze demand, revenue, margin, fulfillment performance,
--   cancellation exposure, and inventory health by category
--   and product.
--
-- Source tables:
--   product_categories
--   products
--   orders
--   order_items
--   shipments
--   inventory
--
-- ============================================================


-- ============================================================
-- 1. CATEGORY PERFORMANCE
-- ============================================================

WITH item_base AS (

    SELECT
        oi.order_id,
        oi.product_id,
        oi.quantity,
        oi.unit_price,

        o.order_status,

        p.category_id,
        p.unit_cost

    FROM order_items AS oi

    JOIN orders AS o
        ON o.order_id = oi.order_id

    JOIN products AS p
        ON p.product_id = oi.product_id
),

category_metrics AS (

    SELECT
        pc.category_id,
        pc.category_name,

        COUNT(
            DISTINCT ib.product_id
        ) AS products_sold,

        COUNT(
            DISTINCT ib.order_id
        ) AS orders_containing_category,

        COUNT(
            DISTINCT ib.order_id
        ) FILTER (
            WHERE ib.order_status = 'cancelled'
        ) AS cancelled_orders,

        SUM(
            ib.quantity
        ) AS units_ordered,

        SUM(
            ib.quantity
        ) FILTER (
            WHERE ib.order_status <> 'cancelled'
        ) AS fulfilled_units,

        ROUND(
            SUM(
                ib.quantity
                * ib.unit_price
            ),
            2
        ) AS gross_demand_value,

        ROUND(
            SUM(
                ib.quantity
                * ib.unit_price
            ) FILTER (
                WHERE ib.order_status <> 'cancelled'
            ),
            2
        ) AS fulfilled_revenue,

        ROUND(
            SUM(
                (
                    ib.unit_price
                    - ib.unit_cost
                )
                * ib.quantity
            ) FILTER (
                WHERE ib.order_status <> 'cancelled'
            ),
            2
        ) AS gross_margin_value,

        ROUND(
            100.0
            * COUNT(
                DISTINCT ib.order_id
            ) FILTER (
                WHERE ib.order_status = 'cancelled'
            )
            / NULLIF(
                COUNT(
                    DISTINCT ib.order_id
                ),
                0
            ),
            2
        ) AS cancellation_exposure_pct

    FROM product_categories AS pc

    LEFT JOIN item_base AS ib
        ON ib.category_id = pc.category_id

    GROUP BY
        pc.category_id,
        pc.category_name
)

SELECT

    category_id,
    category_name,

    products_sold,
    orders_containing_category,
    cancelled_orders,

    units_ordered,
    fulfilled_units,

    gross_demand_value,
    fulfilled_revenue,
    gross_margin_value,

    cancellation_exposure_pct,

    ROUND(
        100.0
        * fulfilled_revenue
        / NULLIF(
            SUM(
                fulfilled_revenue
            ) OVER (),
            0
        ),
        2
    ) AS revenue_share_pct

FROM category_metrics

ORDER BY
    fulfilled_revenue DESC,
    category_id;


-- ============================================================
-- 2. TOP PRODUCT PERFORMANCE
-- ============================================================

WITH item_metrics AS (

    SELECT
        oi.product_id,

        COUNT(
            DISTINCT oi.order_id
        ) AS order_count,

        COUNT(
            DISTINCT oi.order_id
        ) FILTER (
            WHERE o.order_status = 'cancelled'
        ) AS cancelled_order_count,

        SUM(
            oi.quantity
        ) AS units_ordered,

        SUM(
            oi.quantity
        ) FILTER (
            WHERE o.order_status <> 'cancelled'
        ) AS fulfilled_units,

        ROUND(
            SUM(
                oi.quantity
                * oi.unit_price
            ),
            2
        ) AS gross_demand_value,

        ROUND(
            SUM(
                oi.quantity
                * oi.unit_price
            ) FILTER (
                WHERE o.order_status <> 'cancelled'
            ),
            2
        ) AS fulfilled_revenue,

        ROUND(
            SUM(
                (
                    oi.unit_price
                    - p.unit_cost
                )
                * oi.quantity
            ) FILTER (
                WHERE o.order_status <> 'cancelled'
            ),
            2
        ) AS gross_margin_value

    FROM order_items AS oi

    JOIN orders AS o
        ON o.order_id = oi.order_id

    JOIN products AS p
        ON p.product_id = oi.product_id

    GROUP BY
        oi.product_id
),


shipment_metrics AS (

    SELECT
        oi.product_id,

        COUNT(
            DISTINCT s.shipment_id
        ) AS shipments,

        COUNT(
            DISTINCT s.shipment_id
        ) FILTER (
            WHERE s.shipment_status = 'delivered'
        ) AS delivered_shipments,

        COUNT(
            DISTINCT s.shipment_id
        ) FILTER (
            WHERE s.shipment_status = 'exception'
        ) AS exception_shipments,

        COUNT(
            DISTINCT s.shipment_id
        ) FILTER (
            WHERE
                s.shipment_status = 'delivered'
                AND s.delivered_at
                    > s.expected_delivery_at
        ) AS late_deliveries

    FROM order_items AS oi

    JOIN shipments AS s
        ON s.order_id = oi.order_id

    GROUP BY
        oi.product_id
),


inventory_metrics AS (

    SELECT
        product_id,

        COUNT(*) AS inventory_positions,

        COUNT(
            DISTINCT warehouse_id
        ) AS stocked_warehouses,

        SUM(
            on_hand_qty
        ) AS total_on_hand_qty,

        SUM(
            reserved_qty
        ) AS total_reserved_qty,

        COUNT(*) FILTER (
            WHERE on_hand_qty <= reorder_point
        ) AS low_stock_positions,

        ROUND(
            100.0
            * COUNT(*) FILTER (
                WHERE on_hand_qty <= reorder_point
            )
            / NULLIF(
                COUNT(*),
                0
            ),
            2
        ) AS low_stock_position_pct

    FROM inventory

    GROUP BY
        product_id
),


product_analysis AS (

    SELECT

        p.product_id,
        p.sku,
        p.product_name,

        pc.category_name,

        p.unit_price,
        p.unit_cost,

        COALESCE(
            im.order_count,
            0
        ) AS order_count,

        COALESCE(
            im.cancelled_order_count,
            0
        ) AS cancelled_order_count,

        ROUND(
            100.0
            * COALESCE(
                im.cancelled_order_count,
                0
            )
            / NULLIF(
                im.order_count,
                0
            ),
            2
        ) AS cancellation_exposure_pct,

        COALESCE(
            im.units_ordered,
            0
        ) AS units_ordered,

        COALESCE(
            im.fulfilled_units,
            0
        ) AS fulfilled_units,

        COALESCE(
            im.gross_demand_value,
            0
        ) AS gross_demand_value,

        COALESCE(
            im.fulfilled_revenue,
            0
        ) AS fulfilled_revenue,

        COALESCE(
            im.gross_margin_value,
            0
        ) AS gross_margin_value,

        ROUND(
            100.0
            * COALESCE(
                im.gross_margin_value,
                0
            )
            / NULLIF(
                im.fulfilled_revenue,
                0
            ),
            2
        ) AS gross_margin_pct,

        COALESCE(
            sm.shipments,
            0
        ) AS shipments,

        COALESCE(
            sm.delivered_shipments,
            0
        ) AS delivered_shipments,

        COALESCE(
            sm.exception_shipments,
            0
        ) AS exception_shipments,

        ROUND(
            100.0
            * COALESCE(
                sm.exception_shipments,
                0
            )
            / NULLIF(
                sm.shipments,
                0
            ),
            2
        ) AS shipment_exception_rate_pct,

        COALESCE(
            sm.late_deliveries,
            0
        ) AS late_deliveries,

        ROUND(
            100.0
            * COALESCE(
                sm.late_deliveries,
                0
            )
            / NULLIF(
                sm.delivered_shipments,
                0
            ),
            2
        ) AS late_delivery_rate_pct,

        COALESCE(
            iv.inventory_positions,
            0
        ) AS inventory_positions,

        COALESCE(
            iv.stocked_warehouses,
            0
        ) AS stocked_warehouses,

        COALESCE(
            iv.total_on_hand_qty,
            0
        ) AS total_on_hand_qty,

        COALESCE(
            iv.total_reserved_qty,
            0
        ) AS total_reserved_qty,

        COALESCE(
            iv.low_stock_positions,
            0
        ) AS low_stock_positions,

        COALESCE(
            iv.low_stock_position_pct,
            0
        ) AS low_stock_position_pct

    FROM products AS p

    JOIN product_categories AS pc
        ON pc.category_id = p.category_id

    LEFT JOIN item_metrics AS im
        ON im.product_id = p.product_id

    LEFT JOIN shipment_metrics AS sm
        ON sm.product_id = p.product_id

    LEFT JOIN inventory_metrics AS iv
        ON iv.product_id = p.product_id
)


SELECT

    DENSE_RANK() OVER (
        ORDER BY fulfilled_revenue DESC
    ) AS revenue_rank,

    DENSE_RANK() OVER (
        ORDER BY fulfilled_units DESC
    ) AS unit_demand_rank,

    product_id,
    sku,
    product_name,
    category_name,

    unit_price,
    unit_cost,

    order_count,
    cancelled_order_count,
    cancellation_exposure_pct,

    units_ordered,
    fulfilled_units,

    gross_demand_value,
    fulfilled_revenue,

    gross_margin_value,
    gross_margin_pct,

    shipments,
    delivered_shipments,
    exception_shipments,
    shipment_exception_rate_pct,

    late_deliveries,
    late_delivery_rate_pct,

    inventory_positions,
    stocked_warehouses,

    total_on_hand_qty,
    total_reserved_qty,

    low_stock_positions,
    low_stock_position_pct

FROM product_analysis

ORDER BY
    fulfilled_revenue DESC,
    product_id

LIMIT 20;
