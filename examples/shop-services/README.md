# shop-services

The code for Bab 21 of the TLA-ID field guide: an online shop as microservices,
DDD without event sourcing, with domain events, integration events through
queues, an event handler, a projector and a saga. The design was model-checked
first, in `specs/ShopServices.tlaid` at the root of this repository; every fix
TLC led to is in this code, and the tests replay TLC's counterexamples.

| Service   | Aggregate or role                    | Storage             | Spec action(s)                   |
| --------- | ------------------------------------ | ------------------- | -------------------------------- |
| ordering  | Order (placed, confirmed, cancelled) | D1 `shop-ordering`  | `PlaceOrder`, `Ordering`         |
| inventory | Stock (one row, shared by orders)    | D1 `shop-inventory` | `InventoryLoad`, `InventorySave` |
| payment   | Payment, plus the payment provider   | D1 `shop-payment`   | `Payment`                        |
| saga      | process manager, one per order       | Durable Object      | `Saga`, `PaymentTimeout`         |
| projector | "my orders" read model               | D1 `shop-projector` | `Projector`                      |
| notifier  | event handler: confirmation email    | D1 `shop-notifier`  | `NotifySend`, `NotifyDone`       |

The six services run in one Worker to keep the example easy to start. Each has
its own database and its own queue, and none reads another's database, so
splitting them into separate Workers is only configuration.

## The fixes, and where they live

| Fix in the spec | In the code |
| --- | --- |
| `inbox` | `src/lib/inbox.ts`: the message id commits in the same D1 batch as the change |
| `version` | the `*_version` triggers in `migrations/`, and the guard in `src/inventory/service.ts` |
| `skip_stale` | the `WHERE excluded.version > order_view.version` in `src/projector/service.ts` |
| `email_key` | the key `confirmed:<order>` in `src/notifier/service.ts` (and `charge:<order>` in payment) |
| `outbox` | `src/lib/outbox.ts`, and the saga's outbox in `src/saga/durable-object.ts` |
| `refund_late` | the `PaymentCaptured/cancelled` case in `src/saga/saga.ts` |

## Run the tests

Node.js 22 or later:

```sh
npm install
npm test            # 54 tests from the spec, plus one end-to-end run through local queues
npm run typecheck
```

The tests run inside the local Workers runtime with real D1 databases and
Durable Objects. `test/harness.ts` plays the queue the way TLC does: it takes
committed messages out of the outboxes and delivers them in any order, twice,
or after a crash. `test/e2e/` instead lets the outboxes publish to Miniflare's
queues.

## Run it locally

```sh
for s in ordering inventory payment projector notifier; do
  npx wrangler d1 migrations apply shop-$s --local
done
npx wrangler dev
```

From another terminal:

```sh
curl -X POST http://localhost:8787/orders -d '{"id":"o1","amount":250000}'
curl -X POST http://localhost:8787/orders -d '{"id":"o2","amount":250000}'
curl http://localhost:8787/orders/o1
curl http://localhost:8787/orders/o2
```

A few seconds later one order is `"confirmed"` and the other `"cancelled"`:
there was one unit. Which one wins depends on the order the local queues
deliver in. `wrangler dev` does not run the cron trigger on its own; open
`http://localhost:8787/cdn-cgi/local/scheduled` to run the relay by hand.

The fake payment provider declines amounts above `PSP_DECLINE_ABOVE`, and the
notifier prints its email to the console.

## Deploy

1. `npx wrangler d1 create shop-<service>` for the five databases, and copy each `database_id` into `wrangler.jsonc`.
2. `npx wrangler queues create shop-<receiver>` for the six queues, plus `shop-dead-letters`.
3. Apply the migrations with `--remote` instead of `--local`.
4. Replace `FakePsp` and `ConsoleEmail` with clients for your providers that pass the idempotency key through.
5. `npx wrangler deploy`.

A message that keeps failing goes to `shop-dead-letters` after `max_retries`.
Without a dead-letter queue, Cloudflare Queues deletes it, and the spec's
"delivered at least once" would no longer hold.
