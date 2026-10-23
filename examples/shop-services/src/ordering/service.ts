import { emit, type Message } from "../contract";
import { handleOnce, type Outcome } from "../lib/inbox";
import { outboxInserts } from "../lib/outbox";
import { handle, place, type Order } from "./order";

export async function loadOrder(db: D1Database, id: string): Promise<Order | null> {
  return db.prepare("SELECT id, status, amount, version FROM orders WHERE id = ?").bind(id).first<Order>();
}

/**
 * POST /orders (`PlaceOrder` in the spec). The order and its OrderPlaced messages
 * commit in one batch, so a crash right after the commit loses nothing.
 */
export async function placeOrder(db: D1Database, id: string, amount: number): Promise<{ created: boolean; order: Order }> {
  const existing = await loadOrder(db, id);
  const result = place(existing, id, amount);
  if (result.events.length === 0) return { created: false, order: existing! };
  const order = result.order!;
  try {
    await db.batch([
      db
        .prepare("INSERT INTO orders (id, status, amount, version) VALUES (?, ?, ?, ?)")
        .bind(order.id, order.status, order.amount, order.version),
      ...outboxInserts(db, emit("OrderPlaced", id, { version: order.version, amount })),
    ]);
  } catch (e) {
    // the same order placed twice at the same time: the first insert won
    if (/UNIQUE constraint failed: orders\.id/.test(String(e))) return { created: false, order: (await loadOrder(db, id))! };
    throw e;
  }
  return { created: true, order };
}

/** ConfirmOrder and CancelOrder, from the saga (`Ordering(m)` in the spec). */
export async function handleOrdering(db: D1Database, msg: Message): Promise<Outcome> {
  if (msg.type !== "ConfirmOrder" && msg.type !== "CancelOrder") throw new Error(`ordering does not take ${msg.type}`);
  const command = msg.type;
  return handleOnce(db, msg, async () => {
    const order = await loadOrder(db, msg.orderId);
    if (!order) throw new Error(`no order ${msg.orderId}`);
    const result = handle(order, command);
    if (result.events.length === 0) return [];
    const next = result.order!;
    return [
      // the orders_version trigger rejects this save if the row moved on since we loaded it
      db.prepare("UPDATE orders SET status = ?, version = ? WHERE id = ?").bind(next.status, next.version, next.id),
      ...outboxInserts(db, result.events.flatMap((e) => emit(e, next.id, { version: next.version }))),
    ];
  });
}
