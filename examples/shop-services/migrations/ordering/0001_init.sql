-- The Order aggregate's current state (no event sourcing).
CREATE TABLE orders (
  id      TEXT PRIMARY KEY,
  status  TEXT NOT NULL CHECK (status IN ('placed', 'confirmed', 'cancelled')),
  amount  INTEGER NOT NULL CHECK (amount > 0),
  version INTEGER NOT NULL
);
-- Optimistic concurrency: a save must raise the version by exactly one from the
-- stored row, so a save based on a stale load fails and rolls its batch back.
CREATE TRIGGER orders_version BEFORE UPDATE ON orders
WHEN NEW.version <> OLD.version + 1
BEGIN SELECT RAISE(ABORT, 'version_conflict'); END;

CREATE TABLE inbox  (message_id TEXT PRIMARY KEY);
CREATE TABLE outbox (seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT NOT NULL UNIQUE, body TEXT NOT NULL);
