-- ============================================================
-- FulfillAI
-- Model 004: Delivery Features
-- ============================================================
--
-- Grain:
--
--     one row per shipment
--
-- Purpose:
--
--     Build a machine-learning-ready dataset for predicting
--     late delivery and delivery exceptions.
--
-- Leakage policy:
--
--     Predictive features use information available by the
--     time the shipment leaves the warehouse.
--
--     delivered_at and final shipment_status are used only
--     to construct outcome labels.
--
-- ============================================================


CREATE OR REPLACE VIEW vw_delivery_features AS


WITH order_item_metrics AS (

    SELECT

        oi.order_id,

        COUNT(*) AS order_item_lines,

        SUM(
            oi.quantity
        ) AS total_units,

        COUNT(
            DISTINCT oi.product_id
        ) AS distinct_products,

        ROUND(
            AVG(
                oi.unit_price
            )::numeric,
            2
        ) AS avg_item_price,

        ROUND(
            MAX(
                oi.unit_price
            )::numeric,
            2
        ) AS max_item_price

    FROM order_items AS oi

    GROUP BY
        oi.order_id
),


order_weight_metrics AS (

    SELECT

        oi.order_id,

        ROUND(
            SUM(
                oi.quantity
                * p.weight_kg
            )::numeric,
            3
        ) AS total_weight_kg

    FROM order_items AS oi

    JOIN products AS p
        ON p.product_id = oi.product_id

    GROUP BY
        oi.order_id
),


shipment_base AS (

    SELECT

        s.shipment_id,

        s.shipment_external_id,

        s.order_id,

        o.order_external_id,


        -- ====================================================
        -- Warehouse dimensions
        -- ====================================================

        s.warehouse_id,

        w.warehouse_code,

        w.warehouse_name,

        w.city AS warehouse_city,

        w.country_code AS warehouse_country_code,


        -- ====================================================
        -- Destination dimensions
        -- ====================================================

        o.destination_country,

        o.destination_region,


        -- ====================================================
        -- Order attributes known before shipment
        -- ====================================================

        o.shipping_method,

        o.payment_method,

        o.total_amount AS order_value,

        COALESCE(
            oim.order_item_lines,
            0
        ) AS order_item_lines,

        COALESCE(
            oim.total_units,
            0
        ) AS total_units,

        COALESCE(
            oim.distinct_products,
            0
        ) AS distinct_products,

        oim.avg_item_price,

        oim.max_item_price,

        owm.total_weight_kg,


        -- ====================================================
        -- Carrier
        -- ====================================================

        s.carrier,


        -- ====================================================
        -- Timestamps
        -- ====================================================

        o.order_ts,

        o.promised_delivery_ts,

        s.shipped_at,

        s.expected_delivery_at,

        s.delivered_at,


        -- ====================================================
        -- Final outcomes
        -- ====================================================

        s.shipment_status,

        s.shipping_cost


    FROM shipments AS s

    JOIN orders AS o
        ON o.order_id = s.order_id

    JOIN warehouses AS w
        ON w.warehouse_id = s.warehouse_id

    LEFT JOIN order_item_metrics AS oim
        ON oim.order_id = s.order_id

    LEFT JOIN order_weight_metrics AS owm
        ON owm.order_id = s.order_id
),


feature_base AS (

    SELECT

        sb.*,


        -- ====================================================
        -- Calendar features known at order time
        -- ====================================================

        sb.order_ts::date
            AS order_date,

        EXTRACT(
            HOUR FROM sb.order_ts
        )::integer AS order_hour,

        EXTRACT(
            ISODOW FROM sb.order_ts
        )::integer AS order_day_of_week,

        EXTRACT(
            MONTH FROM sb.order_ts
        )::integer AS order_month,

        CASE

            WHEN EXTRACT(
                ISODOW FROM sb.order_ts
            ) IN (6, 7)

            THEN 1

            ELSE 0

        END AS order_is_weekend,


        -- ====================================================
        -- Shipment calendar
        -- ====================================================

        sb.shipped_at::date
            AS ship_date,

        EXTRACT(
            HOUR FROM sb.shipped_at
        )::integer AS ship_hour,

        EXTRACT(
            ISODOW FROM sb.shipped_at
        )::integer AS ship_day_of_week,

        CASE

            WHEN EXTRACT(
                ISODOW FROM sb.shipped_at
            ) IN (6, 7)

            THEN 1

            ELSE 0

        END AS ship_is_weekend,


        -- ====================================================
        -- Processing duration
        --
        -- Known once the order has shipped.
        -- ====================================================

        ROUND(
            (
                EXTRACT(
                    EPOCH FROM (
                        sb.shipped_at
                        - sb.order_ts
                    )
                )
                / 3600.0
            )::numeric,
            2
        ) AS processing_hours,


        -- ====================================================
        -- Promised service window
        -- ====================================================

        ROUND(
            (
                EXTRACT(
                    EPOCH FROM (
                        sb.promised_delivery_ts
                        - sb.order_ts
                    )
                )
                / 3600.0
            )::numeric,
            2
        ) AS promised_total_hours,


        -- ====================================================
        -- Expected carrier transit window
        --
        -- Known at shipment time.
        -- ====================================================

        ROUND(
            (
                EXTRACT(
                    EPOCH FROM (
                        sb.expected_delivery_at
                        - sb.shipped_at
                    )
                )
                / 3600.0
            )::numeric,
            2
        ) AS expected_transit_hours,


        -- ====================================================
        -- Shipping economics
        -- ====================================================

        CASE

            WHEN sb.order_value > 0

            THEN ROUND(
                (
                    sb.shipping_cost
                    /
                    sb.order_value
                    * 100
                )::numeric,
                2
            )

            ELSE NULL

        END AS shipping_cost_pct_of_order,


        CASE

            WHEN sb.total_units > 0

            THEN ROUND(
                (
                    sb.shipping_cost
                    /
                    sb.total_units
                )::numeric,
                2
            )

            ELSE NULL

        END AS shipping_cost_per_unit,


        CASE

            WHEN sb.total_weight_kg > 0

            THEN ROUND(
                (
                    sb.shipping_cost
                    /
                    sb.total_weight_kg
                )::numeric,
                2
            )

            ELSE NULL

        END AS shipping_cost_per_kg


    FROM shipment_base AS sb
),


label_layer AS (

    SELECT

        fb.*,


        -- ====================================================
        -- Outcome labels
        --
        -- These columns MUST NOT be used as predictive inputs.
        -- ====================================================

        CASE

            WHEN fb.shipment_status = 'exception'
            THEN 1

            ELSE 0

        END AS is_delivery_exception,


        CASE

            WHEN
                fb.shipment_status = 'delivered'
                AND fb.delivered_at
                    > fb.expected_delivery_at

            THEN 1

            ELSE 0

        END AS is_late_delivery,


        CASE

            WHEN fb.shipment_status = 'delivered'
            THEN 1

            ELSE 0

        END AS is_delivered,


        -- ====================================================
        -- Outcome timing
        -- ====================================================

        CASE

            WHEN fb.delivered_at IS NOT NULL

            THEN ROUND(
                (
                    EXTRACT(
                        EPOCH FROM (
                            fb.delivered_at
                            - fb.shipped_at
                        )
                    )
                    / 3600.0
                )::numeric,
                2
            )

            ELSE NULL

        END AS actual_transit_hours,


        CASE

            WHEN fb.delivered_at IS NOT NULL

            THEN ROUND(
                (
                    EXTRACT(
                        EPOCH FROM (
                            fb.delivered_at
                            - fb.expected_delivery_at
                        )
                    )
                    / 3600.0
                )::numeric,
                2
            )

            ELSE NULL

        END AS delivery_delay_hours


    FROM feature_base AS fb
)


SELECT

    *

FROM label_layer
;



-- ============================================================
-- VALIDATION 1
-- Grain
-- ============================================================


SELECT

    COUNT(*) AS model_rows,

    COUNT(
        DISTINCT shipment_id
    ) AS distinct_shipments,

    COUNT(*) -
    COUNT(
        DISTINCT shipment_id
    ) AS duplicate_shipment_rows

FROM vw_delivery_features
;



-- ============================================================
-- VALIDATION 2
-- Source shipment reconciliation
-- ============================================================


SELECT

    COUNT(*) AS model_shipments,

    (
        SELECT
            COUNT(*)
        FROM shipments
    ) AS source_shipments,

    COUNT(*) -
    (
        SELECT
            COUNT(*)
        FROM shipments
    ) AS difference

FROM vw_delivery_features
;



-- ============================================================
-- VALIDATION 3
-- Known historical outcome counts
-- ============================================================


SELECT

    COUNT(*) AS shipments,

    SUM(
        is_delivered
    ) AS delivered,

    SUM(
        is_delivery_exception
    ) AS exceptions,

    SUM(
        is_late_delivery
    ) AS late_deliveries,

    ROUND(
        SUM(
            is_delivery_exception
        ) * 100.0
        /
        COUNT(*),
        2
    ) AS exception_rate_pct,

    ROUND(
        SUM(
            is_late_delivery
        ) * 100.0
        /
        NULLIF(
            SUM(
                is_delivered
            ),
            0
        ),
        2
    ) AS late_delivery_rate_pct

FROM vw_delivery_features
;



-- ============================================================
-- VALIDATION 4
-- Referential integrity
-- ============================================================


SELECT

    COUNT(*) FILTER (
        WHERE order_id IS NULL
    ) AS missing_order_id,

    COUNT(*) FILTER (
        WHERE warehouse_id IS NULL
    ) AS missing_warehouse_id,

    COUNT(*) FILTER (
        WHERE carrier IS NULL
    ) AS missing_carrier,

    COUNT(*) FILTER (
        WHERE shipping_method IS NULL
    ) AS missing_shipping_method,

    COUNT(*) FILTER (
        WHERE total_units <= 0
    ) AS invalid_total_units,

    COUNT(*) FILTER (
        WHERE order_item_lines <= 0
    ) AS invalid_item_lines

FROM vw_delivery_features
;



-- ============================================================
-- VALIDATION 5
-- Timestamp integrity
-- ============================================================


SELECT

    COUNT(*) FILTER (
        WHERE shipped_at < order_ts
    ) AS shipped_before_order,

    COUNT(*) FILTER (
        WHERE expected_delivery_at < shipped_at
    ) AS expected_before_shipment,

    COUNT(*) FILTER (
        WHERE
            delivered_at IS NOT NULL
            AND delivered_at < shipped_at
    ) AS delivered_before_shipment,

    COUNT(*) FILTER (
        WHERE processing_hours < 0
    ) AS negative_processing_hours,

    COUNT(*) FILTER (
        WHERE expected_transit_hours < 0
    ) AS negative_expected_transit_hours

FROM vw_delivery_features
;



-- ============================================================
-- VALIDATION 6
-- Label consistency
-- ============================================================


SELECT

    COUNT(*) FILTER (
        WHERE
            is_late_delivery = 1
            AND is_delivered = 0
    ) AS late_but_not_delivered,

    COUNT(*) FILTER (
        WHERE
            is_delivery_exception = 1
            AND is_delivered = 1
    ) AS exception_and_delivered,

    COUNT(*) FILTER (
        WHERE
            is_delivered = 1
            AND delivered_at IS NULL
    ) AS delivered_without_timestamp,

    COUNT(*) FILTER (
        WHERE
            is_late_delivery = 1
            AND delivered_at
                <= expected_delivery_at
    ) AS invalid_late_label

FROM vw_delivery_features
;



-- ============================================================
-- VALIDATION 7
-- Carrier outcome summary
-- ============================================================


SELECT

    carrier,

    COUNT(*) AS shipments,

    SUM(
        is_delivered
    ) AS delivered,

    SUM(
        is_delivery_exception
    ) AS exceptions,

    SUM(
        is_late_delivery
    ) AS late_deliveries,

    ROUND(
        SUM(
            is_delivery_exception
        ) * 100.0
        /
        COUNT(*),
        2
    ) AS exception_rate_pct,

    ROUND(
        SUM(
            is_late_delivery
        ) * 100.0
        /
        NULLIF(
            SUM(
                is_delivered
            ),
            0
        ),
        2
    ) AS late_delivery_rate_pct,

    ROUND(
        AVG(
            processing_hours
        )::numeric,
        2
    ) AS avg_processing_hours,

    ROUND(
        AVG(
            expected_transit_hours
        )::numeric,
        2
    ) AS avg_expected_transit_hours

FROM vw_delivery_features

GROUP BY
    carrier

ORDER BY
    shipments DESC
;



-- ============================================================
-- VALIDATION 8
-- Shipping method summary
-- ============================================================


SELECT

    shipping_method,

    COUNT(*) AS shipments,

    ROUND(
        AVG(
            order_value
        )::numeric,
        2
    ) AS avg_order_value,

    ROUND(
        AVG(
            total_units
        )::numeric,
        2
    ) AS avg_units,

    ROUND(
        AVG(
            total_weight_kg
        )::numeric,
        2
    ) AS avg_weight_kg,

    ROUND(
        AVG(
            processing_hours
        )::numeric,
        2
    ) AS avg_processing_hours,

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
            is_delivery_exception
        ) * 100.0
        /
        COUNT(*),
        2
    ) AS exception_rate_pct,

    ROUND(
        SUM(
            is_late_delivery
        ) * 100.0
        /
        NULLIF(
            SUM(
                is_delivered
            ),
            0
        ),
        2
    ) AS late_delivery_rate_pct

FROM vw_delivery_features

GROUP BY
    shipping_method

ORDER BY
    shipments DESC
;



-- ============================================================
-- VALIDATION 9
-- Preview ML rows
--
-- Outcome fields are intentionally visible here for inspection.
-- They will later be separated from feature columns during
-- dataset export/model training.
-- ============================================================


SELECT

    shipment_id,

    order_id,

    warehouse_code,

    destination_country,

    shipping_method,

    carrier,

    order_value,

    total_units,

    distinct_products,

    total_weight_kg,

    order_day_of_week,

    order_is_weekend,

    processing_hours,

    promised_total_hours,

    expected_transit_hours,

    shipping_cost,

    is_delivery_exception,

    is_late_delivery

FROM vw_delivery_features

ORDER BY
    shipment_id

LIMIT 20
;