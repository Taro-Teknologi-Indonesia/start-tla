-- The Payment aggregate: the provider's answer for each order.
CREATE TABLE payments (
  order_id TEXT PRIMARY KEY,
  status   TEXT NOT NULL CHECK (status IN ('captured', 'declined', 'refunded'))
);

CREATE TABLE inbox  (message_id TEXT PRIMARY KEY);
CREATE TABLE outbox (seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT NOT NULL UNIQUE, body TEXT NOT NULL);
