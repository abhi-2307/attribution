-- ============================================================
-- Attribution Platform — Initial Schema
-- Schema: attribution (within existing database)
-- ============================================================

CREATE SCHEMA IF NOT EXISTS attribution;

-- Raw pixel events (IMMUTABLE — never update or delete)
CREATE TABLE IF NOT EXISTS attribution.pixel_events_raw (
    event_id          UUID PRIMARY KEY,
    visitor_id        TEXT NOT NULL,
    session_id        TEXT NOT NULL,
    event_name        TEXT NOT NULL,
    url               TEXT,
    path              TEXT,
    referrer          TEXT,
    utm_source        TEXT,
    utm_medium        TEXT,
    utm_campaign      TEXT,
    utm_content       TEXT,
    utm_term          TEXT,
    fbclid            TEXT,
    gclid             TEXT,
    ttclid            TEXT,
    msclkid           TEXT,
    user_agent        TEXT,
    ip_address        TEXT,
    event_timestamp   TIMESTAMPTZ NOT NULL,
    created_at        TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_pixel_events_raw_visitor_id      ON attribution.pixel_events_raw (visitor_id);
CREATE INDEX IF NOT EXISTS ix_pixel_events_raw_session_id      ON attribution.pixel_events_raw (session_id);
CREATE INDEX IF NOT EXISTS ix_pixel_events_raw_event_timestamp ON attribution.pixel_events_raw (event_timestamp);
CREATE INDEX IF NOT EXISTS ix_pixel_events_raw_event_name      ON attribution.pixel_events_raw (event_name);

-- Queue table (replaces Kafka for MVP)
CREATE TABLE IF NOT EXISTS attribution.pixel_event_queue (
    id           UUID PRIMARY KEY,
    event_id     UUID NOT NULL,
    status       TEXT DEFAULT 'pending',   -- pending | processing | done | failed
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    processed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS ix_pixel_event_queue_status     ON attribution.pixel_event_queue (status);
CREATE INDEX IF NOT EXISTS ix_pixel_event_queue_created_at ON attribution.pixel_event_queue (created_at);

-- Sessions
CREATE TABLE IF NOT EXISTS attribution.sessions (
    session_id       TEXT PRIMARY KEY,
    visitor_id       TEXT NOT NULL,
    session_start    TIMESTAMPTZ NOT NULL,
    session_end      TIMESTAMPTZ,
    landing_page     TEXT,
    referrer         TEXT,
    utm_source       TEXT,
    utm_medium       TEXT,
    utm_campaign     TEXT,
    utm_content      TEXT,
    utm_term         TEXT,
    fbclid           TEXT,
    gclid            TEXT,
    ttclid           TEXT,
    msclkid          TEXT,
    page_view_count  INTEGER DEFAULT 1,
    created_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_sessions_visitor_id    ON attribution.sessions (visitor_id);
CREATE INDEX IF NOT EXISTS ix_sessions_session_start ON attribution.sessions (session_start);
CREATE INDEX IF NOT EXISTS ix_sessions_utm_campaign  ON attribution.sessions (utm_campaign);

-- Identity Graph
CREATE TABLE IF NOT EXISTS attribution.identity_graph (
    visitor_id           TEXT PRIMARY KEY,
    email_hash           TEXT UNIQUE,
    shopify_customer_id  TEXT,
    first_seen           TIMESTAMPTZ,
    last_seen            TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS ix_identity_graph_email_hash           ON attribution.identity_graph (email_hash);
CREATE INDEX IF NOT EXISTS ix_identity_graph_shopify_customer_id  ON attribution.identity_graph (shopify_customer_id);

-- Orders (from Shopify webhook)
CREATE TABLE IF NOT EXISTS attribution.orders (
    order_id              TEXT PRIMARY KEY,
    customer_email_hash   TEXT,
    order_value           NUMERIC(12, 2),
    currency              TEXT DEFAULT 'USD',
    line_items            JSONB,
    shopify_created_at    TIMESTAMPTZ,
    created_at            TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_orders_customer_email_hash  ON attribution.orders (customer_email_hash);
CREATE INDEX IF NOT EXISTS ix_orders_shopify_created_at   ON attribution.orders (shopify_created_at);

-- Order Journeys
CREATE TABLE IF NOT EXISTS attribution.order_journeys (
    order_id    TEXT PRIMARY KEY,
    visitor_id  TEXT NOT NULL,
    touchpoints JSONB DEFAULT '[]',
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_order_journeys_visitor_id ON attribution.order_journeys (visitor_id);

-- Attribution Results
CREATE TABLE IF NOT EXISTS attribution.attribution_results (
    id                    TEXT PRIMARY KEY,   -- order_id + '_' + model
    order_id              TEXT NOT NULL,
    model                 TEXT NOT NULL,      -- last_click | first_click | linear | time_decay
    touchpoints_credited  JSONB,
    created_at            TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_attribution_results_order_id ON attribution.attribution_results (order_id);
CREATE INDEX IF NOT EXISTS ix_attribution_results_model    ON attribution.attribution_results (model);
