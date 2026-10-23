/** The Worker's entry points: the HTTP API and the queue consumer. */
import { createExecutionContext, createMessageBatch, getQueueResult, waitOnExecutionContext } from "cloudflare:test";
import { env } from "cloudflare:workers";
import { beforeEach, describe, expect, it } from "vitest";
import { emit } from "../src/contract";
import worker from "../src/index";
import { Network, resetStock } from "./harness";

const post = (body: unknown) =>
  worker.fetch(new Request("http://shop/orders", { method: "POST", body: JSON.stringify(body) }), env, createExecutionContext());
const get = (id: string) => worker.fetch(new Request(`http://shop/orders/${id}`), env, createExecutionContext());

describe("HTTP API", () => {
  beforeEach(() => resetStock(1));

  it("POST /orders places an order once", async () => {
    const first = await post({ id: "w1", amount: 250_000 });
    expect(first.status).toBe(201);
    expect(await first.json()).toEqual({ id: "w1", status: "placed", amount: 250_000, version: 1 });
    expect((await post({ id: "w1", amount: 250_000 })).status).toBe(200); // a retried request
    expect((await post({ id: "w2" })).status).toBe(400);
  });

  it("GET /orders/:id shows the read model once the projector has caught up", async () => {
    await post({ id: "w3", amount: 250_000 });
    expect((await get("w3")).status).toBe(404); // nothing projected yet: eventually consistent
    const net = new Network();
    await net.settle(["w3"]);
    expect(await (await get("w3")).json()).toEqual({ orderId: "w3", status: "confirmed", version: 2 });
  });
});

describe("queue consumer", () => {
  it("acks what it handled and retries what failed", async () => {
    await post({ id: "w4", amount: 250_000 });
    const good = emit("OrderPlaced", "w4", { version: 1, amount: 250_000 }).find((m) => m.to === "saga")!;
    const bad = emit("ConfirmOrder", "no-such-order")[0]; // its handler throws
    const batch = createMessageBatch("shop-saga", [
      { id: "1", timestamp: new Date(), attempts: 1, body: good },
      { id: "2", timestamp: new Date(), attempts: 1, body: bad },
    ]);
    const ctx = createExecutionContext();
    await worker.queue(batch, env, ctx);
    await waitOnExecutionContext(ctx);
    const result = await getQueueResult(batch, ctx);
    expect(result.explicitAcks).toEqual(["1"]);
    expect(result.retryMessages.map((m) => m.msgId)).toEqual(["2"]);
  });
});
