/**
 * The tests play the queue themselves, the way TLC does in the spec: they take
 * committed messages out of the outboxes and deliver them in any order, deliver
 * some twice, crash workers after a commit, and fire saga timers when they like.
 */
import { env } from "cloudflare:workers";
import type { Message, MessageType, Receiver } from "../src/contract";
import { deliver, sagaFor, type Deps } from "../src/index";
import { SKU } from "../src/inventory/service";
import type { Outcome } from "../src/lib/inbox";
import { pending } from "../src/lib/outbox";
import type { EmailProvider } from "../src/notifier/email";
import type { Psp } from "../src/payment/psp";
import { getOrderView } from "../src/projector/service";

/** A payment provider that answers per order, and remembers each key's answer as a real one does. */
export class TestPsp implements Psp {
  readonly answers = new Map<string, boolean>(); // orderId -> captured?
  readonly charges = new Map<string, boolean>(); // key -> answer given
  readonly refunds = new Set<string>();

  async charge(req: { key: string; amount: number }): Promise<boolean> {
    if (!this.charges.has(req.key)) this.charges.set(req.key, this.answers.get(req.key.slice("charge:".length)) ?? true);
    return this.charges.get(req.key)!;
  }

  async refund(req: { key: string; chargeKey: string }): Promise<void> {
    this.refunds.add(req.key);
  }
}

/** An email provider that sends at most one email per idempotency key, as real providers do. */
export class TestEmail implements EmailProvider {
  readonly received = new Map<string, number>(); // orderId -> emails the customer got
  readonly keys = new Set<string>();
  /** Orders whose next send succeeds at the provider and then "crashes" our worker. */
  readonly crashAfterSend = new Set<string>();

  async send(email: { key: string; orderId: string }): Promise<void> {
    if (!this.keys.has(email.key)) {
      this.keys.add(email.key);
      this.received.set(email.orderId, (this.received.get(email.orderId) ?? 0) + 1);
    }
    if (this.crashAfterSend.delete(email.orderId)) throw new Error("worker crashed after calling the email provider");
  }
}

export type Source = "ordering" | "inventory" | "payment" | { saga: string };

export class Network {
  /** Messages published and not yet acked: the queues' contents. */
  inFlight: Message[] = [];
  /** Every message some handler finished. */
  readonly delivered: Message[] = [];
  readonly psp = new TestPsp();
  readonly email = new TestEmail();
  readonly deps: Deps = { psp: this.psp, email: this.email };
  /** The newest view version seen per order, to check ViewNeverGoesBack after every step. */
  readonly viewVersions = new Map<string, number>();

  /** The relay: move committed outbox rows onto the queues. */
  async relayFrom(source: Source): Promise<void> {
    if (typeof source === "object") {
      const saga = sagaFor(env, source.saga);
      const ms = await saga.pendingOutbox();
      this.inFlight.push(...ms);
      await saga.ackOutbox(ms.map((m) => m.id));
      return;
    }
    const db = { ordering: env.ORDERING_DB, inventory: env.INVENTORY_DB, payment: env.PAYMENT_DB }[source];
    const ms = await pending(db);
    if (ms.length === 0) return;
    this.inFlight.push(...ms);
    await db.batch(ms.map((m) => db.prepare("DELETE FROM outbox WHERE id = ?").bind(m.id)));
  }

  async relayAll(orderIds: string[]): Promise<void> {
    for (const s of ["ordering", "inventory", "payment"] as const) await this.relayFrom(s);
    for (const o of orderIds) await this.relayFrom({ saga: o });
  }

  find(type: MessageType, orderId: string, to?: Receiver): Message {
    const m = this.inFlight.find((x) => x.type === type && x.orderId === orderId && (to === undefined || x.to === to));
    if (!m) throw new Error(`no ${type} for ${orderId}${to ? ` to ${to}` : ""} in flight`);
    return m;
  }

  /**
   * Deliver one message. The queue acks it if the handler returns, and keeps it
   * for a retry if the handler throws. crashAfterCommit: the worker dies after
   * its transaction commits but before the ack, so the message comes again.
   */
  async deliver(m: Message, crashAfterCommit = false): Promise<Outcome | "failed"> {
    let outcome: Outcome | "failed";
    try {
      outcome = await deliver(env, m, this.deps);
    } catch {
      outcome = "failed";
    }
    if (outcome !== "failed" && !crashAfterCommit) this.inFlight.splice(this.inFlight.indexOf(m), 1);
    if (outcome !== "failed") this.delivered.push(m);
    if (m.to === "projector") await this.checkView(m.orderId);
    return outcome;
  }

  /** Two handlers running at the same time, as a queue consumer does with a batch. */
  async deliverBoth(a: Message, b: Message): Promise<void> {
    await Promise.all([this.deliver(a), this.deliver(b)]);
  }

  /** The queue delivers an already acked message once more: at least once means it may. */
  redeliver(m: Message): void {
    this.inFlight.push(m);
  }

  async deliverNext(type: MessageType, orderId: string, to?: Receiver, crashAfterCommit = false) {
    return this.deliver(this.find(type, orderId, to), crashAfterCommit);
  }

  /** The saga's payment timer fires. */
  async timeout(orderId: string): Promise<void> {
    await sagaFor(env, orderId).paymentTimeout();
  }

  /** Relay and deliver until nothing is left: the fair part of every behavior. */
  async settle(orderIds: string[], pick: (n: number) => number = () => 0): Promise<void> {
    for (let i = 0; i < 1000; i++) {
      await this.relayAll(orderIds);
      if (this.inFlight.length === 0) return;
      await this.deliver(this.inFlight[pick(this.inFlight.length)]);
    }
    throw new Error("did not settle");
  }

  private async checkView(orderId: string): Promise<void> {
    const v = (await getOrderView(env.PROJECTOR_DB, orderId))?.version ?? 0;
    const before = this.viewVersions.get(orderId) ?? 0;
    if (v < before) throw new Error(`ViewNeverGoesBack: ${orderId} went from version ${before} to ${v}`);
    this.viewVersions.set(orderId, v);
  }
}

/** Put `units` on the shelf and forget earlier reservations. */
export async function resetStock(units: number): Promise<void> {
  await env.INVENTORY_DB.batch([
    env.INVENTORY_DB.prepare("DELETE FROM reservations"),
    env.INVENTORY_DB.prepare("UPDATE stock SET available = ?, version = version + 1 WHERE sku = ?").bind(units, SKU),
  ]);
}

/**
 * Holds a handler between its load and its save: `db` lets every read through
 * but stops at batch() until open() is called. `reached` resolves when it stops.
 */
export class Gate {
  private release!: () => void;
  private arrived!: () => void;
  private readonly opened = new Promise<void>((r) => (this.release = r));
  readonly reached = new Promise<void>((r) => (this.arrived = r));
  readonly db: D1Database;

  constructor(real: D1Database) {
    this.db = new Proxy(real, {
      get: (target, prop) => {
        if (prop === "batch") {
          return async (statements: D1PreparedStatement[]) => {
            this.arrived();
            await this.opened;
            return target.batch(statements);
          };
        }
        const value = Reflect.get(target, prop);
        return typeof value === "function" ? value.bind(target) : value;
      },
    });
  }

  open(): void {
    this.release();
  }
}
