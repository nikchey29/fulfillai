-- ============================================================
-- FulfillAI
-- Model 002: Daily Product Demand
-- ============================================================
--
-- Grain:
--   One row per:
--
--       demand_date
--       warehouse_id
--       product_id
--
-- Purpose:
--   Build a dense daily demand time series suitable for:
--
--       demand forecasting
--       inventory planning
--       replenishment modeling
--       warehouse-product analysis
--       seasonality analysis
--       ML feature engineering
--
-- Important:
--   Zero-demand days are deliberately preserved.
--
--   A forecasting model must see days where nothing sold;
--   otherwise demand becomes artificially inflated.
--
-- ============================================================


CREATE OR REPLACE VIEW vw_daily_product_demand AS


WITH date_bounds AS (

    SELECT

        MIN(
            order_ts::date
        ) AS min_date,

        MAX(
            order_ts::date
        ) AS max_date

    FROM orders
),


-- ============================================================
-- Complete daily calendar
-- ============================================================

date_spine AS (

    SELECT

        generate_series(
            min_date,
            max_date,
            INTERVAL '1 day'
        )::date AS demand_date

    FROM date_bounds
),


-- ============================================================
-- Valid warehouse/product combinations
--
-- Inventory already represents the warehouse/product positions
-- that exist in the FulfillAI fulfillment network.
-- ============================================================

warehouse_product_spine AS (

    SELECT

        i.warehouse_id,

        w.warehouse_code,

        w.warehouse_name,

        w.city AS warehouse_city,

        w.country_code AS warehouse_country_code,

        i.product_id,

        p.sku,

        p.product_name,

        p.category_id,

        pc.category_name,

        p.unit_price AS catalog_unit_price,

        p.unit_cost AS catalog_unit_cost,

        p.weight_kg,

        i.on_hand_qty,

        i.reserved_qty,

        i.reorder_point

    FROM inventory AS i

    JOIN warehouses AS w
        ON w.warehouse_id = i.warehouse_id

    JOIN products AS p
        ON p.product_id = i.product_id

    JOIN product_categories AS pc
        ON pc.category_id = p.category_id
),


-- ============================================================
-- Raw daily demand from order-item transactions
-- ============================================================

daily_transactions AS (

    SELECT

        o.order_ts::date AS demand_date,

        o.warehouse_id,

        oi.product_id,


        -- ----------------------------------------------------
        -- Gross customer demand
        --
        -- Includes orders that are ultimately cancelled.
        -- ----------------------------------------------------

        COUNT(
            DISTINCT o.order_id
        ) AS gross_order_count,

        SUM(
            oi.quantity
        ) AS gross_units_requested,

        ROUND(
            SUM(
                oi.quantity
                * oi.unit_price
            )::numeric,
            2
        ) AS gross_requested_value,


        -- ----------------------------------------------------
        -- Realized demand
        --
        -- Excludes cancelled orders.
        -- ----------------------------------------------------

        COUNT(
            DISTINCT o.order_id
        ) FILTER (
            WHERE o.order_status <> 'cancelled'
        ) AS order_count,

        COALESCE(
            SUM(
                oi.quantity
            ) FILTER (
                WHERE o.order_status <> 'cancelled'
            ),
            0
        ) AS units_sold,

        ROUND(
            COALESCE(
                SUM(
                    oi.quantity
                    * oi.unit_price
                ) FILTER (
                    WHERE o.order_status <> 'cancelled'
                ),
                0
            )::numeric,
            2
        ) AS revenue,


        -- ----------------------------------------------------
        -- Cancellation demand
        -- ----------------------------------------------------

        COUNT(
            DISTINCT o.order_id
        ) FILTER (
            WHERE o.order_status = 'cancelled'
        ) AS cancelled_order_count,

        COALESCE(
            SUM(
                oi.quantity
            ) FILTER (
                WHERE o.order_status = 'cancelled'
            ),
            0
        ) AS cancelled_units,


        -- ----------------------------------------------------
        -- Observed transaction price
        -- ----------------------------------------------------

        ROUND(
            AVG(
                oi.unit_price
            ) FILTER (
                WHERE o.order_status <> 'cancelled'
            )::numeric,
            2
        ) AS avg_selling_price


    FROM orders AS o

    JOIN order_items AS oi
        ON oi.order_id = o.order_id

    GROUP BY

        o.order_ts::date,

        o.warehouse_id,

        oi.product_id
),


-- ============================================================
-- Dense calendar
--
-- Every valid warehouse/product position receives one row
-- for every date in the simulation period.
-- ============================================================

daily_base AS (

    SELECT

        d.demand_date,


        -- ----------------------------------------------------
        -- Date dimensions
        -- ----------------------------------------------------

        DATE_TRUNC(
            'week',
            d.demand_date
        )::date AS demand_week,

        DATE_TRUNC(
            'month',
            d.demand_date
        )::date AS demand_month,

        EXTRACT(
            YEAR FROM d.demand_date
        )::integer AS demand_year,

        EXTRACT(
            MONTH FROM d.demand_date
        )::integer AS demand_month_number,

        EXTRACT(
            ISODOW FROM d.demand_date
        )::integer AS day_of_week,

        EXTRACT(
            DOY FROM d.demand_date
        )::integer AS day_of_year,

        CASE

            WHEN EXTRACT(
                ISODOW FROM d.demand_date
            ) IN (6, 7)

            THEN 1

            ELSE 0

        END AS is_weekend,


        -- ----------------------------------------------------
        -- Warehouse
        -- ----------------------------------------------------

        wp.warehouse_id,

        wp.warehouse_code,

        wp.warehouse_name,

        wp.warehouse_city,

        wp.warehouse_country_code,


        -- ----------------------------------------------------
        -- Product
        -- ----------------------------------------------------

        wp.product_id,

        wp.sku,

        wp.product_name,

        wp.category_id,

        wp.category_name,

        wp.catalog_unit_price,

        wp.catalog_unit_cost,

        wp.weight_kg,


        -- ----------------------------------------------------
        -- Inventory snapshot context
        --
        -- These are current snapshot attributes, not historical
        -- inventory balances.
        -- ----------------------------------------------------

        wp.on_hand_qty AS snapshot_on_hand_qty,

        wp.reserved_qty AS snapshot_reserved_qty,

        wp.reorder_point AS snapshot_reorder_point,


        -- ----------------------------------------------------
        -- Daily gross demand
        -- ----------------------------------------------------

        COALESCE(
            dt.gross_order_count,
            0
        ) AS gross_order_count,

        COALESCE(
            dt.gross_units_requested,
            0
        ) AS gross_units_requested,

        COALESCE(
            dt.gross_requested_value,
            0
        ) AS gross_requested_value,


        -- ----------------------------------------------------
        -- Daily realized demand
        -- ----------------------------------------------------

        COALESCE(
            dt.order_count,
            0
        ) AS order_count,

        COALESCE(
            dt.units_sold,
            0
        ) AS units_sold,

        COALESCE(
            dt.revenue,
            0
        ) AS revenue,


        -- ----------------------------------------------------
        -- Cancellation metrics
        -- ----------------------------------------------------

        COALESCE(
            dt.cancelled_order_count,
            0
        ) AS cancelled_order_count,

        COALESCE(
            dt.cancelled_units,
            0
        ) AS cancelled_units,


        -- ----------------------------------------------------
        -- Price features
        -- ----------------------------------------------------

        dt.avg_selling_price,

        wp.catalog_unit_price
            - wp.catalog_unit_cost
            AS catalog_unit_margin,


        CASE

            WHEN wp.catalog_unit_price > 0

            THEN ROUND(
                (
                    (
                        wp.catalog_unit_price
                        - wp.catalog_unit_cost
                    )
                    / wp.catalog_unit_price
                    * 100
                )::numeric,
                2
            )

            ELSE NULL

        END AS catalog_margin_pct


    FROM date_spine AS d

    CROSS JOIN warehouse_product_spine AS wp

    LEFT JOIN daily_transactions AS dt

        ON dt.demand_date = d.demand_date

        AND dt.warehouse_id =
            wp.warehouse_id

        AND dt.product_id =
            wp.product_id
),


-- ============================================================
-- Forecasting features
--
-- IMPORTANT:
--
-- Rolling features use only PREVIOUS days.
--
-- The current day's units_sold is NOT included, preventing
-- target leakage when this model is later used for ML.
-- ============================================================

feature_layer AS (

    SELECT

        db.*,


        -- ----------------------------------------------------
        -- Lag features
        -- ----------------------------------------------------

        LAG(
            db.units_sold,
            1
        ) OVER (

            PARTITION BY
                db.warehouse_id,
                db.product_id

            ORDER BY
                db.demand_date

        ) AS lag_1_units,


        LAG(
            db.units_sold,
            7
        ) OVER (

            PARTITION BY
                db.warehouse_id,
                db.product_id

            ORDER BY
                db.demand_date

        ) AS lag_7_units,


        LAG(
            db.units_sold,
            14
        ) OVER (

            PARTITION BY
                db.warehouse_id,
                db.product_id

            ORDER BY
                db.demand_date

        ) AS lag_14_units,


        LAG(
            db.units_sold,
            28
        ) OVER (

            PARTITION BY
                db.warehouse_id,
                db.product_id

            ORDER BY
                db.demand_date

        ) AS lag_28_units,


        -- ----------------------------------------------------
        -- Previous 7 days
        -- ----------------------------------------------------

        SUM(
            db.units_sold
        ) OVER (

            PARTITION BY
                db.warehouse_id,
                db.product_id

            ORDER BY
                db.demand_date

            ROWS BETWEEN
                7 PRECEDING
                AND
                1 PRECEDING

        ) AS rolling_7d_units,


        ROUND(
            AVG(
                db.units_sold
            ) OVER (

                PARTITION BY
                    db.warehouse_id,
                    db.product_id

                ORDER BY
                    db.demand_date

                ROWS BETWEEN
                    7 PRECEDING
                    AND
                    1 PRECEDING
            )::numeric,
            2
        ) AS rolling_7d_avg_units,


        -- ----------------------------------------------------
        -- Previous 28 days
        -- ----------------------------------------------------

        SUM(
            db.units_sold
        ) OVER (

            PARTITION BY
                db.warehouse_id,
                db.product_id

            ORDER BY
                db.demand_date

            ROWS BETWEEN
                28 PRECEDING
                AND
                1 PRECEDING

        ) AS rolling_28d_units,


        ROUND(
            AVG(
                db.units_sold
            ) OVER (

                PARTITION BY
                    db.warehouse_id,
                    db.product_id

                ORDER BY
                    db.demand_date

                ROWS BETWEEN
                    28 PRECEDING
                    AND
                    1 PRECEDING
            )::numeric,
            2
        ) AS rolling_28d_avg_units,


        -- ----------------------------------------------------
        -- Previous 7-day order activity
        -- ----------------------------------------------------

        SUM(
            db.order_count
        ) OVER (

            PARTITION BY
                db.warehouse_id,
                db.product_id

            ORDER BY
                db.demand_date

            ROWS BETWEEN
                7 PRECEDING
                AND
                1 PRECEDING

        ) AS rolling_7d_orders,


        -- ----------------------------------------------------
        -- Previous 7-day revenue
        -- ----------------------------------------------------

        ROUND(
            SUM(
                db.revenue
            ) OVER (

                PARTITION BY
                    db.warehouse_id,
                    db.product_id

                ORDER BY
                    db.demand_date

                ROWS BETWEEN
                    7 PRECEDING
                    AND
                    1 PRECEDING
            )::numeric,
            2
        ) AS rolling_7d_revenue


    FROM daily_base AS db
)


SELECT

    *

FROM feature_layer
;



-- ============================================================
-- VALIDATION 1
-- Dense time-series grain
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

FROM vw_daily_product_demand
;



-- ============================================================
-- VALIDATION 2
-- Date boundaries
-- ============================================================


SELECT

    MIN(
        demand_date
    ) AS first_date,

    MAX(
        demand_date
    ) AS last_date,

    COUNT(
        DISTINCT demand_date
    ) AS calendar_days

FROM vw_daily_product_demand
;



-- ============================================================
-- VALIDATION 3
-- Gross demand reconciliation
--
-- These totals include cancelled orders and therefore must
-- exactly match the raw order_items table.
-- ============================================================


SELECT

    SUM(
        gross_units_requested
    ) AS model_gross_units,

    (
        SELECT
            SUM(quantity)

        FROM order_items
    ) AS source_gross_units,

    SUM(
        gross_units_requested
    )
    -
    (
        SELECT
            SUM(quantity)

        FROM order_items
    ) AS gross_unit_difference

FROM vw_daily_product_demand
;



-- ============================================================
-- VALIDATION 4
-- Realized demand reconciliation
--
-- Excludes cancelled orders.
-- ============================================================


SELECT

    SUM(
        units_sold
    ) AS model_units_sold,

    (
        SELECT

            SUM(
                oi.quantity
            )

        FROM order_items AS oi

        JOIN orders AS o
            ON o.order_id = oi.order_id

        WHERE
            o.order_status <> 'cancelled'

    ) AS source_units_sold,

    SUM(
        units_sold
    )
    -
    (
        SELECT

            SUM(
                oi.quantity
            )

        FROM order_items AS oi

        JOIN orders AS o
            ON o.order_id = oi.order_id

        WHERE
            o.order_status <> 'cancelled'

    ) AS units_difference

FROM vw_daily_product_demand
;



-- ============================================================
-- VALIDATION 5
-- Revenue reconciliation
-- ============================================================


SELECT

    ROUND(
        SUM(
            revenue
        )::numeric,
        2
    ) AS model_revenue,

    (

        SELECT

            ROUND(
                SUM(
                    oi.quantity
                    * oi.unit_price
                )::numeric,
                2
            )

        FROM order_items AS oi

        JOIN orders AS o
            ON o.order_id = oi.order_id

        WHERE
            o.order_status <> 'cancelled'

    ) AS source_revenue,

    ROUND(
        (
            SUM(
                revenue
            )
            -
            (

                SELECT

                    SUM(
                        oi.quantity
                        * oi.unit_price
                    )

                FROM order_items AS oi

                JOIN orders AS o
                    ON o.order_id =
                        oi.order_id

                WHERE
                    o.order_status
                    <> 'cancelled'
            )
        )::numeric,
        2
    ) AS revenue_difference

FROM vw_daily_product_demand
;



-- ============================================================
-- VALIDATION 6
-- Zero-demand preservation
--
-- We WANT many zero-demand rows.
-- ============================================================


SELECT

    COUNT(*) AS model_rows,

    COUNT(*) FILTER (
        WHERE units_sold = 0
    ) AS zero_demand_rows,

    COUNT(*) FILTER (
        WHERE units_sold > 0
    ) AS positive_demand_rows,

    ROUND(
        (
            COUNT(*) FILTER (
                WHERE units_sold = 0
            )
            * 100.0
            / COUNT(*)
        ),
        2
    ) AS zero_demand_pct

FROM vw_daily_product_demand
;



-- ============================================================
-- VALIDATION 7
-- Feature integrity
-- ============================================================


SELECT

    COUNT(*) FILTER (
        WHERE units_sold < 0
    ) AS negative_units,

    COUNT(*) FILTER (
        WHERE order_count < 0
    ) AS negative_orders,

    COUNT(*) FILTER (
        WHERE revenue < 0
    ) AS negative_revenue,

    COUNT(*) FILTER (
        WHERE cancelled_units < 0
    ) AS negative_cancelled_units,

    COUNT(*) FILTER (
        WHERE
            gross_units_requested
            <
            units_sold
    ) AS realized_exceeds_gross,

    COUNT(*) FILTER (
        WHERE
            gross_units_requested
            <>
            units_sold
            +
            cancelled_units
    ) AS gross_demand_reconciliation_failures

FROM vw_daily_product_demand
;



-- ============================================================
-- VALIDATION 8
-- Demand summary
-- ============================================================


SELECT

    COUNT(*) AS rows,

    SUM(
        order_count
    ) AS daily_order_product_occurrences,

    SUM(
        units_sold
    ) AS total_units_sold,

    ROUND(
        SUM(
            revenue
        )::numeric,
        2
    ) AS total_revenue,

    ROUND(
        AVG(
            units_sold
        )::numeric,
        4
    ) AS avg_units_per_position_day,

    MAX(
        units_sold
    ) AS max_units_single_position_day

FROM vw_daily_product_demand
;



-- ============================================================
-- VALIDATION 9
-- Preview forecasting features
--
-- Restrict to rows with enough history so lag fields are easy
-- to inspect.
-- ============================================================


SELECT

    demand_date,

    warehouse_code,

    sku,

    category_name,

    units_sold,

    order_count,

    revenue,

    is_weekend,

    lag_1_units,

    lag_7_units,

    lag_14_units,

    lag_28_units,

    rolling_7d_units,

    rolling_7d_avg_units,

    rolling_28d_units,

    rolling_28d_avg_units

FROM vw_daily_product_demand

WHERE

    demand_date >= (
        SELECT
            MIN(order_ts::date)
            + 28
        FROM orders
    )

ORDER BY

    warehouse_id,
    product_id,
    demand_date

LIMIT 20
;