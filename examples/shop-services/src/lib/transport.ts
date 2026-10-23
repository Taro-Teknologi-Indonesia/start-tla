import type { Message, Receiver } from "../contract";
import type { Env } from "../env";

export interface Transport {
  send(messages: Message[]): Promise<void>;
}

/** Sends each message to its receiver's queue. Queues deliver at least once, in any order. */
export class QueueTransport implements Transport {
  constructor(private readonly env: Env) {}

  async send(messages: Message[]): Promise<void> {
    const byQueue = new Map<Receiver, Message[]>();
    for (const m of messages) byQueue.set(m.to, [...(byQueue.get(m.to) ?? []), m]);
    await Promise.all(
      [...byQueue].map(([to, ms]) => queueFor(this.env, to).sendBatch(ms.map((body) => ({ body })))),
    );
  }
}

export function queueFor(env: Env, to: Receiver): Queue<Message> {
  switch (to) {
    case "ordering":
      return env.ORDERING_QUEUE;
    case "inventory":
      return env.INVENTORY_QUEUE;
    case "payment":
      return env.PAYMENT_QUEUE;
    case "saga":
      return env.SAGA_QUEUE;
    case "projector":
      return env.PROJECTOR_QUEUE;
    case "notifier":
      return env.NOTIFIER_QUEUE;
  }
}
