-- The Stock aggregate: one row per product, shared by every order.
CREATE TABLE stock (
  sku       TEXT PRIMARY KEY,
  available INTEGER NOT NULL CHECK (available >= 0),
  version   INTEGER NOT NULL
);
CREATE TRIGGER stock_version BEFORE UPDATE ON stock
WHEN NEW.version <> OLD.version + 1
BEGIN SELECT RAISE(ABORT, 'version_conflict'); END;

CREATE TABLE reservations (
  order_id TEXT PRIMARY KEY,
  status   TEXT NOT NULL CHECK (status IN ('reserved', 'rejected', 'released'))
);

CREATE TABLE inbox  (message_id TEXT PRIMARY KEY);
CREATE TABLE outbox (seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT NOT NULL UNIQUE, body TEXT NOT NULL);

-- The one product on sale, with one unit, as in the spec's model.
INSERT INTO stock (sku, available, version) VALUES ('batik-tulis', 1, 0);
