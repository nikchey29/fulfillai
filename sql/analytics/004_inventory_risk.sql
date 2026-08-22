-- ============================================================
-- FulfillAI
-- Inventory & Stockout Risk Analytics
-- ============================================================
--
-- Purpose:
--   Combine inventory snapshots, demand and inventory movement
--   history to identify stock pressure and replenishment risk.
--
-- Source tables:
--   inventory
--   inventory_movements
--   orders
--   order_items
--   products
--   product_categories
--   warehouses
--
-- ============================================================


-- ============================================================
-- 1. WAREHOUSE INVENTORY HEALTH
-- ============================================================

WITH demand AS (

    SELECT
        o.warehouse_id,
        oi.product_id,

        COUNT(
            DISTINCT o.order_id
        ) FILTER (
            WHERE o.order_status <> 'cancelled'
        ) AS fulfilled_orders,

        SUM(
            oi.quantity
        ) FILTER (
            WHERE o.order_status <> 'cancelled'
        ) AS fulfilled_units

    FROM orders AS o

    JOIN order_items AS oi
        ON oi.order_id = o.order_id

    GROUP BY
        o.warehouse_id,
        oi.product_id
),


movement_metrics AS (

    SELECT
        warehouse_id,
        product_id,

        COUNT(*) AS movement_count,

        COUNT(*) FILTER (
            WHERE movement_type = 'receipt'
        ) AS receipt_events,

        COUNT(*) FILTER (
            WHERE movement_type = 'reservation'
        ) AS reservation_events,

        COUNT(*) FILTER (
            WHERE movement_type = 'release'
        ) AS release_events,

        COUNT(*) FILTER (
            WHERE movement_type = 'shipment'
        ) AS shipment_events,

        SUM(
            CASE
                WHEN movement_type = 'reservation'
                THEN ABS(quantity_change)
                ELSE 0
            END
        ) AS reservation_units,

        SUM(
            CASE
                WHEN movement_type = 'release'
                THEN ABS(quantity_change)
                ELSE 0
            END
        ) AS release_units,

        SUM(
            CASE
                WHEN movement_type = 'shipment'
                THEN ABS(quantity_change)
                ELSE 0
            END
        ) AS shipped_units,

        SUM(
            CASE
                WHEN movement_type = 'receipt'
                THEN ABS(quantity_change)
                ELSE 0
            END
        ) AS received_units

    FROM inventory_movements

    GROUP BY
        warehouse_id,
        product_id
),


position_metrics AS (

    SELECT
        i.warehouse_id,
        i.product_id,

        i.on_hand_qty,
        i.reserved_qty,
        i.reorder_point,

        GREATEST(
            i.on_hand_qty - i.reserved_qty,
            0
        ) AS available_qty,

        ROUND(
            100.0
            * i.reserved_qty
            / NULLIF(
                i.on_hand_qty,
                0
            ),
            2
        ) AS reserved_pct,

        COALESCE(
            d.fulfilled_orders,
            0
        ) AS fulfilled_orders,

        COALESCE(
            d.fulfilled_units,
            0
        ) AS fulfilled_units,

        ROUND(
            COALESCE(
                d.fulfilled_units,
                0
            ) / 365.0,
            2
        ) AS avg_daily_demand,

        ROUND(
            (
                GREATEST(
                    i.on_hand_qty - i.reserved_qty,
                    0
                )
                /
                NULLIF(
                    COALESCE(
                        d.fulfilled_units,
                        0
                    ) / 365.0,
                    0
                )
            )::numeric,
            2
        ) AS estimated_days_of_supply,

        COALESCE(
            mm.movement_count,
            0
        ) AS movement_count,

        COALESCE(
            mm.receipt_events,
            0
        ) AS receipt_events,

        COALESCE(
            mm.reservation_events,
            0
        ) AS reservation_events,

        COALESCE(
            mm.release_events,
            0
        ) AS release_events,

        COALESCE(
            mm.shipment_events,
            0
        ) AS shipment_events,

        COALESCE(
            mm.reservation_units,
            0
        ) AS reservation_units,

        COALESCE(
            mm.release_units,
            0
        ) AS release_units,

        COALESCE(
            mm.shipped_units,
            0
        ) AS shipped_units,

        COALESCE(
            mm.received_units,
            0
        ) AS received_units

    FROM inventory AS i

    LEFT JOIN demand AS d
        ON d.warehouse_id = i.warehouse_id
        AND d.product_id = i.product_id

    LEFT JOIN movement_metrics AS mm
        ON mm.warehouse_id = i.warehouse_id
        AND mm.product_id = i.product_id
)


SELECT

    w.warehouse_id,
    w.warehouse_code,
    w.warehouse_name,

    COUNT(*) AS inventory_positions,

    SUM(
        pm.on_hand_qty
    ) AS snapshot_on_hand_units,

    SUM(
        pm.reserved_qty
    ) AS reserved_units,

    SUM(
        pm.available_qty
    ) AS available_units,

    SUM(
        pm.fulfilled_units
    ) AS annual_fulfilled_units,

    COUNT(*) FILTER (
        WHERE pm.on_hand_qty <= pm.reorder_point
    ) AS low_stock_positions,

    ROUND(
        100.0
        * COUNT(*) FILTER (
            WHERE pm.on_hand_qty <= pm.reorder_point
        )
        / NULLIF(
            COUNT(*),
            0
        ),
        2
    ) AS low_stock_rate_pct,

    COUNT(*) FILTER (
        WHERE pm.available_qty <= pm.reorder_point
    ) AS available_below_reorder_positions,

    ROUND(
        100.0
        * COUNT(*) FILTER (
            WHERE pm.available_qty <= pm.reorder_point
        )
        / NULLIF(
            COUNT(*),
            0
        ),
        2
    ) AS available_below_reorder_pct,

    SUM(
        pm.movement_count
    ) AS inventory_movements,

    SUM(
        pm.reservation_units
    ) AS reservation_units,

    SUM(
        pm.release_units
    ) AS released_units,

    SUM(
        pm.shipped_units
    ) AS shipped_units,

    SUM(
        pm.received_units
    ) AS received_units

FROM position_metrics AS pm

JOIN warehouses AS w
    ON w.warehouse_id = pm.warehouse_id

GROUP BY
    w.warehouse_id,
    w.warehouse_code,
    w.warehouse_name

ORDER BY
    available_below_reorder_pct DESC,
    w.warehouse_id;


-- ============================================================
-- 2. PRODUCT / WAREHOUSE STOCKOUT RISK
-- ============================================================

WITH demand AS (

    SELECT
        o.warehouse_id,
        oi.product_id,

        COUNT(
            DISTINCT o.order_id
        ) FILTER (
            WHERE o.order_status <> 'cancelled'
        ) AS fulfilled_orders,

        SUM(
            oi.quantity
        ) FILTER (
            WHERE o.order_status <> 'cancelled'
        ) AS fulfilled_units

    FROM orders AS o

    JOIN order_items AS oi
        ON oi.order_id = o.order_id

    GROUP BY
        o.warehouse_id,
        oi.product_id
),


movement_metrics AS (

    SELECT
        warehouse_id,
        product_id,

        COUNT(*) AS total_movements,

        COUNT(*) FILTER (
            WHERE movement_type = 'receipt'
        ) AS receipt_events,

        COUNT(*) FILTER (
            WHERE movement_type = 'reservation'
        ) AS reservation_events,

        COUNT(*) FILTER (
            WHERE movement_type = 'release'
        ) AS release_events,

        COUNT(*) FILTER (
            WHERE movement_type = 'shipment'
        ) AS shipment_events,

        SUM(
            CASE
                WHEN movement_type = 'reservation'
                THEN ABS(quantity_change)
                ELSE 0
            END
        ) AS reservation_units,

        SUM(
            CASE
                WHEN movement_type = 'release'
                THEN ABS(quantity_change)
                ELSE 0
            END
        ) AS released_units,

        SUM(
            CASE
                WHEN movement_type = 'shipment'
                THEN ABS(quantity_change)
                ELSE 0
            END
        ) AS shipped_units,

        SUM(
            CASE
                WHEN movement_type = 'receipt'
                THEN ABS(quantity_change)
                ELSE 0
            END
        ) AS received_units

    FROM inventory_movements

    GROUP BY
        warehouse_id,
        product_id
),


inventory_analysis AS (

    SELECT

        i.warehouse_id,
        w.warehouse_code,
        w.warehouse_name,

        i.product_id,
        p.sku,
        p.product_name,

        pc.category_name,

        i.on_hand_qty,
        i.reserved_qty,
        i.reorder_point,

        GREATEST(
            i.on_hand_qty - i.reserved_qty,
            0
        ) AS available_qty,

        ROUND(
            100.0
            * i.reserved_qty
            / NULLIF(
                i.on_hand_qty,
                0
            ),
            2
        ) AS reserved_pct,

        COALESCE(
            d.fulfilled_orders,
            0
        ) AS fulfilled_orders,

        COALESCE(
            d.fulfilled_units,
            0
        ) AS fulfilled_units,

        ROUND(
            COALESCE(
                d.fulfilled_units,
                0
            ) / 365.0,
            2
        ) AS avg_daily_demand,

        ROUND(
            (
                GREATEST(
                    i.on_hand_qty - i.reserved_qty,
                    0
                )
                /
                NULLIF(
                    COALESCE(
                        d.fulfilled_units,
                        0
                    ) / 365.0,
                    0
                )
            )::numeric,
            2
        ) AS estimated_days_of_supply,

        COALESCE(
            mm.total_movements,
            0
        ) AS total_movements,

        COALESCE(
            mm.receipt_events,
            0
        ) AS receipt_events,

        COALESCE(
            mm.reservation_events,
            0
        ) AS reservation_events,

        COALESCE(
            mm.release_events,
            0
        ) AS release_events,

        COALESCE(
            mm.shipment_events,
            0
        ) AS shipment_events,

        COALESCE(
            mm.reservation_units,
            0
        ) AS reservation_units,

        COALESCE(
            mm.released_units,
            0
        ) AS released_units,

        COALESCE(
            mm.shipped_units,
            0
        ) AS shipped_units,

        COALESCE(
            mm.received_units,
            0
        ) AS received_units

    FROM inventory AS i

    JOIN warehouses AS w
        ON w.warehouse_id = i.warehouse_id

    JOIN products AS p
        ON p.product_id = i.product_id

    JOIN product_categories AS pc
        ON pc.category_id = p.category_id

    LEFT JOIN demand AS d
        ON d.warehouse_id = i.warehouse_id
        AND d.product_id = i.product_id

    LEFT JOIN movement_metrics AS mm
        ON mm.warehouse_id = i.warehouse_id
        AND mm.product_id = i.product_id
),


risk_scored AS (

    SELECT
        *,

        CASE

            WHEN available_qty <= 0
                THEN 'CRITICAL'

            WHEN on_hand_qty <= reorder_point
                THEN 'CRITICAL'

            WHEN available_qty <= reorder_point
                THEN 'HIGH'

            WHEN estimated_days_of_supply IS NOT NULL
                 AND estimated_days_of_supply < 14
                THEN 'HIGH'

            WHEN estimated_days_of_supply IS NOT NULL
                 AND estimated_days_of_supply < 30
                THEN 'MEDIUM'

            ELSE 'HEALTHY'

        END AS risk_level,

        CASE

            WHEN available_qty <= 0
                THEN 100

            WHEN on_hand_qty <= reorder_point
                THEN 90

            WHEN available_qty <= reorder_point
                THEN 80

            WHEN estimated_days_of_supply IS NOT NULL
                 AND estimated_days_of_supply < 14
                THEN 70

            WHEN estimated_days_of_supply IS NOT NULL
                 AND estimated_days_of_supply < 30
                THEN 50

            ELSE 10

        END AS risk_score

    FROM inventory_analysis
)


SELECT

    risk_level,
    risk_score,

    warehouse_id,
    warehouse_code,
    warehouse_name,

    product_id,
    sku,
    product_name,
    category_name,

    on_hand_qty,
    reserved_qty,
    available_qty,
    reorder_point,

    reserved_pct,

    fulfilled_orders,
    fulfilled_units,

    avg_daily_demand,
    estimated_days_of_supply,

    total_movements,

    reservation_events,
    release_events,
    shipment_events,
    receipt_events,

    reservation_units,
    released_units,
    shipped_units,
    received_units

FROM risk_scored

ORDER BY

    risk_score DESC,

    estimated_days_of_supply
        ASC NULLS LAST,

    fulfilled_units DESC,

    warehouse_id,
    product_id

LIMIT 30;