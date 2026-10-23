/** Two orders for the last unit, through the real queues: one is confirmed, one cancelled. */
import { exports } from "cloudflare:workers";
import { expect, it } from "vitest";

async function waitForStatus(id: string, statuses: string[]): Promise<{ status: string; version: number }> {
  for (let i = 0; i < 200; i++) {
    const res = await exports.default.fetch(`http://shop/orders/${id}`);
    if (res.status === 200) {
      const view = await res.json<{ status: string; version: number }>();
      if (statuses.includes(view.status)) return view;
    }
    await new Promise((r) => setTimeout(r, 100));
  }
  throw new Error(`${id} never reached ${statuses.join(" or ")}`);
}

it("runs the whole saga through the queues", async () => {
  for (const id of ["e1", "e2"]) {
    const res = await exports.default.fetch("http://shop/orders", {
      method: "POST",
      body: JSON.stringify({ id, amount: 250_000 }),
    });
    expect(res.status).toBe(201);
  }
  const final = await Promise.all(["e1", "e2"].map((id) => waitForStatus(id, ["confirmed", "cancelled"])));
  expect(final.map((v) => v.status).sort()).toEqual(["cancelled", "confirmed"]);
}, 30_000);
