/**
 * The integration contract between the services: which messages exist and who
 * receives each one. This is `Receivers(t)` and `Emit(t, o, v)` in ShopServices.tlaid.
 */

export type Receiver = "ordering" | "inventory" | "payment" | "saga" | "projector" | "notifier";

export const receivers = {
  // integration events
  OrderPlaced: ["saga", "projector"],
  OrderConfirmed: ["projector", "notifier"],
  OrderCancelled: ["projector"],
  StockReserved: ["saga"],
  StockRejected: ["saga"],
  PaymentCaptured: ["saga"],
  PaymentDeclined: ["saga"],
  // commands sent by the saga
  ReserveStock: ["inventory"],
  ReleaseStock: ["inventory"],
  ChargePayment: ["payment"],
  RefundPayment: ["payment"],
  ConfirmOrder: ["ordering"],
  CancelOrder: ["ordering"],
} as const satisfies Record<string, readonly Receiver[]>;

export type MessageType = keyof typeof receivers;

/** Domain events that no other service subscribes to; they never leave their service. */
export type InternalEvent = "StockReleased" | "PaymentRefunded";

export interface Message {
  /** Derived from the content, so a message sent twice has the same id. Inboxes deduplicate on it. */
  id: string;
  type: MessageType;
  orderId: string;
  /** The Order row's version, on events from ordering; 0 on everything else. */
  version: number;
  /** Rupiah, on OrderPlaced and ChargePayment. */
  amount?: number;
  to: Receiver;
}

/** The messages a service sends for one domain event or command: one per receiver. */
export function emit(
  type: MessageType | InternalEvent,
  orderId: string,
  extra: { version?: number; amount?: number } = {},
): Message[] {
  if (!(type in receivers)) return []; // an internal domain event
  const t = type as MessageType;
  return receivers[t].map((to) => ({
    id: `${t}:${orderId}:${to}`,
    type: t,
    orderId,
    version: extra.version ?? 0,
    ...(extra.amount === undefined ? {} : { amount: extra.amount }),
    to,
  }));
}
