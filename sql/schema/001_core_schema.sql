BEGIN;

-- =========================================================
-- FulfillAI core operational schema
-- =========================================================


-- ---------------------------------------------------------
-- Customers
-- ---------------------------------------------------------

CREATE TABLE customers (
    customer_id BIGSERIAL PRIMARY KEY,
    customer_external_id VARCHAR(40) NOT NULL UNIQUE,
    country_code CHAR(2) NOT NULL,
    region VARCHAR(100),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);


-- ---------------------------------------------------------
-- Product categories
-- ---------------------------------------------------------

CREATE TABLE product_categories (
    category_id SMALLSERIAL PRIMARY KEY,
    category_name VARCHAR(100) NOT NULL UNIQUE
);


-- ---------------------------------------------------------
-- Products
-- ---------------------------------------------------------

CREATE TABLE products (
    product_id BIGSERIAL PRIMARY KEY,
    sku VARCHAR(50) NOT NULL UNIQUE,
    product_name VARCHAR(200) NOT NULL,
    category_id SMALLINT NOT NULL
        REFERENCES product_categories(category_id),
    unit_price NUMERIC(12, 2) NOT NULL
        CHECK (unit_price >= 0),
    unit_cost NUMERIC(12, 2)
        CHECK (unit_cost IS NULL OR unit_cost >= 0),
    weight_kg NUMERIC(10, 3)
        CHECK (weight_kg IS NULL OR weight_kg > 0),
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);


-- ---------------------------------------------------------
-- Warehouses
-- ---------------------------------------------------------

CREATE TABLE warehouses (
    warehouse_id SMALLSERIAL PRIMARY KEY,
    warehouse_code VARCHAR(20) NOT NULL UNIQUE,
    warehouse_name VARCHAR(100) NOT NULL,
    city VARCHAR(100) NOT NULL,
    country_code CHAR(2) NOT NULL,
    capacity_units INTEGER NOT NULL
        CHECK (capacity_units > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);


-- ---------------------------------------------------------
-- Current inventory state
-- ---------------------------------------------------------

CREATE TABLE inventory (
    warehouse_id SMALLINT NOT NULL
        REFERENCES warehouses(warehouse_id),
    product_id BIGINT NOT NULL
        REFERENCES products(product_id),
    on_hand_qty INTEGER NOT NULL DEFAULT 0
        CHECK (on_hand_qty >= 0),
    reserved_qty INTEGER NOT NULL DEFAULT 0
        CHECK (reserved_qty >= 0),
    reorder_point INTEGER NOT NULL DEFAULT 0
        CHECK (reorder_point >= 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (warehouse_id, product_id),

    CHECK (reserved_qty <= on_hand_qty)
);


-- ---------------------------------------------------------
-- Orders
-- ---------------------------------------------------------

CREATE TABLE orders (
    order_id BIGSERIAL PRIMARY KEY,
    order_external_id VARCHAR(40) NOT NULL UNIQUE,

    customer_id BIGINT NOT NULL
        REFERENCES customers(customer_id),

    warehouse_id SMALLINT
        REFERENCES warehouses(warehouse_id),

    order_status VARCHAR(30) NOT NULL
        CHECK (
            order_status IN (
                'created',
                'payment_confirmed',
                'processing',
                'packed',
                'shipped',
                'delivered',
                'cancelled'
            )
        ),

    shipping_method VARCHAR(20) NOT NULL
        CHECK (
            shipping_method IN (
                'standard',
                'express',
                'same_day'
            )
        ),

    payment_method VARCHAR(30),

    destination_country CHAR(2) NOT NULL,
    destination_region VARCHAR(100),

    order_ts TIMESTAMPTZ NOT NULL,
    promised_delivery_ts TIMESTAMPTZ NOT NULL,

    total_amount NUMERIC(14, 2) NOT NULL
        CHECK (total_amount >= 0),

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CHECK (promised_delivery_ts >= order_ts)
);


-- ---------------------------------------------------------
-- Order items
-- ---------------------------------------------------------

CREATE TABLE order_items (
    order_item_id BIGSERIAL PRIMARY KEY,

    order_id BIGINT NOT NULL
        REFERENCES orders(order_id)
        ON DELETE CASCADE,

    product_id BIGINT NOT NULL
        REFERENCES products(product_id),

    quantity INTEGER NOT NULL
        CHECK (quantity > 0),

    unit_price NUMERIC(12, 2) NOT NULL
        CHECK (unit_price >= 0),

    UNIQUE (order_id, product_id)
);


-- ---------------------------------------------------------
-- Shipments
-- ---------------------------------------------------------

CREATE TABLE shipments (
    shipment_id BIGSERIAL PRIMARY KEY,

    shipment_external_id VARCHAR(40) NOT NULL UNIQUE,

    order_id BIGINT NOT NULL
        REFERENCES orders(order_id),

    warehouse_id SMALLINT NOT NULL
        REFERENCES warehouses(warehouse_id),

    carrier VARCHAR(100),

    shipment_status VARCHAR(30) NOT NULL
        CHECK (
            shipment_status IN (
                'pending',
                'label_created',
                'in_transit',
                'delivered',
                'exception',
                'returned'
            )
        ),

    shipped_at TIMESTAMPTZ,
    expected_delivery_at TIMESTAMPTZ,
    delivered_at TIMESTAMPTZ,

    shipping_cost NUMERIC(12, 2)
        CHECK (shipping_cost IS NULL OR shipping_cost >= 0),

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CHECK (
        delivered_at IS NULL
        OR shipped_at IS NULL
        OR delivered_at >= shipped_at
    )
);


-- ---------------------------------------------------------
-- Inventory movements
-- ---------------------------------------------------------

CREATE TABLE inventory_movements (
    movement_id BIGSERIAL PRIMARY KEY,

    warehouse_id SMALLINT NOT NULL
        REFERENCES warehouses(warehouse_id),

    product_id BIGINT NOT NULL
        REFERENCES products(product_id),

    order_id BIGINT
        REFERENCES orders(order_id),

    movement_type VARCHAR(30) NOT NULL
        CHECK (
            movement_type IN (
                'receipt',
                'reservation',
                'release',
                'shipment',
                'adjustment',
                'return'
            )
        ),

    quantity_change INTEGER NOT NULL
        CHECK (quantity_change <> 0),

    event_ts TIMESTAMPTZ NOT NULL,

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);


-- ---------------------------------------------------------
-- Operational event stream
-- ---------------------------------------------------------

CREATE TABLE order_events (
    event_id BIGSERIAL PRIMARY KEY,

    event_key VARCHAR(64) NOT NULL UNIQUE,

    order_id BIGINT NOT NULL
        REFERENCES orders(order_id),

    warehouse_id SMALLINT
        REFERENCES warehouses(warehouse_id),

    event_type VARCHAR(50) NOT NULL,

    event_ts TIMESTAMPTZ NOT NULL,

    source VARCHAR(50) NOT NULL,

    payload JSONB NOT NULL DEFAULT '{}'::JSONB,

    ingested_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);


-- =========================================================
-- Indexes
-- =========================================================

CREATE INDEX idx_orders_order_ts
    ON orders(order_ts);

CREATE INDEX idx_orders_status
    ON orders(order_status);

CREATE INDEX idx_orders_warehouse
    ON orders(warehouse_id);

CREATE INDEX idx_order_items_order
    ON order_items(order_id);

CREATE INDEX idx_order_items_product
    ON order_items(product_id);

CREATE INDEX idx_shipments_order
    ON shipments(order_id);

CREATE INDEX idx_shipments_status
    ON shipments(shipment_status);

CREATE INDEX idx_shipments_expected_delivery
    ON shipments(expected_delivery_at);

CREATE INDEX idx_inventory_movements_product_time
    ON inventory_movements(product_id, event_ts);

CREATE INDEX idx_inventory_movements_warehouse_time
    ON inventory_movements(warehouse_id, event_ts);

CREATE INDEX idx_order_events_order_time
    ON order_events(order_id, event_ts);

CREATE INDEX idx_order_events_type_time
    ON order_events(event_type, event_ts);


COMMIT;