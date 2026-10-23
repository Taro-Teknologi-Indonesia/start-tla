import { cloudflareTest, readD1Migrations } from "@cloudflare/vitest-plugin";
import { defineConfig } from "vitest/config";

const services = ["ordering", "inventory", "payment", "projector", "notifier"] as const;

export default defineConfig(async () => {
  const migrations = Object.fromEntries(
    await Promise.all(services.map(async (s) => [s, await readD1Migrations(`./migrations/${s}`)] as const)),
  );
  const worker = (autoRelay: "on" | "off") =>
    cloudflareTest({
      wrangler: { configPath: "./wrangler.jsonc" },
      miniflare: { bindings: { AUTO_RELAY: autoRelay, TEST_MIGRATIONS: migrations } },
    });
  return {
    test: {
      projects: [
        {
          // The tests play the queue themselves (test/harness.ts), so nothing is published automatically.
          plugins: [worker("off")],
          test: { name: "spec", include: ["test/*.test.ts"], setupFiles: ["./test/apply-migrations.ts"] },
        },
        {
          // The real thing, locally: outboxes relay to Miniflare's queues, which call the consumer.
          plugins: [worker("on")],
          test: { name: "e2e", include: ["test/e2e/*.test.ts"], setupFiles: ["./test/apply-migrations.ts"] },
        },
      ],
    },
  };
});
