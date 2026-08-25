with fulfillment as (
    select * from {{ ref('fct_fulfillment') }}
)
select
    date_trunc('day', order_ts)::date as order_date,
    warehouse_id,
    count(*) as orders,
    count(*) filter (where shipment_status = 'delivered') as delivered_shipments,
    count(*) filter (where is_late_delivery = 1) as late_deliveries,
    count(*) filter (where is_delivery_exception = 1) as delivery_exceptions,
    round(avg(total_amount)::numeric, 2) as average_order_value,
    round(avg(shipping_cost)::numeric, 2) as average_shipping_cost,
    round(avg(processing_hours)::numeric, 2) as average_processing_hours
from fulfillment
group by 1, 2
