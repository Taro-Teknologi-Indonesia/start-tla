import type { Message } from "../contract";

export type Outcome = "handled" | "duplicate";

/**
 * Handle one message so that its effect happens at most once ("inbox" in the spec).
 * `decide` loads what it needs, runs the domain logic and returns the writes. They
 * commit in one D1 batch, which is one transaction, together with the inbox row for
 * this message and any outbox rows ("outbox"). A second delivery of the same message
 * is skipped here, or fails on the inbox's primary key, which rolls its batch back.
 * Any other failure, such as a version conflict ("version"), rolls back and throws,
 * so the queue retries the message later.
 */
export async function handleOnce(
  db: D1Database,
  msg: Message,
  decide: () => Promise<D1PreparedStatement[]>,
): Promise<Outcome> {
  if (await db.prepare("SELECT 1 FROM inbox WHERE message_id = ?").bind(msg.id).first()) return "duplicate";
  const writes = await decide();
  try {
    await db.batch([db.prepare("INSERT INTO inbox (message_id) VALUES (?)").bind(msg.id), ...writes]);
    return "handled";
  } catch (e) {
    if (isInboxDuplicate(e)) return "duplicate"; // a concurrent delivery of the same message won
    throw e;
  }
}

function isInboxDuplicate(e: unknown): boolean {
  return /UNIQUE constraint failed: inbox\.message_id/.test(String(e));
}

/** True when a write failed on a version trigger: another handler saved first. */
export function isVersionConflict(e: unknown): boolean {
  return /version_conflict/.test(String(e));
}
