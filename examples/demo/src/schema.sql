-- Wheelo: rides table (PostgreSQL)
CREATE TABLE rides (
    id            UUID PRIMARY KEY,
    user_id       UUID        NOT NULL REFERENCES users (id),
    scooter_id    TEXT        NOT NULL REFERENCES scooters (id),
    status        TEXT        NOT NULL CHECK (status IN ('active', 'finished', 'cancelled')),
    started_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at   TIMESTAMPTZ,
    minutes       INTEGER,
    price_rub     INTEGER,
    start_point   POINT       NOT NULL,
    end_point     POINT
);

CREATE INDEX rides_user_started_idx ON rides (user_id, started_at DESC);

-- Personal data retention: GPS points are cleared after 180 days.
-- UPDATE rides SET start_point = NULL, end_point = NULL WHERE finished_at < now() - interval '180 days';
