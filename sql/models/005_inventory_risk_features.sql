-- ============================================================
-- FulfillAI
-- Model 005: Inventory Risk Features
-- ============================================================
--
-- Grain:
--
--     one row per
--         demand_date
--         warehouse_id
--         product_id
--
-- Purpose:
--
--     Build a leakage-safe ML feature dataset for:
--
--         stockout prediction
--         reorder-risk prediction
--         replenishment planning
--         inventory monitoring
--
-- Feature cutoff:
--
--     When predicting risk beginning on demand_date,
--     inventory features come from the END OF THE PRIOR DAY.
--
--     Demand-history features use only PREVIOUS dates.
--
-- Target:
--
--     Did available inventory reach <= 0 during the
--     current date + following 6 dates?
--
--     That gives a seven-day prediction horizon.
--
-- IMPORTANT:
--
--     Future inventory values are used ONLY to create labels.
--     They must never become model input features.
--
-- ============================================================


CREATE OR REPLACE VIEW vw_inventory_risk_features AS


WITH history AS (

    SELECT

        d.demand_date,

        d.warehouse_id,

        d.warehouse_code,

        d.product_id,

        d.sku,

        d.category_name,

        d.snapshot_reorder_point,


        -- ====================================================
        -- Today's observed demand
        --
        -- This is retained for reconciliation and inspection.
        -- It must NOT be used as an input when predicting
        -- today's inventory risk.
        -- ====================================================

        d.units_sold,

        d.revenue,


        -- ====================================================
        -- Current end-of-day inventory
        --
        -- Also retained for reconciliation/target construction.
        -- Do NOT use as prediction-time features for this day.
        -- ====================================================

        d.ending_on_hand_qty,

        d.ending_reserved_qty,

        d.ending_available_qty,


        -- ====================================================
        -- PRIOR-DAY INVENTORY FEATURES
        -- ====================================================

        LAG(
            d.ending_on_hand_qty,
            1
        ) OVER (

            PARTITION BY
                d.warehouse_id,
                d.product_id

            ORDER BY
                d.demand_date

        ) AS prior_day_on_hand_qty,


        LAG(
            d.ending_reserved_qty,
            1
        ) OVER (

            PARTITION BY
                d.warehouse_id,
                d.product_id

            ORDER BY
                d.demand_date

        ) AS prior_day_reserved_qty,


        LAG(
            d.ending_available_qty,
            1
        ) OVER (

            PARTITION BY
                d.warehouse_id,
                d.product_id

            ORDER BY
                d.demand_date

        ) AS prior_day_available_qty,


        -- ====================================================
        -- DEMAND LAGS
        -- ====================================================

        LAG(
            d.units_sold,
            1
        ) OVER (

            PARTITION BY
                d.warehouse_id,
                d.product_id

            ORDER BY
                d.demand_date

        ) AS lag_1_units,


        LAG(
            d.units_sold,
            7
        ) OVER (

            PARTITION BY
                d.warehouse_id,
                d.product_id

            ORDER BY
                d.demand_date

        ) AS lag_7_units,


        LAG(
            d.units_sold,
            14
        ) OVER (

            PARTITION BY
                d.warehouse_id,
                d.product_id

            ORDER BY
                d.demand_date

        ) AS lag_14_units,


        LAG(
            d.units_sold,
            28
        ) OVER (

            PARTITION BY
                d.warehouse_id,
                d.product_id

            ORDER BY
                d.demand_date

        ) AS lag_28_units,


        -- ====================================================
        -- HISTORICAL 7-DAY DEMAND
        --
        -- Current row deliberately excluded.
        -- ====================================================

        COUNT(
            d.units_sold
        ) OVER (

            PARTITION BY
                d.warehouse_id,
                d.product_id

            ORDER BY
                d.demand_date

            ROWS BETWEEN
                7 PRECEDING
                AND 1 PRECEDING

        ) AS historical_observation_days_7d,


        SUM(
            d.units_sold
        ) OVER (

            PARTITION BY
                d.warehouse_id,
                d.product_id

            ORDER BY
                d.demand_date

            ROWS BETWEEN
                7 PRECEDING
                AND 1 PRECEDING

        ) AS historical_7d_units,


        AVG(
            d.units_sold::numeric
        ) OVER (

            PARTITION BY
                d.warehouse_id,
                d.product_id

            ORDER BY
                d.demand_date

            ROWS BETWEEN
                7 PRECEDING
                AND 1 PRECEDING

        ) AS historical_7d_avg_units,


        -- ====================================================
        -- HISTORICAL 28-DAY DEMAND
        -- ====================================================

        COUNT(
            d.units_sold
        ) OVER (

            PARTITION BY
                d.warehouse_id,
                d.product_id

            ORDER BY
                d.demand_date

            ROWS BETWEEN
                28 PRECEDING
                AND 1 PRECEDING

        ) AS historical_observation_days_28d,


        SUM(
            d.units_sold
        ) OVER (

            PARTITION BY
                d.warehouse_id,
                d.product_id

            ORDER BY
                d.demand_date

            ROWS BETWEEN
                28 PRECEDING
                AND 1 PRECEDING

        ) AS historical_28d_units,


        AVG(
            d.units_sold::numeric
        ) OVER (

            PARTITION BY
                d.warehouse_id,
                d.product_id

            ORDER BY
                d.demand_date

            ROWS BETWEEN
                28 PRECEDING
                AND 1 PRECEDING

        ) AS historical_28d_avg_units,


        STDDEV_SAMP(
            d.units_sold::numeric
        ) OVER (

            PARTITION BY
                d.warehouse_id,
                d.product_id

            ORDER BY
                d.demand_date

            ROWS BETWEEN
                28 PRECEDING
                AND 1 PRECEDING

        ) AS historical_28d_demand_stddev,


        -- ====================================================
        -- RECENT INVENTORY MOVEMENT HISTORY
        --
        -- Again, current date deliberately excluded.
        -- ====================================================

        SUM(
            d.receipt_units
        ) OVER (

            PARTITION BY
                d.warehouse_id,
                d.product_id

            ORDER BY
                d.demand_date

            ROWS BETWEEN
                7 PRECEDING
                AND 1 PRECEDING

        ) AS historical_7d_receipt_units,


        SUM(
            d.reservation_units
        ) OVER (

            PARTITION BY
                d.warehouse_id,
                d.product_id

            ORDER BY
                d.demand_date

            ROWS BETWEEN
                7 PRECEDING
                AND 1 PRECEDING

        ) AS historical_7d_reservation_units,


        SUM(
            d.release_units
        ) OVER (

            PARTITION BY
                d.warehouse_id,
                d.product_id

            ORDER BY
                d.demand_date

            ROWS BETWEEN
                7 PRECEDING
                AND 1 PRECEDING

        ) AS historical_7d_release_units,


        SUM(
            d.shipment_units
        ) OVER (

            PARTITION BY
                d.warehouse_id,
                d.product_id

            ORDER BY
                d.demand_date

            ROWS BETWEEN
                7 PRECEDING
                AND 1 PRECEDING

        ) AS historical_7d_shipment_units,


        -- ====================================================
        -- FUTURE OBSERVATION WINDOW
        --
        -- TARGET CONSTRUCTION ONLY.
        -- ====================================================

        COUNT(*) OVER (

            PARTITION BY
                d.warehouse_id,
                d.product_id

            ORDER BY
                d.demand_date

            ROWS BETWEEN
                CURRENT ROW
                AND 6 FOLLOWING

        ) AS future_observation_days,


        MIN(
            d.ending_available_qty
        ) OVER (

            PARTITION BY
                d.warehouse_id,
                d.product_id

            ORDER BY
                d.demand_date

            ROWS BETWEEN
                CURRENT ROW
                AND 6 FOLLOWING

        ) AS future_min_available_qty_raw,


        SUM(

            CASE

                WHEN d.ending_available_qty <= 0
                THEN 1

                ELSE 0

            END

        ) OVER (

            PARTITION BY
                d.warehouse_id,
                d.product_id

            ORDER BY
                d.demand_date

            ROWS BETWEEN
                CURRENT ROW
                AND 6 FOLLOWING

        ) AS future_stockout_days_raw,


        MAX(

            CASE

                WHEN
                    d.ending_available_qty
                    <= d.snapshot_reorder_point

                THEN 1

                ELSE 0

            END

        ) OVER (

            PARTITION BY
                d.warehouse_id,
                d.product_id

            ORDER BY
                d.demand_date

            ROWS BETWEEN
                CURRENT ROW
                AND 6 FOLLOWING

        ) AS future_reorder_breach_raw


    FROM vw_warehouse_product_daily AS d
),


engineered AS (

    SELECT

        h.*,


        -- ====================================================
        -- CALENDAR FEATURES
        -- ====================================================

        EXTRACT(
            ISODOW FROM h.demand_date
        )::integer AS day_of_week,


        EXTRACT(
            MONTH FROM h.demand_date
        )::integer AS month_of_year,


        CASE

            WHEN EXTRACT(
                ISODOW FROM h.demand_date
            ) IN (6, 7)

            THEN 1

            ELSE 0

        END AS is_weekend,


        -- ====================================================
        -- INVENTORY PRESSURE
        -- ====================================================

        CASE

            WHEN h.snapshot_reorder_point > 0

            THEN ROUND(
                (
                    h.prior_day_available_qty
                    /
                    h.snapshot_reorder_point::numeric
                ),
                4
            )

            ELSE NULL

        END AS available_to_reorder_ratio,


        CASE

            WHEN h.prior_day_on_hand_qty > 0

            THEN ROUND(
                (
                    h.prior_day_reserved_qty
                    * 100.0
                    /
                    h.prior_day_on_hand_qty
                )::numeric,
                2
            )

            ELSE NULL

        END AS prior_reserved_inventory_pct,


        -- ====================================================
        -- HISTORICAL DAYS OF SUPPLY
        -- ====================================================

        CASE

            WHEN h.prior_day_available_qty <= 0
            THEN 0::numeric

            WHEN h.historical_7d_avg_units > 0

            THEN ROUND(
                (
                    h.prior_day_available_qty
                    /
                    h.historical_7d_avg_units
                )::numeric,
                2
            )

            ELSE NULL

        END AS historical_days_of_supply_7d,


        CASE

            WHEN h.prior_day_available_qty <= 0
            THEN 0::numeric

            WHEN h.historical_28d_avg_units > 0

            THEN ROUND(
                (
                    h.prior_day_available_qty
                    /
                    h.historical_28d_avg_units
                )::numeric,
                2
            )

            ELSE NULL

        END AS historical_days_of_supply_28d,


        -- ====================================================
        -- DEMAND ACCELERATION
        -- ====================================================

        CASE

            WHEN h.historical_28d_avg_units > 0

            THEN ROUND(
                (
                    h.historical_7d_avg_units
                    /
                    h.historical_28d_avg_units
                )::numeric,
                4
            )

            ELSE NULL

        END AS demand_acceleration_ratio,


        -- ====================================================
        -- DEMAND VARIABILITY
        -- ====================================================

        CASE

            WHEN h.historical_28d_avg_units > 0

            THEN ROUND(
                (
                    h.historical_28d_demand_stddev
                    /
                    h.historical_28d_avg_units
                )::numeric,
                4
            )

            ELSE NULL

        END AS demand_coefficient_of_variation_28d,


        -- ====================================================
        -- PRIOR-DAY REORDER FLAGS
        -- ====================================================

        CASE

            WHEN h.prior_day_available_qty <= 0
            THEN 1

            ELSE 0

        END AS prior_day_stockout_flag,


        CASE

            WHEN
                h.prior_day_available_qty
                <= h.snapshot_reorder_point

            THEN 1

            ELSE 0

        END AS prior_day_reorder_flag,


        GREATEST(
            h.snapshot_reorder_point
            - h.prior_day_available_qty,
            0
        ) AS prior_day_reorder_gap_units,


        -- ====================================================
        -- TARGET LABELS
        --
        -- Only created when the complete seven-day future
        -- observation window exists.
        -- ====================================================

        CASE

            WHEN h.future_observation_days = 7

            THEN CASE

                WHEN h.future_stockout_days_raw > 0
                THEN 1

                ELSE 0

            END

            ELSE NULL

        END AS target_stockout_next_7d,


        CASE

            WHEN h.future_observation_days = 7

            THEN h.future_stockout_days_raw

            ELSE NULL

        END AS target_stockout_days_next_7d,


        CASE

            WHEN h.future_observation_days = 7

            THEN h.future_reorder_breach_raw

            ELSE NULL

        END AS target_reorder_breach_next_7d,


        CASE

            WHEN h.future_observation_days = 7

            THEN h.future_min_available_qty_raw

            ELSE NULL

        END AS target_min_available_next_7d,


        -- ====================================================
        -- ML ELIGIBILITY
        --
        -- Require:
        --
        --     28 complete historical days
        --     prior inventory state
        --     full future 7-day target horizon
        -- ====================================================

        CASE

            WHEN
                h.historical_observation_days_28d = 28

                AND h.prior_day_available_qty
                    IS NOT NULL

                AND h.future_observation_days = 7

            THEN 1

            ELSE 0

        END AS ml_feature_eligible


    FROM history AS h
),


finalized AS (

    SELECT

        e.*,


        -- ====================================================
        -- HUMAN-READABLE CURRENT RISK BAND
        --
        -- Uses historical / prior-day information only.
        -- ====================================================

        CASE

            WHEN e.prior_day_available_qty IS NULL
            THEN 'UNKNOWN'

            WHEN e.historical_observation_days_7d < 7
            THEN 'WARMUP'

            WHEN e.prior_day_available_qty <= 0
            THEN 'STOCKOUT'

            WHEN
                e.prior_day_available_qty
                <= e.snapshot_reorder_point

            THEN 'CRITICAL'

            WHEN
                e.historical_days_of_supply_7d
                IS NOT NULL

                AND
                e.historical_days_of_supply_7d <= 3

            THEN 'HIGH'

            WHEN
                e.historical_days_of_supply_7d
                IS NOT NULL

                AND
                e.historical_days_of_supply_7d <= 7

            THEN 'MEDIUM'

            ELSE 'LOW'

        END AS risk_band


    FROM engineered AS e
)


SELECT

    *

FROM finalized
;



-- ============================================================
-- VALIDATION 1
-- Grain
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
    ) AS positions,

    COUNT(*)
    -
    COUNT(
        DISTINCT (
            demand_date,
            warehouse_id,
            product_id
        )
    ) AS duplicate_grain_rows

FROM vw_inventory_risk_features
;



-- ============================================================
-- VALIDATION 2
-- Historical and future-window coverage
-- ============================================================


SELECT

    COUNT(*) AS total_rows,

    COUNT(*) FILTER (
        WHERE historical_observation_days_28d = 28
    ) AS rows_with_28d_history,

    COUNT(*) FILTER (
        WHERE future_observation_days = 7
    ) AS rows_with_full_7d_target,

    COUNT(*) FILTER (
        WHERE ml_feature_eligible = 1
    ) AS ml_eligible_rows,

    COUNT(*) FILTER (
        WHERE future_observation_days < 7
    ) AS incomplete_target_rows

FROM vw_inventory_risk_features
;



-- ============================================================
-- VALIDATION 3
-- Demand reconciliation
-- ============================================================


SELECT

    SUM(units_sold)
        AS risk_model_units,

    (
        SELECT
            SUM(units_sold)

        FROM vw_warehouse_product_daily
    ) AS operational_model_units,

    SUM(units_sold)
    -
    (
        SELECT
            SUM(units_sold)

        FROM vw_warehouse_product_daily
    ) AS units_difference,


    ROUND(
        SUM(revenue)::numeric,
        2
    ) AS risk_model_revenue,

    (
        SELECT

            ROUND(
                SUM(revenue)::numeric,
                2
            )

        FROM vw_warehouse_product_daily
    ) AS operational_model_revenue,


    ROUND(
        (
            SUM(revenue)
            -
            (
                SELECT
                    SUM(revenue)

                FROM vw_warehouse_product_daily
            )
        )::numeric,
        2
    ) AS revenue_difference

FROM vw_inventory_risk_features
;



-- ============================================================
-- VALIDATION 4
-- Target / eligibility integrity
-- ============================================================


SELECT

    COUNT(*) FILTER (

        WHERE
            future_observation_days < 7

            AND target_stockout_next_7d
                IS NOT NULL

    ) AS incomplete_horizon_with_stockout_target,


    COUNT(*) FILTER (

        WHERE
            future_observation_days < 7

            AND target_reorder_breach_next_7d
                IS NOT NULL

    ) AS incomplete_horizon_with_reorder_target,


    COUNT(*) FILTER (

        WHERE
            target_stockout_next_7d
            NOT IN (0, 1)

    ) AS invalid_stockout_labels,


    COUNT(*) FILTER (

        WHERE
            target_reorder_breach_next_7d
            NOT IN (0, 1)

    ) AS invalid_reorder_labels,


    COUNT(*) FILTER (

        WHERE
            ml_feature_eligible = 1

            AND historical_observation_days_28d
                <> 28

    ) AS eligible_without_full_history,


    COUNT(*) FILTER (

        WHERE
            ml_feature_eligible = 1

            AND future_observation_days
                <> 7

    ) AS eligible_without_full_target

FROM vw_inventory_risk_features
;



-- ============================================================
-- VALIDATION 5
-- Inventory-history integrity
-- ============================================================


SELECT

    COUNT(*) FILTER (

        WHERE prior_day_on_hand_qty < 0

    ) AS negative_prior_on_hand,


    COUNT(*) FILTER (

        WHERE prior_day_reserved_qty < 0

    ) AS negative_prior_reserved,


    COUNT(*) FILTER (

        WHERE
            prior_day_reserved_qty
            > prior_day_on_hand_qty

    ) AS prior_reserved_exceeds_on_hand,


    COUNT(*) FILTER (

        WHERE historical_7d_units < 0

    ) AS negative_historical_7d_demand,


    COUNT(*) FILTER (

        WHERE historical_28d_units < 0

    ) AS negative_historical_28d_demand

FROM vw_inventory_risk_features
;



-- ============================================================
-- VALIDATION 6
-- Target distribution
-- ============================================================


SELECT

    COUNT(*) FILTER (
        WHERE ml_feature_eligible = 1
    ) AS eligible_rows,


    COUNT(*) FILTER (

        WHERE
            ml_feature_eligible = 1

            AND target_stockout_next_7d = 1

    ) AS stockout_positive_rows,


    ROUND(

        COUNT(*) FILTER (

            WHERE
                ml_feature_eligible = 1

                AND target_stockout_next_7d = 1

        ) * 100.0

        /

        NULLIF(
            COUNT(*) FILTER (
                WHERE ml_feature_eligible = 1
            ),
            0
        ),

        2

    ) AS stockout_positive_rate_pct,


    COUNT(*) FILTER (

        WHERE
            ml_feature_eligible = 1

            AND target_reorder_breach_next_7d = 1

    ) AS reorder_positive_rows,


    ROUND(

        COUNT(*) FILTER (

            WHERE
                ml_feature_eligible = 1

                AND target_reorder_breach_next_7d = 1

        ) * 100.0

        /

        NULLIF(
            COUNT(*) FILTER (
                WHERE ml_feature_eligible = 1
            ),
            0
        ),

        2

    ) AS reorder_positive_rate_pct

FROM vw_inventory_risk_features
;



-- ============================================================
-- VALIDATION 7
-- Risk-band distribution
-- ============================================================


SELECT

    risk_band,

    COUNT(*) AS rows,

    ROUND(
        COUNT(*) * 100.0
        /
        SUM(COUNT(*))
        OVER (),
        2
    ) AS row_pct

FROM vw_inventory_risk_features

GROUP BY
    risk_band

ORDER BY

    CASE risk_band

        WHEN 'STOCKOUT'
            THEN 1

        WHEN 'CRITICAL'
            THEN 2

        WHEN 'HIGH'
            THEN 3

        WHEN 'MEDIUM'
            THEN 4

        WHEN 'LOW'
            THEN 5

        WHEN 'WARMUP'
            THEN 6

        WHEN 'UNKNOWN'
            THEN 7

        ELSE 8

    END
;



-- ============================================================
-- VALIDATION 8
-- ML-ready preview
-- ============================================================


SELECT

    demand_date,

    warehouse_code,

    sku,

    category_name,

    snapshot_reorder_point,

    prior_day_on_hand_qty,

    prior_day_reserved_qty,

    prior_day_available_qty,

    lag_1_units,

    lag_7_units,

    historical_7d_units,

    ROUND(
        historical_7d_avg_units,
        2
    ) AS historical_7d_avg_units,

    historical_28d_units,

    ROUND(
        historical_28d_avg_units,
        2
    ) AS historical_28d_avg_units,

    historical_days_of_supply_7d,

    historical_days_of_supply_28d,

    available_to_reorder_ratio,

    demand_acceleration_ratio,

    demand_coefficient_of_variation_28d,

    historical_7d_receipt_units,

    historical_7d_shipment_units,

    risk_band,

    target_stockout_next_7d,

    target_reorder_breach_next_7d

FROM vw_inventory_risk_features

WHERE ml_feature_eligible = 1

ORDER BY

    warehouse_id,
    product_id,
    demand_date

LIMIT 30
;
