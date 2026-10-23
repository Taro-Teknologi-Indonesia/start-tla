/**
 * The Order aggregate: pure domain logic, `OrderHandle` in the spec.
 * A command returns the new state and the domain events it raised; no events
 * means the command does not apply in this state.
 */

export type OrderStatus = "placed" | "confirmed" | "cancelled";
export type OrderEvent = "OrderPlaced" | "OrderConfirmed" | "OrderCancelled";
export type OrderCommand = "PlaceOrder" | "ConfirmOrder" | "CancelOrder";

export interface Order {
  id: string;
  status: OrderStatus;
  amount: number;
  /** Bumped by every change; optimistic concurrency and the projector both use it. */
  version: number;
}

export interface OrderResult {
  order: Order | null;
  events: OrderEvent[];
}

function raise(order: Order, status: OrderStatus, event: OrderEvent): OrderResult {
  return { order: { ...order, status, version: order.version + 1 }, events: [event] };
}

export function place(existing: Order | null, id: string, amount: number): OrderResult {
  if (existing) return { order: existing, events: [] };
  if (!Number.isInteger(amount) || amount <= 0) throw new Error("amount must be a positive whole number of rupiah");
  return { order: { id, status: "placed", amount, version: 1 }, events: ["OrderPlaced"] };
}

export function handle(order: Order, command: Exclude<OrderCommand, "PlaceOrder">): OrderResult {
  if (order.status !== "placed") return { order, events: [] };
  return command === "ConfirmOrder"
    ? raise(order, "confirmed", "OrderConfirmed")
    : raise(order, "cancelled", "OrderCancelled");
}
