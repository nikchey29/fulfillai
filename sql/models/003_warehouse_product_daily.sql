-- ============================================================
-- FulfillAI
-- Model 003: Warehouse Product Daily
-- ============================================================
--
-- Grain:
--
--     one row per
--
--         demand_date
--         warehouse_id
--         product_id
--
-- Foundation:
--
--     vw_daily_product_demand
--              +
--     inventory_movements
--
-- Purpose:
--
--     Reconstruct operational inventory state through time
--     and combine it with historical demand.
--
-- Supports:
--
--     inventory planning
--     stockout-risk modeling
--     replenishment recommendations
--     warehouse/product monitoring
--     demand forecasting
--     ML feature engineering
--
-- Important accounting semantics:
--
--     receipt:
--         increases physical on-hand inventory
--
--     reservation:
--         increases reserved inventory
--
--     release:
--         decreases reserved inventory
--
--     shipment:
--         decreases physical on-hand inventory
--         and consumes the corresponding reservation
--
-- Therefore:
--
--     on_hand change =
--         receipts - shipments
--
--     reserved change =
--         reservations - releases - shipments
--
--     available =
--         on_hand - reserved
--
-- ============================================================


CREATE OR REPLACE VIEW vw_warehouse_product_daily AS


WITH model_bounds AS (

    SELECT

        MIN(demand_date) AS first_date,

        MAX(demand_date) AS last_date

    FROM vw_daily_product_demand
),


-- ============================================================
-- Daily movement ledger
--
-- quantity_change is signed in the raw ledger. We convert
-- each business event to a positive unit quantity here and
-- apply the inventory-accounting semantics explicitly.
-- ============================================================

daily_movements AS (

    SELECT

        im.event_ts::date AS movement_date,

        im.warehouse_id,

        im.product_id,


        COUNT(*) AS movement_event_count,


        -- ----------------------------------------------------
        -- Receipt
        -- ----------------------------------------------------

        COUNT(*) FILTER (
            WHERE im.movement_type = 'receipt'
        ) AS receipt_event_count,

        COALESCE(
            SUM(
                ABS(im.quantity_change)
            ) FILTER (
                WHERE im.movement_type = 'receipt'
            ),
            0
        ) AS receipt_units,


        -- ----------------------------------------------------
        -- Reservation
        -- ----------------------------------------------------

        COUNT(*) FILTER (
            WHERE im.movement_type = 'reservation'
        ) AS reservation_event_count,

        COALESCE(
            SUM(
                ABS(im.quantity_change)
            ) FILTER (
                WHERE im.movement_type = 'reservation'
            ),
            0
        ) AS reservation_units,


        -- ----------------------------------------------------
        -- Release
        -- ----------------------------------------------------

        COUNT(*) FILTER (
            WHERE im.movement_type = 'release'
        ) AS release_event_count,

        COALESCE(
            SUM(
                ABS(im.quantity_change)
            ) FILTER (
                WHERE im.movement_type = 'release'
            ),
            0
        ) AS release_units,


        -- ----------------------------------------------------
        -- Shipment
        -- ----------------------------------------------------

        COUNT(*) FILTER (
            WHERE im.movement_type = 'shipment'
        ) AS shipment_event_count,

        COALESCE(
            SUM(
                ABS(im.quantity_change)
            ) FILTER (
                WHERE im.movement_type = 'shipment'
            ),
            0
        ) AS shipment_units


    FROM inventory_movements AS im

    CROSS JOIN model_bounds AS mb

    WHERE

        im.event_ts::date
            BETWEEN mb.first_date
            AND mb.last_date

    GROUP BY

        im.event_ts::date,

        im.warehouse_id,

        im.product_id
),


-- ============================================================
-- Join daily demand to movement activity
-- ============================================================

daily_ledger AS (

    SELECT

        d.*,


        -- ----------------------------------------------------
        -- Movement event counts
        -- ----------------------------------------------------

        COALESCE(
            dm.movement_event_count,
            0
        ) AS movement_event_count,

        COALESCE(
            dm.receipt_event_count,
            0
        ) AS receipt_event_count,

        COALESCE(
            dm.reservation_event_count,
            0
        ) AS reservation_event_count,

        COALESCE(
            dm.release_event_count,
            0
        ) AS release_event_count,

        COALESCE(
            dm.shipment_event_count,
            0
        ) AS shipment_event_count,


        -- ----------------------------------------------------
        -- Movement units
        -- ----------------------------------------------------

        COALESCE(
            dm.receipt_units,
            0
        ) AS receipt_units,

        COALESCE(
            dm.reservation_units,
            0
        ) AS reservation_units,

        COALESCE(
            dm.release_units,
            0
        ) AS release_units,

        COALESCE(
            dm.shipment_units,
            0
        ) AS shipment_units,


        -- ----------------------------------------------------
        -- Daily inventory-accounting changes
        -- ----------------------------------------------------

        (
            COALESCE(
                dm.receipt_units,
                0
            )
            -
            COALESCE(
                dm.shipment_units,
                0
            )
        ) AS net_on_hand_change,


        (
            COALESCE(
                dm.reservation_units,
                0
            )
            -
            COALESCE(
                dm.release_units,
                0
            )
            -
            COALESCE(
                dm.shipment_units,
                0
            )
        ) AS net_reserved_change,


        (
            COALESCE(
                dm.receipt_units,
                0
            )
            -
            COALESCE(
                dm.reservation_units,
                0
            )
            +
            COALESCE(
                dm.release_units,
                0
            )
        ) AS net_available_change


    FROM vw_daily_product_demand AS d

    LEFT JOIN daily_movements AS dm

        ON dm.movement_date =
            d.demand_date

        AND dm.warehouse_id =
            d.warehouse_id

        AND dm.product_id =
            d.product_id
),


-- ============================================================
-- Reconstruct inventory state
--
-- Opening receipt events establish the ledger balance.
-- Subsequent receipts and shipments update physical inventory.
--
-- Reservations/releases/shipments update the reserved balance.
-- ============================================================

inventory_state AS (

    SELECT

        dl.*,


        -- ----------------------------------------------------
        -- Historical physical inventory
        -- ----------------------------------------------------

        SUM(
            dl.net_on_hand_change
        ) OVER (

            PARTITION BY
                dl.warehouse_id,
                dl.product_id

            ORDER BY
                dl.demand_date

            ROWS BETWEEN
                UNBOUNDED PRECEDING
                AND CURRENT ROW

        ) AS ending_on_hand_qty,


        -- ----------------------------------------------------
        -- Historical reserved inventory
        -- ----------------------------------------------------

        SUM(
            dl.net_reserved_change
        ) OVER (

            PARTITION BY
                dl.warehouse_id,
                dl.product_id

            ORDER BY
                dl.demand_date

            ROWS BETWEEN
                UNBOUNDED PRECEDING
                AND CURRENT ROW

        ) AS ending_reserved_qty


    FROM daily_ledger AS dl
),


-- ============================================================
-- Available inventory
-- ============================================================

availability_state AS (

    SELECT

        s.*,

        (
            s.ending_on_hand_qty
            -
            s.ending_reserved_qty
        ) AS ending_available_qty


    FROM inventory_state AS s
),


-- ============================================================
-- Prior-day state
--
-- Useful for forecasting today's demand without looking at
-- information generated later during the current day.
-- ============================================================

lagged_state AS (

    SELECT

        a.*,


        LAG(
            a.ending_on_hand_qty,
            1
        ) OVER (

            PARTITION BY
                a.warehouse_id,
                a.product_id

            ORDER BY
                a.demand_date

        ) AS prior_day_on_hand_qty,


        LAG(
            a.ending_reserved_qty,
            1
        ) OVER (

            PARTITION BY
                a.warehouse_id,
                a.product_id

            ORDER BY
                a.demand_date

        ) AS prior_day_reserved_qty,


        LAG(
            a.ending_available_qty,
            1
        ) OVER (

            PARTITION BY
                a.warehouse_id,
                a.product_id

            ORDER BY
                a.demand_date

        ) AS prior_day_available_qty


    FROM availability_state AS a
)


-- ============================================================
-- Final operational feature layer
-- ============================================================

SELECT

    l.*,


    -- ========================================================
    -- STOCK FLAGS
    -- ========================================================

    CASE

        WHEN l.ending_available_qty <= 0
        THEN 1

        ELSE 0

    END AS is_stockout,


    CASE

        WHEN
            l.ending_available_qty > 0
            AND l.ending_available_qty
                <= l.snapshot_reorder_point

        THEN 1

        ELSE 0

    END AS is_below_reorder_point,


    CASE

        WHEN
            l.ending_available_qty
            <= l.snapshot_reorder_point

        THEN 1

        ELSE 0

    END AS requires_reorder,


    CASE

        WHEN l.receipt_units > 0
        THEN 1

        ELSE 0

    END AS is_receipt_day,


    CASE

        WHEN l.reservation_units > 0
        THEN 1

        ELSE 0

    END AS has_reservation_activity,


    CASE

        WHEN l.shipment_units > 0
        THEN 1

        ELSE 0

    END AS has_shipment_activity,


    -- ========================================================
    -- REORDER GAP
    -- ========================================================

    GREATEST(
        l.snapshot_reorder_point
            - l.ending_available_qty,
        0
    ) AS reorder_gap_units,


    -- ========================================================
    -- RESERVED INVENTORY PRESSURE
    -- ========================================================

    CASE

        WHEN l.ending_on_hand_qty > 0

        THEN ROUND(
            (
                l.ending_reserved_qty
                * 100.0
                /
                l.ending_on_hand_qty
            )::numeric,
            2
        )

        ELSE NULL

    END AS reserved_inventory_pct,


    -- ========================================================
    -- DAYS OF SUPPLY
    --
    -- Uses historical demand velocity only.
    -- ========================================================

    CASE

        WHEN l.ending_available_qty <= 0
        THEN 0::numeric

        WHEN
            l.rolling_7d_avg_units IS NOT NULL
            AND l.rolling_7d_avg_units > 0

        THEN ROUND(
            (
                l.ending_available_qty
                /
                l.rolling_7d_avg_units
            )::numeric,
            2
        )

        ELSE NULL

    END AS days_of_supply_7d,


    CASE

        WHEN l.ending_available_qty <= 0
        THEN 0::numeric

        WHEN
            l.rolling_28d_avg_units IS NOT NULL
            AND l.rolling_28d_avg_units > 0

        THEN ROUND(
            (
                l.ending_available_qty
                /
                l.rolling_28d_avg_units
            )::numeric,
            2
        )

        ELSE NULL

    END AS days_of_supply_28d,


    -- ========================================================
    -- INVENTORY / DEMAND PRESSURE
    -- ========================================================

    CASE

        WHEN
            l.ending_available_qty > 0
            AND l.rolling_28d_units IS NOT NULL

        THEN ROUND(
            (
                l.rolling_28d_units
                /
                l.ending_available_qty::numeric
            ),
            4
        )

        ELSE NULL

    END AS demand_inventory_pressure_28d,


    -- ========================================================
    -- OPERATIONAL STOCK STATUS
    -- ========================================================

    CASE

        WHEN l.ending_available_qty <= 0

            THEN 'STOCKOUT'

        WHEN
            l.ending_available_qty
            <= l.snapshot_reorder_point

            THEN 'CRITICAL'

        WHEN
            l.ending_available_qty
            <= (
                l.snapshot_reorder_point
                * 1.5
            )

            THEN 'LOW'

        ELSE 'HEALTHY'

    END AS stock_status


FROM lagged_state AS l
;



-- ============================================================
-- VALIDATION 1
-- Model grain
-- ============================================================


SELECT

    COUNT(*) AS model_rows,

    COUNT(
        DISTINCT demand_date
    ) AS calendar_days,

    COUNT(
        DISTINCT (
            warehouse_id,
            product_id
        )
    ) AS warehouse_product_positions,

    COUNT(*) -
    COUNT(
        DISTINCT (
            demand_date,
            warehouse_id,
            product_id
        )
    ) AS duplicate_grain_rows

FROM vw_warehouse_product_daily
;



-- ============================================================
-- VALIDATION 2
-- Reconcile daily model movement ledger against source ledger
--
-- Only movements inside the demand-model date window are
-- compared here.
-- ============================================================


WITH bounds AS (

    SELECT

        MIN(demand_date) AS first_date,

        MAX(demand_date) AS last_date

    FROM vw_warehouse_product_daily
),


source AS (

    SELECT

        COALESCE(
            SUM(
                ABS(quantity_change)
            ) FILTER (
                WHERE movement_type = 'receipt'
            ),
            0
        ) AS receipt_units,

        COALESCE(
            SUM(
                ABS(quantity_change)
            ) FILTER (
                WHERE movement_type = 'reservation'
            ),
            0
        ) AS reservation_units,

        COALESCE(
            SUM(
                ABS(quantity_change)
            ) FILTER (
                WHERE movement_type = 'release'
            ),
            0
        ) AS release_units,

        COALESCE(
            SUM(
                ABS(quantity_change)
            ) FILTER (
                WHERE movement_type = 'shipment'
            ),
            0
        ) AS shipment_units,

        COUNT(*) AS movement_events

    FROM inventory_movements AS im

    CROSS JOIN bounds AS b

    WHERE

        im.event_ts::date
            BETWEEN b.first_date
            AND b.last_date
),


model AS (

    SELECT

        SUM(receipt_units)
            AS receipt_units,

        SUM(reservation_units)
            AS reservation_units,

        SUM(release_units)
            AS release_units,

        SUM(shipment_units)
            AS shipment_units,

        SUM(movement_event_count)
            AS movement_events

    FROM vw_warehouse_product_daily
)


SELECT

    m.receipt_units
        AS model_receipt_units,

    s.receipt_units
        AS source_receipt_units,

    m.receipt_units
        - s.receipt_units
        AS receipt_difference,


    m.reservation_units
        AS model_reservation_units,

    s.reservation_units
        AS source_reservation_units,

    m.reservation_units
        - s.reservation_units
        AS reservation_difference,


    m.release_units
        AS model_release_units,

    s.release_units
        AS source_release_units,

    m.release_units
        - s.release_units
        AS release_difference,


    m.shipment_units
        AS model_shipment_units,

    s.shipment_units
        AS source_shipment_units,

    m.shipment_units
        - s.shipment_units
        AS shipment_difference,


    m.movement_events
        AS model_movement_events,

    s.movement_events
        AS source_movement_events,

    m.movement_events
        - s.movement_events
        AS event_difference


FROM model AS m

CROSS JOIN source AS s
;



-- ============================================================
-- VALIDATION 3
-- Known movement types
-- ============================================================


WITH bounds AS (

    SELECT

        MIN(demand_date) AS first_date,

        MAX(demand_date) AS last_date

    FROM vw_warehouse_product_daily
)


SELECT

    COUNT(*) AS unknown_movement_events

FROM inventory_movements AS im

CROSS JOIN bounds AS b

WHERE

    im.event_ts::date
        BETWEEN b.first_date
        AND b.last_date

    AND im.movement_type NOT IN (

        'receipt',
        'reservation',
        'release',
        'shipment'
    )
;



-- ============================================================
-- VALIDATION 4
-- Inventory-state integrity
-- ============================================================


SELECT

    COUNT(*) FILTER (
        WHERE ending_on_hand_qty < 0
    ) AS negative_on_hand_rows,

    COUNT(*) FILTER (
        WHERE ending_reserved_qty < 0
    ) AS negative_reserved_rows,

    COUNT(*) FILTER (
        WHERE ending_available_qty < 0
    ) AS negative_available_rows,

    COUNT(*) FILTER (
        WHERE
            ending_reserved_qty
            > ending_on_hand_qty
    ) AS reserved_exceeds_on_hand_rows,

    COUNT(*) FILTER (
        WHERE
            is_stockout = 1
            AND ending_available_qty > 0
    ) AS invalid_stockout_flags,

    COUNT(*) FILTER (
        WHERE
            requires_reorder = 0
            AND ending_available_qty
                <= snapshot_reorder_point
    ) AS invalid_reorder_flags

FROM vw_warehouse_product_daily
;



-- ============================================================
-- VALIDATION 5
-- Demand layer must remain unchanged
-- ============================================================


SELECT

    SUM(units_sold)
        AS operational_model_units,

    (
        SELECT
            SUM(units_sold)

        FROM vw_daily_product_demand
    ) AS demand_model_units,

    SUM(units_sold)
    -
    (
        SELECT
            SUM(units_sold)

        FROM vw_daily_product_demand
    ) AS units_difference,


    ROUND(
        SUM(revenue)::numeric,
        2
    ) AS operational_model_revenue,

    (
        SELECT

            ROUND(
                SUM(revenue)::numeric,
                2
            )

        FROM vw_daily_product_demand
    ) AS demand_model_revenue,

    ROUND(
        (
            SUM(revenue)
            -
            (
                SELECT
                    SUM(revenue)

                FROM vw_daily_product_demand
            )
        )::numeric,
        2
    ) AS revenue_difference

FROM vw_warehouse_product_daily
;



-- ============================================================
-- VALIDATION 6
-- Final-day network inventory position
--
-- This is an operational summary, not a requirement that the
-- ending ledger match the static inventory snapshot.
-- ============================================================


WITH final_day AS (

    SELECT

        *

    FROM vw_warehouse_product_daily

    WHERE demand_date = (

        SELECT
            MAX(demand_date)

        FROM vw_warehouse_product_daily
    )
)


SELECT

    demand_date,

    COUNT(*) AS inventory_positions,

    SUM(
        ending_on_hand_qty
    ) AS network_on_hand_units,

    SUM(
        ending_reserved_qty
    ) AS network_reserved_units,

    SUM(
        ending_available_qty
    ) AS network_available_units,

    COUNT(*) FILTER (
        WHERE is_stockout = 1
    ) AS stockout_positions,

    COUNT(*) FILTER (
        WHERE is_below_reorder_point = 1
    ) AS below_reorder_positions,

    COUNT(*) FILTER (
        WHERE requires_reorder = 1
    ) AS reorder_positions

FROM final_day

GROUP BY
    demand_date
;



-- ============================================================
-- VALIDATION 7
-- Stock-status distribution on final day
-- ============================================================


SELECT

    stock_status,

    COUNT(*) AS positions,

    ROUND(
        COUNT(*) * 100.0
        /
        SUM(COUNT(*))
        OVER (),
        2
    ) AS position_pct

FROM vw_warehouse_product_daily

WHERE demand_date = (

    SELECT
        MAX(demand_date)

    FROM vw_warehouse_product_daily
)

GROUP BY
    stock_status

ORDER BY

    CASE stock_status

        WHEN 'STOCKOUT'
            THEN 1

        WHEN 'CRITICAL'
            THEN 2

        WHEN 'LOW'
            THEN 3

        WHEN 'HEALTHY'
            THEN 4

        ELSE 5

    END
;



-- ============================================================
-- VALIDATION 8
-- Preview inventory + demand + forecasting features
-- ============================================================


SELECT

    demand_date,

    warehouse_code,

    sku,

    category_name,

    units_sold,

    rolling_7d_avg_units,

    rolling_28d_avg_units,

    receipt_units,

    reservation_units,

    release_units,

    shipment_units,

    ending_on_hand_qty,

    ending_reserved_qty,

    ending_available_qty,

    prior_day_available_qty,

    snapshot_reorder_point,

    reorder_gap_units,

    days_of_supply_7d,

    days_of_supply_28d,

    reserved_inventory_pct,

    stock_status

FROM vw_warehouse_product_daily

WHERE demand_date >= (

    SELECT
        MAX(demand_date) - 7

    FROM vw_warehouse_product_daily
)

ORDER BY

    warehouse_id,
    product_id,
    demand_date

LIMIT 30
;