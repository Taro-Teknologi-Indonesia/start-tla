import { emit, type Message } from "../contract";
import { handleOnce, type Outcome } from "../lib/inbox";
import { outboxInserts } from "../lib/outbox";
import { charge, refund, type PaymentResult, type PaymentStatus } from "./payment";
import type { Psp } from "./psp";

export async function getPayment(db: D1Database, orderId: string): Promise<PaymentStatus | null> {
  const row = await db.prepare("SELECT status FROM payments WHERE order_id = ?").bind(orderId).first<{ status: PaymentStatus }>();
  return row?.status ?? null;
}

/**
 * ChargePayment and RefundPayment, from the saga (`Payment(m, ok)` in the spec).
 * The spec asks the PSP and records the answer in one step. Here the PSP call
 * comes first and the commit second; the idempotency key covers the gap.
 */
export async function handlePayment(db: D1Database, psp: Psp, msg: Message): Promise<Outcome> {
  if (msg.type !== "ChargePayment" && msg.type !== "RefundPayment") throw new Error(`payment does not take ${msg.type}`);
  return handleOnce(db, msg, async () => {
    const current = await getPayment(db, msg.orderId);
    let result: PaymentResult;
    if (msg.type === "ChargePayment") {
      const ok = current === null ? await psp.charge({ key: `charge:${msg.orderId}`, amount: msg.amount ?? 0 }) : false;
      result = charge(current, ok);
    } else {
      if (current === "captured") await psp.refund({ key: `refund:${msg.orderId}`, chargeKey: `charge:${msg.orderId}` });
      result = refund(current);
    }
    if (result.status === current) return [];
    return [
      db
        .prepare(
          "INSERT INTO payments (order_id, status) VALUES (?, ?) ON CONFLICT(order_id) DO UPDATE SET status = excluded.status",
        )
        .bind(msg.orderId, result.status),
      ...outboxInserts(db, result.events.flatMap((e) => emit(e, msg.orderId))),
    ];
  });
}
