import type { Message } from "../contract";
import { handleOnce, type Outcome } from "../lib/inbox";

export interface OrderView {
  orderId: string;
  status: string;
  version: number;
}

const shown: Partial<Record<Message["type"], string>> = {
  OrderPlaced: "placed",
  OrderConfirmed: "confirmed",
  OrderCancelled: "cancelled",
};

/**
 * The "my orders" read model (`Projector(m)` in the spec). Events reach it in any
 * order, so a row only moves forward: the upsert applies an event only if its
 * version is newer than the row's ("skip_stale" in the spec).
 */
export async function handleProjector(db: D1Database, msg: Message): Promise<Outcome> {
  const status = shown[msg.type];
  if (!status) throw new Error(`projector does not take ${msg.type}`);
  return handleOnce(db, msg, async () => [
    db
      .prepare(
        `INSERT INTO order_view (order_id, status, version) VALUES (?, ?, ?)
         ON CONFLICT(order_id) DO UPDATE SET status = excluded.status, version = excluded.version
         WHERE excluded.version > order_view.version`,
      )
      .bind(msg.orderId, status, msg.version),
  ]);
}

/** GET /orders/:id */
export async function getOrderView(db: D1Database, orderId: string): Promise<OrderView | null> {
  return db
    .prepare("SELECT order_id AS orderId, status, version FROM order_view WHERE order_id = ?")
    .bind(orderId)
    .first<OrderView>();
}
