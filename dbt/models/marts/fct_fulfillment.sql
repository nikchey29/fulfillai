with orders as (
    select * from {{ ref('stg_orders') }}
),
shipments as (
    select * from {{ ref('stg_shipments') }}
)
select
    o.order_id,
    o.order_external_id,
    o.warehouse_id,
    o.order_status,
    o.shipping_method,
    o.payment_method,
    o.destination_country,
    o.order_ts,
    o.promised_delivery_ts,
    o.total_amount,
    s.shipment_id,
    s.shipment_external_id,
    s.carrier,
    s.shipment_status,
    s.shipped_at,
    s.expected_delivery_at,
    s.delivered_at,
    s.shipping_cost,
    s.is_late_delivery,
    s.is_delivery_exception,
    case
        when s.shipped_at is not null
        then extract(epoch from (s.shipped_at - o.order_ts)) / 3600.0
    end as processing_hours
from orders o
left join shipments s using (order_id)
