import { emit, type Message } from "../contract";
import { handleOnce, type Outcome } from "../lib/inbox";
import { outboxInserts } from "../lib/outbox";
import { release, reserve, type Reservation, type Stock } from "./stock";

/** The one product on sale. */
export const SKU = "batik-tulis";

export async function loadStock(db: D1Database): Promise<Stock> {
  const stock = await db.prepare("SELECT sku, available, version FROM stock WHERE sku = ?").bind(SKU).first<Stock>();
  if (!stock) throw new Error(`no stock row for ${SKU}`);
  return stock;
}

/**
 * ReserveStock and ReleaseStock, from the saga (`InventoryLoad` and `InventorySave`
 * in the spec). Many orders share the Stock row and the queue runs handlers in
 * parallel, so the save carries the version we loaded ("version" in the spec).
 */
export async function handleInventory(db: D1Database, msg: Message): Promise<Outcome> {
  if (msg.type !== "ReserveStock" && msg.type !== "ReleaseStock") throw new Error(`inventory does not take ${msg.type}`);
  return handleOnce(db, msg, async () => {
    const stock = await loadStock(db);
    const row = await db
      .prepare("SELECT status FROM reservations WHERE order_id = ?")
      .bind(msg.orderId)
      .first<{ status: Reservation }>();
    const before = row?.status ?? null;
    const result = msg.type === "ReserveStock" ? reserve(stock) : release(stock, before);
    const writes: D1PreparedStatement[] = [];
    if (result.stock !== stock) {
      // the stock_version trigger rejects this save if another handler saved since our load
      writes.push(
        db
          .prepare("UPDATE stock SET available = ?, version = ? WHERE sku = ?")
          .bind(result.stock.available, result.stock.version, SKU),
      );
    } else {
      // Nothing to save, but the decision still rests on what we loaded: touch the row
      // only if its version moved, so that the trigger fails this batch too.
      writes.push(db.prepare("UPDATE stock SET version = version WHERE sku = ? AND version <> ?").bind(SKU, stock.version));
    }
    if (result.reservation !== before) {
      writes.push(
        db
          .prepare(
            "INSERT INTO reservations (order_id, status) VALUES (?, ?) ON CONFLICT(order_id) DO UPDATE SET status = excluded.status",
          )
          .bind(msg.orderId, result.reservation),
      );
    }
    writes.push(...outboxInserts(db, result.events.flatMap((e) => emit(e, msg.orderId))));
    return writes;
  });
}
