/**
 * Six services in one Worker, to keep the example easy to run. Each service has
 * its own D1 database and its own queue, and none reads another's database, so
 * splitting them into separate Workers is only configuration.
 */
import type { Message } from "./contract";
import type { Env } from "./env";
import { handleInventory } from "./inventory/service";
import type { Outcome } from "./lib/inbox";
import { relay } from "./lib/outbox";
import { QueueTransport } from "./lib/transport";
import { ConsoleEmail, type EmailProvider } from "./notifier/email";
import { handleNotifier } from "./notifier/service";
import { handleOrdering, placeOrder } from "./ordering/service";
import { FakePsp, type Psp } from "./payment/psp";
import { handlePayment } from "./payment/service";
import { getOrderView, handleProjector } from "./projector/service";

export { OrderSaga } from "./saga/durable-object";

/** The outside systems: a payment provider and an email provider. */
export interface Deps {
  psp: Psp;
  email: EmailProvider;
}

export function defaultDeps(env: Env): Deps {
  return { psp: new FakePsp(Number(env.PSP_DECLINE_ABOVE)), email: new ConsoleEmail() };
}

export function sagaFor(env: Env, orderId: string) {
  return env.ORDER_SAGA.get(env.ORDER_SAGA.idFromName(orderId));
}

/** Hand one message to the service it is addressed to. */
export async function deliver(env: Env, msg: Message, deps: Deps = defaultDeps(env)): Promise<Outcome> {
  switch (msg.to) {
    case "ordering":
      return handleOrdering(env.ORDERING_DB, msg);
    case "inventory":
      return handleInventory(env.INVENTORY_DB, msg);
    case "payment":
      return handlePayment(env.PAYMENT_DB, deps.psp, msg);
    case "saga":
      return sagaFor(env, msg.orderId).handle(msg);
    case "projector":
      return handleProjector(env.PROJECTOR_DB, msg);
    case "notifier":
      return handleNotifier(env.NOTIFIER_DB, deps.email, msg);
  }
}

/** Publish every D1 outbox. The sagas publish their own after each commit, and on their alarm. */
export async function relayAll(env: Env): Promise<void> {
  const transport = new QueueTransport(env);
  for (const db of [env.ORDERING_DB, env.INVENTORY_DB, env.PAYMENT_DB]) {
    while ((await relay(db, transport)) > 0) {}
  }
}

export default {
  async fetch(request, env, ctx): Promise<Response> {
    const url = new URL(request.url);
    if (request.method === "POST" && url.pathname === "/orders") {
      const body = await request.json<{ id?: unknown; amount?: unknown }>().catch(() => ({}) as { id?: unknown; amount?: unknown });
      if (typeof body.id !== "string" || !/^[\w-]{1,64}$/.test(body.id) || typeof body.amount !== "number") {
        return Response.json({ error: 'expected {"id": "<order id>", "amount": <rupiah>}' }, { status: 400 });
      }
      try {
        const { created, order } = await placeOrder(env.ORDERING_DB, body.id, body.amount);
        if (env.AUTO_RELAY === "on") ctx.waitUntil(relay(env.ORDERING_DB, new QueueTransport(env)));
        return Response.json(order, { status: created ? 201 : 200 });
      } catch (e) {
        return Response.json({ error: String(e) }, { status: 400 });
      }
    }
    const match = url.pathname.match(/^\/orders\/([\w-]{1,64})$/);
    if (request.method === "GET" && match) {
      const view = await getOrderView(env.PROJECTOR_DB, match[1]);
      return view ? Response.json(view) : Response.json({ error: "not found" }, { status: 404 });
    }
    return Response.json({ error: "not found" }, { status: 404 });
  },

  /** Every queue has this Worker as its consumer. A message that fails is retried later. */
  async queue(batch, env, ctx): Promise<void> {
    for (const m of batch.messages) {
      try {
        await deliver(env, m.body);
        m.ack();
      } catch (e) {
        console.error(`retrying ${m.body.id}:`, String(e)); // e.g. a version conflict: load again next time
        m.retry({ delaySeconds: 2 });
      }
    }
    if (env.AUTO_RELAY === "on") ctx.waitUntil(relayAll(env));
  },

  /** Every minute: publish rows left behind by a worker that died between commit and publish. */
  async scheduled(_controller, env, ctx): Promise<void> {
    ctx.waitUntil(relayAll(env));
  },
} satisfies ExportedHandler<Env, Message>;
