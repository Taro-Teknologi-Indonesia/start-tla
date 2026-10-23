import type { Message } from "./contract";
import type { OrderSaga } from "./saga/durable-object";

export interface Env {
  // one D1 database per service: no service reads another's tables
  ORDERING_DB: D1Database;
  INVENTORY_DB: D1Database;
  PAYMENT_DB: D1Database;
  PROJECTOR_DB: D1Database;
  NOTIFIER_DB: D1Database;
  // one queue per receiver
  ORDERING_QUEUE: Queue<Message>;
  INVENTORY_QUEUE: Queue<Message>;
  PAYMENT_QUEUE: Queue<Message>;
  SAGA_QUEUE: Queue<Message>;
  PROJECTOR_QUEUE: Queue<Message>;
  NOTIFIER_QUEUE: Queue<Message>;
  // one saga per order
  ORDER_SAGA: DurableObjectNamespace<OrderSaga>;
  /** "on": publish outbox rows right after each commit. Tests switch it off and play the queue themselves. */
  AUTO_RELAY: string;
  PAYMENT_TIMEOUT_SECONDS: string;
  /** The fake payment provider declines charges above this many rupiah. */
  PSP_DECLINE_ABOVE: string;
}

// `import { env, exports } from "cloudflare:workers"` (and the test helpers) see this Env
// and this Worker's exports.
declare global {
  namespace Cloudflare {
    interface Env extends ShopEnv {}
    interface GlobalProps {
      mainModule: typeof import("./index");
      durableNamespaces: "OrderSaga";
    }
  }
}
type ShopEnv = Env;
