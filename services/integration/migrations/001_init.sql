-- MVP schema: Telegram → OCR → 1С
-- Apply: psql -U docrec -d docrec -f 001_init.sql

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TYPE packet_status AS ENUM (
    'draft',
    'queued',
    'processing',
    'ready',
    'error',
    'imported'
);

CREATE TYPE document_type AS ENUM (
    'torg12',
    'upd',
    'unknown'
);

CREATE TABLE orgs (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE warehouses (
    id              TEXT PRIMARY KEY,
    org_id          TEXT NOT NULL REFERENCES orgs (id),
    name            TEXT NOT NULL,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX warehouses_org_idx ON warehouses (org_id);

CREATE TABLE users (
    telegram_user_id    BIGINT PRIMARY KEY,
    display_name        TEXT,
    is_whitelisted      BOOLEAN NOT NULL DEFAULT FALSE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Binding: telegram user → current org/warehouse context
CREATE TABLE user_bindings (
    telegram_user_id    BIGINT PRIMARY KEY REFERENCES users (telegram_user_id),
    org_id              TEXT NOT NULL REFERENCES orgs (id),
    warehouse_id        TEXT NOT NULL REFERENCES warehouses (id),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE packets (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    status              packet_status NOT NULL DEFAULT 'draft',
    document_type       document_type,
    telegram_user_id    BIGINT NOT NULL REFERENCES users (telegram_user_id),
    org_id              TEXT NOT NULL REFERENCES orgs (id),
    warehouse_id        TEXT NOT NULL REFERENCES warehouses (id),
    storage_path        TEXT,
    photos_count        INT NOT NULL DEFAULT 0,
    document_number     TEXT,
    document_date       DATE,
    supplier_name       TEXT,
    overall_confidence  NUMERIC(5, 4),
    error_message       TEXT,
    result_json         JSONB,
    recognized_at       TIMESTAMPTZ,
    imported_at         TIMESTAMPTZ,
    imported_by         TEXT,
    ptu_ref             TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX packets_status_idx ON packets (status);
CREATE INDEX packets_org_wh_status_idx ON packets (org_id, warehouse_id, status);
CREATE INDEX packets_user_status_idx ON packets (telegram_user_id, status);
CREATE INDEX packets_created_idx ON packets (created_at DESC);

-- One open draft packet per user (partial unique index)
CREATE UNIQUE INDEX packets_one_draft_per_user_idx
    ON packets (telegram_user_id)
    WHERE status = 'draft';

CREATE TABLE packet_files (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    packet_id           UUID NOT NULL REFERENCES packets (id) ON DELETE CASCADE,
    seq_no              INT NOT NULL,
    filename            TEXT NOT NULL,
    content_type        TEXT NOT NULL DEFAULT 'image/jpeg',
    storage_key         TEXT NOT NULL,
    sha256              TEXT,
    telegram_file_id    TEXT,
    file_unique_id      TEXT,
    size_bytes          BIGINT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (packet_id, seq_no)
);

CREATE INDEX packet_files_packet_idx ON packet_files (packet_id);

-- Dedup Telegram updates (webhook retries)
CREATE TABLE telegram_updates (
    update_id           BIGINT PRIMARY KEY,
    received_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE worker_jobs (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    packet_id           UUID NOT NULL REFERENCES packets (id) ON DELETE CASCADE,
    job_type            TEXT NOT NULL DEFAULT 'recognize',
    attempts            INT NOT NULL DEFAULT 0,
    locked_at           TIMESTAMPTZ,
    locked_by           TEXT,
    run_after           TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_error          TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (packet_id, job_type)
);

CREATE INDEX worker_jobs_poll_idx
    ON worker_jobs (run_after)
    WHERE locked_at IS NULL;

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER packets_updated_at
    BEFORE UPDATE ON packets
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Seed for single-user MVP pilot
INSERT INTO orgs (id, name) VALUES ('org-001', 'Организация пилот');
INSERT INTO warehouses (id, org_id, name) VALUES ('wh-001', 'org-001', 'Склад пилот');

-- Replace TELEGRAM_USER_ID after BotFather / first /start
-- INSERT INTO users (telegram_user_id, display_name, is_whitelisted)
-- VALUES (123456789, 'Pilot User', TRUE);
-- INSERT INTO user_bindings (telegram_user_id, org_id, warehouse_id)
-- VALUES (123456789, 'org-001', 'wh-001');
