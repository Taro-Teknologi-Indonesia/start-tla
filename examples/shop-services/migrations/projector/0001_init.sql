-- The read model behind the "my orders" page. version is the Order row version of
-- the newest event applied; the row only ever moves forward.
CREATE TABLE order_view (
  order_id TEXT PRIMARY KEY,
  status   TEXT NOT NULL,
  version  INTEGER NOT NULL
);

CREATE TABLE inbox (message_id TEXT PRIMARY KEY);
