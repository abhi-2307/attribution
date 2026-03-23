-- ============================================================
-- Attribution Platform — Multi-Client Support
-- Adds `clients` table and `client_id` column to all data tables.
-- ============================================================

-- ─── 1. Clients table ────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS attribution.clients (
    client_id               TEXT PRIMARY KEY,
    name                    TEXT NOT NULL,
    api_key                 TEXT UNIQUE NOT NULL,   -- used to authenticate reporting API calls
    shopify_webhook_secret  TEXT,                   -- per-client Shopify HMAC secret
    created_at              TIMESTAMPTZ DEFAULT NOW()
);

-- ─── 2. Add client_id column to all data tables ──────────────────────────────
--
-- Columns are added as nullable so you can backfill existing data first.
-- After seeding your clients and running the UPDATE statements below,
-- apply NOT NULL:
--
--   ALTER TABLE attribution.<table> ALTER COLUMN client_id SET NOT NULL;

ALTER TABLE attribution.pixel_events_raw    ADD COLUMN IF NOT EXISTS client_id TEXT REFERENCES attribution.clients(client_id);
ALTER TABLE attribution.pixel_event_queue   ADD COLUMN IF NOT EXISTS client_id TEXT REFERENCES attribution.clients(client_id);
ALTER TABLE attribution.sessions            ADD COLUMN IF NOT EXISTS client_id TEXT REFERENCES attribution.clients(client_id);
ALTER TABLE attribution.orders              ADD COLUMN IF NOT EXISTS client_id TEXT REFERENCES attribution.clients(client_id);
ALTER TABLE attribution.order_journeys      ADD COLUMN IF NOT EXISTS client_id TEXT REFERENCES attribution.clients(client_id);
ALTER TABLE attribution.attribution_results ADD COLUMN IF NOT EXISTS client_id TEXT REFERENCES attribution.clients(client_id);

-- identity_graph: drop the global email_hash unique constraint and replace
-- with a per-client one so the same customer can appear across different stores.
ALTER TABLE attribution.identity_graph ADD COLUMN IF NOT EXISTS client_id TEXT REFERENCES attribution.clients(client_id);
ALTER TABLE attribution.identity_graph DROP CONSTRAINT IF EXISTS identity_graph_email_hash_key;
CREATE UNIQUE INDEX IF NOT EXISTS uix_identity_graph_client_email
    ON attribution.identity_graph (client_id, email_hash)
    WHERE email_hash IS NOT NULL;

-- ─── 3. Indexes on client_id ─────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS ix_pixel_events_raw_client_id      ON attribution.pixel_events_raw    (client_id);
CREATE INDEX IF NOT EXISTS ix_pixel_event_queue_client_id     ON attribution.pixel_event_queue   (client_id);
CREATE INDEX IF NOT EXISTS ix_sessions_client_id              ON attribution.sessions            (client_id);
CREATE INDEX IF NOT EXISTS ix_identity_graph_client_id        ON attribution.identity_graph      (client_id);
CREATE INDEX IF NOT EXISTS ix_orders_client_id                ON attribution.orders              (client_id);
CREATE INDEX IF NOT EXISTS ix_order_journeys_client_id        ON attribution.order_journeys      (client_id);
CREATE INDEX IF NOT EXISTS ix_attribution_results_client_id   ON attribution.attribution_results (client_id);

-- ─── 4. Example: seed your clients ──────────────────────────────────────────
--
-- INSERT INTO attribution.clients (client_id, name, api_key, shopify_webhook_secret)
-- VALUES
--     ('client_acme',  'Acme Corp',   'apik_acme_xxxxxxxxxxxx',  'shpss_acme_secret'),
--     ('client_beta',  'Beta Brand',  'apik_beta_xxxxxxxxxxxx',  'shpss_beta_secret');
--
-- Then backfill existing rows (if any) before setting NOT NULL:
--
-- UPDATE attribution.pixel_events_raw    SET client_id = 'client_acme' WHERE client_id IS NULL;
-- UPDATE attribution.pixel_event_queue   SET client_id = 'client_acme' WHERE client_id IS NULL;
-- UPDATE attribution.sessions            SET client_id = 'client_acme' WHERE client_id IS NULL;
-- UPDATE attribution.identity_graph      SET client_id = 'client_acme' WHERE client_id IS NULL;
-- UPDATE attribution.orders              SET client_id = 'client_acme' WHERE client_id IS NULL;
-- UPDATE attribution.order_journeys      SET client_id = 'client_acme' WHERE client_id IS NULL;
-- UPDATE attribution.attribution_results SET client_id = 'client_acme' WHERE client_id IS NULL;
--
-- Then enforce NOT NULL:
--
-- ALTER TABLE attribution.pixel_events_raw    ALTER COLUMN client_id SET NOT NULL;
-- ALTER TABLE attribution.pixel_event_queue   ALTER COLUMN client_id SET NOT NULL;
-- ALTER TABLE attribution.sessions            ALTER COLUMN client_id SET NOT NULL;
-- ALTER TABLE attribution.identity_graph      ALTER COLUMN client_id SET NOT NULL;
-- ALTER TABLE attribution.orders              ALTER COLUMN client_id SET NOT NULL;
-- ALTER TABLE attribution.order_journeys      ALTER COLUMN client_id SET NOT NULL;
-- ALTER TABLE attribution.attribution_results ALTER COLUMN client_id SET NOT NULL;
