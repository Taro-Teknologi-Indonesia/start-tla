/**
 * The order saga (process manager): `SagaOn` and `PaymentTimeout` in the spec.
 * Pure: given the saga's state and an event, the next state and the commands to send.
 */
import { emit, type Message } from "../contract";

export type SagaState = "none" | "reserving" | "charging" | "done" | "cancelled";

export interface Saga {
  orderId: string;
  state: SagaState;
  amount: number;
}

export interface Step {
  saga: Saga;
  commands: Message[];
}

const to = (saga: Saga, state: SagaState, commands: Message[]): Step => ({ saga: { ...saga, state }, commands });

/** React to an event. One the saga does not expect in its current state is ignored. */
export function onEvent(saga: Saga, msg: Message): Step {
  const o = saga.orderId;
  switch (`${msg.type}/${saga.state}`) {
    case "OrderPlaced/none":
      return to({ ...saga, amount: msg.amount ?? 0 }, "reserving", emit("ReserveStock", o));
    case "StockReserved/reserving":
      return to(saga, "charging", emit("ChargePayment", o, { amount: saga.amount }));
    case "StockRejected/reserving":
      return to(saga, "cancelled", emit("CancelOrder", o));
    case "PaymentCaptured/charging":
      return to(saga, "done", emit("ConfirmOrder", o));
    case "PaymentDeclined/charging":
      return to(saga, "cancelled", [...emit("ReleaseStock", o), ...emit("CancelOrder", o)]);
    case "PaymentCaptured/cancelled":
      // We gave up on the payment, but the provider took the money after all: give it back.
      return to(saga, "cancelled", emit("RefundPayment", o));
    default:
      return { saga, commands: [] };
  }
}

/** The payment timer fired and there is still no answer: give up and compensate. */
export function onPaymentTimeout(saga: Saga): Step {
  if (saga.state !== "charging") return { saga, commands: [] };
  return to(saga, "cancelled", [...emit("ReleaseStock", saga.orderId), ...emit("CancelOrder", saga.orderId)]);
}
