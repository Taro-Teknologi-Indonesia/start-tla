import type { Message } from "../contract";
import type { Transport } from "./transport";

/**
 * Outbox rows for messages, to add to the same batch as the state change ("outbox"
 * in the spec). If the worker dies after the commit, the rows are still there.
 */
export function outboxInserts(db: D1Database, messages: Message[]): D1PreparedStatement[] {
  return messages.map((m) =>
    db.prepare("INSERT OR IGNORE INTO outbox (id, body) VALUES (?, ?)").bind(m.id, JSON.stringify(m)),
  );
}

/**
 * The relay: publish pending rows, then delete them. A crash between the two
 * publishes a row again later; the receivers' inboxes absorb the duplicate.
 */
export async function relay(db: D1Database, transport: Transport, limit = 100): Promise<number> {
  const { results } = await db
    .prepare("SELECT id, body FROM outbox ORDER BY seq LIMIT ?")
    .bind(limit)
    .all<{ id: string; body: string }>();
  if (results.length === 0) return 0;
  await transport.send(results.map((r) => JSON.parse(r.body) as Message));
  await db.batch(results.map((r) => db.prepare("DELETE FROM outbox WHERE id = ?").bind(r.id)));
  return results.length;
}

/** The messages still waiting in an outbox, oldest first. Tests use it to play the queue. */
export async function pending(db: D1Database): Promise<Message[]> {
  const { results } = await db.prepare("SELECT body FROM outbox ORDER BY seq").all<{ body: string }>();
  return results.map((r) => JSON.parse(r.body) as Message);
}
