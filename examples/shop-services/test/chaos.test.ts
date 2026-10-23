/**
 * Random behaviors of the whole system: three orders and one unit, relays that
 * lag, messages delivered in any order and sometimes twice, workers that crash
 * after committing, handlers running in parallel, timers firing whenever. The
 * invariants are checked after every step, the liveness properties at the end.
 * Each run is seeded, so a failure names a seed that reproduces it.
 */
import { env } from "cloudflare:workers";
import { describe, it } from "vitest";
import { placeOrder } from "../src/ordering/service";
import { Network, resetStock, type Source } from "./harness";
import { invariants, settledProperties } from "./properties";

/** mulberry32: a small seeded random number generator. */
function rng(seed: number): () => number {
  return () => {
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const RUNS = 30;
const STEPS = 60;

describe("chaos", () => {
  it.each(Array.from({ length: RUNS }, (_, i) => i + 1))("seed %i", async (seed) => {
    const random = rng(seed);
    const pick = <T>(xs: T[]): T => xs[Math.floor(random() * xs.length)];
    const orders = ["a", "b", "c"].map((x) => `${x}-chaos-${seed}`);
    await resetStock(1);
    const net = new Network();
    for (const o of orders) net.psp.answers.set(o, random() < 0.7);
    const placed: string[] = [];
    let crashes = 0;

    for (let step = 0; step < STEPS; step++) {
      const r = random();
      const unplaced = orders.filter((o) => !placed.includes(o));
      const inventory = net.inFlight.filter((m) => m.to === "inventory");
      if (r < 0.15 && unplaced.length > 0) {
        const o = pick(unplaced);
        await placeOrder(env.ORDERING_DB, o, 100_000);
        placed.push(o);
      } else if (r < 0.4) {
        const sources: Source[] = ["ordering", "inventory", "payment", ...placed.map((o) => ({ saga: o }))];
        await net.relayFrom(pick(sources));
      } else if (r < 0.75 && net.inFlight.length > 0) {
        const crash = crashes < 3 && random() < 0.15;
        if (crash) crashes++;
        await net.deliver(pick(net.inFlight), crash);
      } else if (r < 0.8 && inventory.length >= 2) {
        const a = pick(inventory);
        await net.deliverBoth(a, pick(inventory.filter((m) => m !== a)));
      } else if (r < 0.87 && net.delivered.length > 0) {
        net.redeliver(pick(net.delivered));
      } else if (r < 0.95 && placed.length > 0) {
        await net.timeout(pick(placed));
      } else if (placed.length > 0) {
        net.email.crashAfterSend.add(pick(placed));
      }
      await invariants(1, placed, net.email);
    }

    for (const o of orders.filter((o) => !placed.includes(o))) {
      await placeOrder(env.ORDERING_DB, o, 100_000);
      placed.push(o);
    }
    net.email.crashAfterSend.clear();
    await net.settle(placed, (n) => Math.floor(random() * n));
    await invariants(1, placed, net.email);
    await settledProperties(placed, net.email);
  });
});
