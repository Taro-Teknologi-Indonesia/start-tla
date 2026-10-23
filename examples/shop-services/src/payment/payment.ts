/**
 * The Payment aggregate: pure domain logic, `Charge` and `Refund` in the spec.
 * `ok` is the payment provider's answer.
 */

export type PaymentStatus = "captured" | "declined" | "refunded";

export interface PaymentResult {
  status: PaymentStatus | null;
  events: ("PaymentCaptured" | "PaymentDeclined" | "PaymentRefunded")[];
}

export function charge(current: PaymentStatus | null, ok: boolean): PaymentResult {
  if (current !== null) return { status: current, events: [] };
  return ok ? { status: "captured", events: ["PaymentCaptured"] } : { status: "declined", events: ["PaymentDeclined"] };
}

export function refund(current: PaymentStatus | null): PaymentResult {
  if (current !== "captured") return { status: current, events: [] };
  return { status: "refunded", events: ["PaymentRefunded"] }; // internal: nobody subscribes
}
