select
    order_id,
    order_external_id,
    customer_id,
    warehouse_id,
    order_status,
    shipping_method,
    payment_method,
    destination_country,
    destination_region,
    order_ts,
    promised_delivery_ts,
    total_amount
from {{ source('operational', 'orders') }}
