import type { Message } from "../contract";
import { handleOnce, type Outcome } from "../lib/inbox";
import type { EmailProvider } from "./email";

/**
 * The event handler that emails the customer when an order is confirmed
 * (`NotifySend` then `NotifyDone` in the spec). The email goes out before the
 * inbox row commits; the key `confirmed:<order>` makes a repeat harmless.
 */
export async function handleNotifier(db: D1Database, email: EmailProvider, msg: Message): Promise<Outcome> {
  if (msg.type !== "OrderConfirmed") throw new Error(`notifier does not take ${msg.type}`);
  return handleOnce(db, msg, async () => {
    await email.send({
      key: `confirmed:${msg.orderId}`,
      orderId: msg.orderId,
      subject: `Pesanan ${msg.orderId} dikonfirmasi`,
      text: "Pembayaranmu sudah kami terima, dan pesananmu sedang disiapkan.",
    });
    return [];
  });
}
