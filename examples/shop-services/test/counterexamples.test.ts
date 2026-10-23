/**
 * Every counterexample TLC found in the spec, replayed step by step against the
 * fixed code. Each test names the round and the fix that makes it pass.
 */
import { env } from "cloudflare:workers";
import { beforeEach, describe, expect, it } from "vitest";
import { handleInventory } from "../src/inventory/service";
import { loadOrder, placeOrder } from "../src/ordering/service";
import { getPayment } from "../src/payment/service";
import { getOrderView } from "../src/projector/service";
import { Gate, Network, resetStock } from "./harness";
import { invariants, settledProperties, stockConserved } from "./properties";

let n = 0;
/** Fresh order ids for every test, so tests never share a saga or a row. */
const ids = (...names: string[]) => names.map((x) => `${x}-${++n}`);

describe("the counterexamples TLC found", () => {
  beforeEach(() => resetStock(1));

  it("round 1: ReserveStock delivered again after a crash reserves nothing twice (inbox)", async () => {
    const [o1] = ids("o1");
    const net = new Network();
    await placeOrder(env.ORDERING_DB, o1, 100_000);
    await net.relayFrom("ordering");
    await net.deliverNext("OrderPlaced", o1, "saga");
    await net.relayFrom({ saga: o1 });
    await net.deliverNext("ReserveStock", o1, "inventory", true); // committed, then crashed before the ack
    expect(await net.deliverNext("ReserveStock", o1, "inventory")).toBe("duplicate");
    await stockConserved(1);
    await net.settle([o1]);
    await settledProperties([o1], net.email);
  });

  it("round 2: two orders reserving the last unit at once: one save fails and is retried (version)", async () => {
    const [o1, o2] = ids("o1", "o2");
    const net = new Network();
    for (const o of [o1, o2]) {
      await placeOrder(env.ORDERING_DB, o, 100_000);
      await net.relayFrom("ordering");
      await net.deliverNext("OrderPlaced", o, "saga");
      await net.relayFrom({ saga: o });
    }
    // Both handlers load the stock (1 unit, version v) before either saves.
    const g1 = new Gate(env.INVENTORY_DB);
    const g2 = new Gate(env.INVENTORY_DB);
    const save1 = handleInventory(g1.db, net.find("ReserveStock", o1));
    const save2 = handleInventory(g2.db, net.find("ReserveStock", o2));
    await Promise.all([g1.reached, g2.reached]);
    g1.open();
    expect(await save1).toBe("handled");
    g2.open();
    await expect(save2).rejects.toThrow(/version_conflict/);
    await stockConserved(1);
    // The queue retries o2's message: it loads again and finds no unit left.
    await net.settle([o1, o2]);
    expect((await loadOrder(env.ORDERING_DB, o2))?.status).toBe("cancelled");
    await stockConserved(1);
    await settledProperties([o1, o2], net.email);
  });

  it("round 3: an OrderPlaced that reaches the projector last does not undo the cancellation (skip_stale)", async () => {
    const [o1] = ids("o1");
    const net = new Network();
    await placeOrder(env.ORDERING_DB, o1, 100_000);
    await net.relayFrom("ordering");
    await net.deliverNext("OrderPlaced", o1, "saga");
    await net.relayFrom({ saga: o1 });
    await net.deliverNext("ReserveStock", o1);
    await net.relayFrom("inventory");
    await net.deliverNext("StockReserved", o1);
    await net.timeout(o1); // the payment never answered in time
    await net.relayFrom({ saga: o1 });
    await net.deliverNext("CancelOrder", o1);
    await net.relayFrom("ordering");
    await net.deliverNext("OrderCancelled", o1, "projector");
    await net.deliverNext("OrderPlaced", o1, "projector"); // the late copy
    expect(await getOrderView(env.PROJECTOR_DB, o1)).toEqual({ orderId: o1, status: "cancelled", version: 2 });
    await net.settle([o1]);
    await settledProperties([o1], net.email);
  });

  it("round 4: a notifier crash after the email went out sends no second email (email_key)", async () => {
    const [o1] = ids("o1");
    const net = new Network();
    await placeOrder(env.ORDERING_DB, o1, 100_000);
    for (const [type, to] of [
      ["OrderPlaced", "saga"],
      ["ReserveStock", "inventory"],
      ["StockReserved", "saga"],
      ["ChargePayment", "payment"],
      ["PaymentCaptured", "saga"],
      ["ConfirmOrder", "ordering"],
    ] as const) {
      await net.relayAll([o1]);
      await net.deliverNext(type, o1, to);
    }
    await net.relayAll([o1]);
    net.email.crashAfterSend.add(o1);
    expect(await net.deliverNext("OrderConfirmed", o1, "notifier")).toBe("failed"); // sent, then crashed
    expect(await net.deliverNext("OrderConfirmed", o1, "notifier")).toBe("handled"); // the queue retries
    expect(net.email.received.get(o1)).toBe(1);
    await net.settle([o1]);
    await settledProperties([o1], net.email);
  });

  it("round 5: StockReserved survives a crash right after inventory commits (outbox)", async () => {
    const [o1, o2] = ids("o1", "o2");
    const net = new Network();
    await placeOrder(env.ORDERING_DB, o1, 100_000);
    await net.relayFrom("ordering");
    await net.deliverNext("OrderPlaced", o1, "saga");
    await net.relayFrom({ saga: o1 });
    await placeOrder(env.ORDERING_DB, o2, 100_000);
    await net.deliverNext("ReserveStock", o1, "inventory", true); // committed, then crashed: no publish, no ack
    expect(await net.deliverNext("ReserveStock", o1, "inventory")).toBe("duplicate");
    // The StockReserved row is still in inventory's outbox; the next relay run publishes it.
    await net.relayFrom("inventory");
    expect(net.find("StockReserved", o1).to).toBe("saga");
    await net.settle([o1, o2]);
    expect((await loadOrder(env.ORDERING_DB, o1))?.status).toBe("confirmed");
    expect((await loadOrder(env.ORDERING_DB, o2))?.status).toBe("cancelled");
    await settledProperties([o1, o2], net.email);
  });

  it("round 6: a payment captured after the saga gave up is refunded (refund_late)", async () => {
    const [o1] = ids("o1");
    const net = new Network();
    await placeOrder(env.ORDERING_DB, o1, 100_000);
    for (const [type, to] of [
      ["OrderPlaced", "saga"],
      ["ReserveStock", "inventory"],
      ["StockReserved", "saga"],
      ["ChargePayment", "payment"], // the provider takes the money...
    ] as const) {
      await net.relayAll([o1]);
      await net.deliverNext(type, o1, to);
    }
    await net.relayAll([o1]);
    await net.timeout(o1); // ...but the saga's timer fires first
    await net.deliverNext("PaymentCaptured", o1); // the late answer
    await net.settle([o1]);
    expect(await getPayment(env.PAYMENT_DB, o1)).toBe("refunded");
    expect((await loadOrder(env.ORDERING_DB, o1))?.status).toBe("cancelled");
    await invariants(1, [o1], net.email);
    await settledProperties([o1], net.email);
  });
});
