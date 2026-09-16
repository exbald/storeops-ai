import test from "node:test";
import assert from "node:assert/strict";
import { StoreOpsClient, VersionConflictError } from "../src/lib/api-client.ts";
import { IS_TEST_DOUBLE } from "../src/lib/doubles.ts";

test("StoreOpsClient uses isolated test doubles by default in test mode", async () => {
  assert.equal(IS_TEST_DOUBLE, true);
  const client = new StoreOpsClient({ useDoubles: true });
  const stores = await client.listStores();
  assert.ok(stores.items.length >= 2);
  assert.equal(stores.items[0].code, "STR-001");
});

test("StoreOpsClient creates a store and increments list", async () => {
  const client = new StoreOpsClient({ useDoubles: true });
  const initial = await client.listStores();
  const created = await client.createStore({
    code: "STR-TEST-99",
    name: "Test Store",
    retailer: "FairPrice",
    region: "North",
    format: "SUPERMARKET",
    timezone: "Asia/Singapore",
  });
  assert.equal(created.code, "STR-TEST-99");
  assert.equal(created.version, 1);
  const after = await client.listStores();
  assert.equal(after.items.length, initial.items.length + 1);
});

test("StoreOpsClient detects version conflict on concurrent update", async () => {
  const client = new StoreOpsClient({ useDoubles: true });
  const stores = await client.listStores();
  const target = stores.items[0];

  await assert.rejects(
    async () => {
      // Pass wrong expected_version to simulate concurrent edit
      await client.updateStore(target.id, {
        expected_version: 9999,
        name: "Conflicted Name",
      });
    },
    (err: unknown) => {
      assert.ok(err instanceof VersionConflictError);
      assert.equal(err.status, 409);
      assert.equal(err.code, "VERSION_CONFLICT");
      return true;
    }
  );
});

test("StoreOpsClient stages and commits an import", async () => {
  const client = new StoreOpsClient({ useDoubles: true });
  const staged = await client.createImport({
    kind: "SALES",
    media_id: "00000000-0000-0000-0000-000000000055",
  });
  assert.equal(staged.status, "VALIDATED");
  assert.equal(staged.committed_at, null);

  const committed = await client.commitImport(staged.id);
  assert.equal(committed.status, "COMMITTED");
  assert.ok(committed.committed_at !== null);
  assert.ok(committed.batch_id !== null);
});
