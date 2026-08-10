-- Run as superuser after CREATE DATABASE docrec OWNER docrec;
-- psql -U postgres -d docrec -f seed_pilot_user.sql

INSERT INTO users (telegram_user_id, display_name, is_whitelisted)
VALUES (322646729, 'Pilot', TRUE)
ON CONFLICT (telegram_user_id) DO UPDATE SET is_whitelisted = TRUE, display_name = EXCLUDED.display_name;

INSERT INTO user_bindings (telegram_user_id, org_id, warehouse_id)
VALUES (322646729, 'org-001', 'wh-001')
ON CONFLICT (telegram_user_id) DO UPDATE
SET org_id = EXCLUDED.org_id, warehouse_id = EXCLUDED.warehouse_id, updated_at = now();
