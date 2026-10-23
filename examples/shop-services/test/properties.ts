/**
 * The spec's properties, with the same names, checked against the real databases.
 * Invariants hold after every step; the liveness properties are checked once
 * everything has been delivered (Network.settle), which is when they must hold.
 */
import { env } from "cloudflare:workers";
import { expect } from "vitest";
import { sagaFor } from "../src/index";
import { loadStock } from "../src/inventory/service";
import { loadOrder } from "../src/ordering/service";
import { getPayment } from "../src/payment/service";
import { getOrderView } from "../src/projector/service";
import type { TestEmail } from "./harness";

async function reservation(orderId: string): Promise<string | null> {
  const row = await env.INVENTORY_DB.prepare("SELECT status FROM reservations WHERE order_id = ?")
    .bind(orderId)
    .first<{ status: string }>();
  return row?.status ?? null;
}

// ---- safety ----

export async function stockConserved(units: number): Promise<void> {
  const { available } = await loadStock(env.INVENTORY_DB);
  const held = await env.INVENTORY_DB.prepare("SELECT count(*) AS n FROM reservations WHERE status = 'reserved'").first<{
    n: number;
  }>();
  expect(available + held!.n, "StockConserved").toBe(units);
}

export async function confirmedMeansPaid(orderIds: string[]): Promise<void> {
  for (const o of orderIds) {
    if ((await loadOrder(env.ORDERING_DB, o))?.status !== "confirmed") continue;
    expect(await getPayment(env.PAYMENT_DB, o), `ConfirmedMeansPaid ${o}`).toBe("captured");
    expect(await reservation(o), `ConfirmedMeansPaid ${o}`).toBe("reserved");
  }
}

export function atMostOneEmail(email: TestEmail): void {
  for (const [o, n] of email.received) expect(n, `AtMostOneEmail ${o}`).toBeLessThanOrEqual(1);
}

export async function invariants(units: number, orderIds: string[], email: TestEmail): Promise<void> {
  await stockConserved(units);
  await confirmedMeansPaid(orderIds);
  atMostOneEmail(email);
}

// ---- liveness, once everything has settled ----

export async function settledProperties(orderIds: string[], email: TestEmail): Promise<void> {
  for (const o of orderIds) {
    const order = await loadOrder(env.ORDERING_DB, o);
    if (!order) continue;
    const payment = await getPayment(env.PAYMENT_DB, o);
    expect(["confirmed", "cancelled"], `OrderCompletes ${o}`).toContain(order.status);
    if (payment === "captured") expect(order.status, `NoMoneyWithoutGoods ${o}`).toBe("confirmed");
    if (order.status === "cancelled") expect(await reservation(o), `CancelledReleasesStock ${o}`).not.toBe("reserved");
    expect((await getOrderView(env.PROJECTOR_DB, o))?.status, `ViewCatchesUp ${o}`).toBe(order.status);
    if (order.status === "confirmed") expect(email.received.get(o), `CustomerEmailed ${o}`).toBe(1);
    expect(["done", "cancelled"], `saga of ${o} finished`).toContain((await sagaFor(env, o).state())?.state);
  }
}
