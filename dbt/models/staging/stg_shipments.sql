select
    shipment_id,
    shipment_external_id,
    order_id,
    warehouse_id,
    carrier,
    shipment_status,
    shipped_at,
    expected_delivery_at,
    delivered_at,
    shipping_cost,
    case
        when shipment_status = 'delivered'
         and delivered_at > expected_delivery_at then 1
        else 0
    end as is_late_delivery,
    case when shipment_status = 'exception' then 1 else 0 end as is_delivery_exception
from {{ source('operational', 'shipments') }}
