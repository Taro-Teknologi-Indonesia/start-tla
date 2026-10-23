import { DurableObject } from "cloudflare:workers";
import type { Message } from "../contract";
import type { Env } from "../env";
import type { Outcome } from "../lib/inbox";
import { QueueTransport } from "../lib/transport";
import { onEvent, onPaymentTimeout, type Saga, type SagaState, type Step } from "./saga";

const RETRY_RELAY_MS = 10_000;

/**
 * One saga per order. Its SQLite storage holds the saga's state, an inbox and an
 * outbox, and a transition commits all three in one transaction. The alarm is the
 * payment timer, and it also retries an outbox that could not be published.
 */
export class OrderSaga extends DurableObject<Env> {
  private readonly sql: SqlStorage;

  constructor(ctx: DurableObjectState, env: Env) {
    super(ctx, env);
    this.sql = ctx.storage.sql;
    this.sql.exec(`
      CREATE TABLE IF NOT EXISTS saga (order_id TEXT PRIMARY KEY, state TEXT NOT NULL, amount INTEGER NOT NULL,
                                       deadline INTEGER);
      CREATE TABLE IF NOT EXISTS inbox (message_id TEXT PRIMARY KEY);
      CREATE TABLE IF NOT EXISTS outbox (seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT NOT NULL UNIQUE,
                                         body TEXT NOT NULL);`);
  }

  /** Handle one event for this order's saga (`Saga(m)` in the spec). */
  async handle(msg: Message): Promise<Outcome> {
    const outcome = this.ctx.storage.transactionSync((): Outcome => {
      if (this.sql.exec("SELECT 1 FROM inbox WHERE message_id = ?", msg.id).toArray().length > 0) return "duplicate";
      this.sql.exec("INSERT INTO inbox (message_id) VALUES (?)", msg.id);
      this.commit(onEvent(this.current() ?? { orderId: msg.orderId, state: "none", amount: 0 }, msg));
      return "handled";
    });
    await this.afterCommit();
    return outcome;
  }

  /** The payment timer (`PaymentTimeout(o)` in the spec). Runs from alarm(), and from tests. */
  async paymentTimeout(): Promise<void> {
    this.ctx.storage.transactionSync(() => {
      const saga = this.current();
      if (saga) this.commit(onPaymentTimeout(saga));
    });
    await this.afterCommit();
  }

  async alarm(): Promise<void> {
    const saga = this.current();
    const deadline = this.deadline();
    if (saga?.state === "charging" && deadline !== null && Date.now() >= deadline) await this.paymentTimeout();
    else await this.afterCommit();
  }

  async state(): Promise<Saga | null> {
    return this.current();
  }

  /** Messages committed but not yet published. Tests use these two methods to play the queue. */
  async pendingOutbox(): Promise<Message[]> {
    return this.sql
      .exec<{ body: string }>("SELECT body FROM outbox ORDER BY seq")
      .toArray()
      .map((r) => JSON.parse(r.body) as Message);
  }

  async ackOutbox(ids: string[]): Promise<void> {
    for (const id of ids) this.sql.exec("DELETE FROM outbox WHERE id = ?", id);
  }

  private current(): Saga | null {
    const rows = this.sql
      .exec<{ order_id: string; state: SagaState; amount: number }>("SELECT order_id, state, amount FROM saga")
      .toArray();
    return rows.length === 0 ? null : { orderId: rows[0].order_id, state: rows[0].state, amount: rows[0].amount };
  }

  private deadline(): number | null {
    const rows = this.sql.exec<{ deadline: number | null }>("SELECT deadline FROM saga").toArray();
    return rows[0]?.deadline ?? null;
  }

  /** Inside the transaction: the new state, its deadline, and the commands as outbox rows. */
  private commit(step: Step): void {
    const before = this.current();
    const s = step.saga;
    const deadline =
      s.state === "charging"
        ? before?.state === "charging"
          ? this.deadline()
          : Date.now() + Number(this.env.PAYMENT_TIMEOUT_SECONDS) * 1000
        : null;
    this.sql.exec(
      `INSERT INTO saga (order_id, state, amount, deadline) VALUES (?, ?, ?, ?)
       ON CONFLICT(order_id) DO UPDATE SET state = excluded.state, amount = excluded.amount, deadline = excluded.deadline`,
      s.orderId,
      s.state,
      s.amount,
      deadline,
    );
    for (const m of step.commands) {
      this.sql.exec("INSERT OR IGNORE INTO outbox (id, body) VALUES (?, ?)", m.id, JSON.stringify(m));
    }
  }

  /** After the commit: publish the outbox, then set the alarm for whatever is still to come. */
  private async afterCommit(): Promise<void> {
    if (this.env.AUTO_RELAY === "on") {
      try {
        const pending = await this.pendingOutbox();
        if (pending.length > 0) {
          await new QueueTransport(this.env).send(pending);
          await this.ackOutbox(pending.map((m) => m.id));
        }
      } catch (e) {
        console.error("saga outbox not published yet:", String(e)); // the alarm retries
      }
    }
    const times: number[] = [];
    const deadline = this.deadline();
    if (this.current()?.state === "charging" && deadline !== null) times.push(deadline);
    if (this.env.AUTO_RELAY === "on" && (await this.pendingOutbox()).length > 0) times.push(Date.now() + RETRY_RELAY_MS);
    if (times.length > 0) await this.ctx.storage.setAlarm(Math.min(...times));
    else await this.ctx.storage.deleteAlarm();
  }
}
