import { applyD1Migrations, type D1Migration } from "cloudflare:test";
import { env } from "cloudflare:workers";

const migrations = (env as unknown as { TEST_MIGRATIONS: Record<string, D1Migration[]> }).TEST_MIGRATIONS;
await applyD1Migrations(env.ORDERING_DB, migrations.ordering);
await applyD1Migrations(env.INVENTORY_DB, migrations.inventory);
await applyD1Migrations(env.PAYMENT_DB, migrations.payment);
await applyD1Migrations(env.PROJECTOR_DB, migrations.projector);
await applyD1Migrations(env.NOTIFIER_DB, migrations.notifier);
