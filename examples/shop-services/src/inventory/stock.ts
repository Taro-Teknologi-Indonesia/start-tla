/**
 * The Stock aggregate: one row per product, shared by every order. Pure domain
 * logic, `Reserve` and `Release` in the spec.
 */

export type Reservation = "reserved" | "rejected" | "released";

export interface Stock {
  sku: string;
  available: number;
  version: number;
}

export interface StockResult {
  stock: Stock;
  reservation: Reservation | null;
  events: ("StockReserved" | "StockRejected" | "StockReleased")[];
}

export function reserve(stock: Stock): StockResult {
  if (stock.available > 0) {
    return {
      stock: { ...stock, available: stock.available - 1, version: stock.version + 1 },
      reservation: "reserved",
      events: ["StockReserved"],
    };
  }
  return { stock, reservation: "rejected", events: ["StockRejected"] };
}

export function release(stock: Stock, reservation: Reservation | null): StockResult {
  if (reservation !== "reserved") return { stock, reservation, events: [] };
  return {
    stock: { ...stock, available: stock.available + 1, version: stock.version + 1 },
    reservation: "released",
    events: ["StockReleased"], // a domain event; no other service subscribes to it
  };
}
