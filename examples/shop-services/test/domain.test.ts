/** The pure domain logic: aggregates, the saga's transitions, the contract. */
import { describe, expect, it } from "vitest";
import { emit, type Message, type MessageType } from "../src/contract";
import { release, reserve } from "../src/inventory/stock";
import { handle, place, type Order } from "../src/ordering/order";
import { charge, refund } from "../src/payment/payment";
import { onEvent, onPaymentTimeout, type SagaState } from "../src/saga/saga";

describe("contract", () => {
  it("gives a message one id per content, one message per receiver", () => {
    expect(emit("OrderPlaced", "o1", { version: 1, amount: 100 }).map((m) => m.id)).toEqual([
      "OrderPlaced:o1:saga",
      "OrderPlaced:o1:projector",
    ]);
    expect(emit("StockReleased", "o1")).toEqual([]); // a domain event that stays inside inventory
  });
});

describe("Order", () => {
  const placed: Order = { id: "o1", status: "placed", amount: 100, version: 1 };

  it("is placed once", () => {
    expect(place(null, "o1", 100)).toEqual({ order: placed, events: ["OrderPlaced"] });
    expect(place(placed, "o1", 100).events).toEqual([]);
  });

  it("is confirmed or cancelled only while placed, and each change bumps the version", () => {
    expect(handle(placed, "ConfirmOrder")).toEqual({
      order: { ...placed, status: "confirmed", version: 2 },
      events: ["OrderConfirmed"],
    });
    const cancelled = handle(placed, "CancelOrder").order!;
    expect(cancelled.version).toBe(2);
    expect(handle(cancelled, "ConfirmOrder").events).toEqual([]);
  });
});

describe("Stock", () => {
  it("reserves while units are left, and rejects after", () => {
    const one = { sku: "s", available: 1, version: 0 };
    const r = reserve(one);
    expect(r).toEqual({ stock: { sku: "s", available: 0, version: 1 }, reservation: "reserved", events: ["StockReserved"] });
    expect(reserve(r.stock)).toEqual({ stock: r.stock, reservation: "rejected", events: ["StockRejected"] });
  });

  it("releases only a reserved unit", () => {
    const none = { sku: "s", available: 0, version: 1 };
    expect(release(none, "reserved").stock.available).toBe(1);
    expect(release(none, "rejected")).toEqual({ stock: none, reservation: "rejected", events: [] });
  });
});

describe("Payment", () => {
  it("records the provider's first answer only", () => {
    expect(charge(null, true)).toEqual({ status: "captured", events: ["PaymentCaptured"] });
    expect(charge(null, false)).toEqual({ status: "declined", events: ["PaymentDeclined"] });
    expect(charge("captured", false)).toEqual({ status: "captured", events: [] });
    expect(refund("captured").status).toBe("refunded");
    expect(refund("declined").events).toEqual([]);
  });
});

describe("saga: every row of SagaOn", () => {
  const msg = (type: MessageType): Message => ({ id: `${type}:o1:saga`, type, orderId: "o1", version: 0, to: "saga", amount: 100 });
  const rows: [MessageType, SagaState, SagaState, string[]][] = [
    ["OrderPlaced", "none", "reserving", ["ReserveStock"]],
    ["StockReserved", "reserving", "charging", ["ChargePayment"]],
    ["StockRejected", "reserving", "cancelled", ["CancelOrder"]],
    ["PaymentCaptured", "charging", "done", ["ConfirmOrder"]],
    ["PaymentDeclined", "charging", "cancelled", ["ReleaseStock", "CancelOrder"]],
    ["PaymentCaptured", "cancelled", "cancelled", ["RefundPayment"]], // the late capture
    ["StockReserved", "charging", "charging", []], // anything else: ignored
    ["PaymentDeclined", "cancelled", "cancelled", []],
  ];
  it.each(rows)("%s while %s -> %s, sends %j", (type, from, next, commands) => {
    const step = onEvent({ orderId: "o1", state: from, amount: 100 }, msg(type));
    expect(step.saga.state).toBe(next);
    expect(step.commands.map((c) => c.type)).toEqual(commands);
  });

  it("gives up on a payment only while charging", () => {
    const step = onPaymentTimeout({ orderId: "o1", state: "charging", amount: 100 });
    expect([step.saga.state, step.commands.map((c) => c.type)]).toEqual(["cancelled", ["ReleaseStock", "CancelOrder"]]);
    expect(onPaymentTimeout({ orderId: "o1", state: "done", amount: 100 }).commands).toEqual([]);
  });
});
