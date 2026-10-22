#!/usr/bin/env sh
# Wheelo: test data for local development (was scripts/seed_db.sh).
set -eu
psql "${WHEELO_DATABASE_URL:-postgresql://localhost:5432/wheelo}" <<'SQL'
INSERT INTO scooters (id, status, battery_percent) VALUES ('WH-1042', 'available', 87) ON CONFLICT DO NOTHING;
SQL
