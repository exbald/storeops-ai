/**
 * Live HTTP Wire Integration Test for StoreOpsClient (AC40).
 *
 * Verifies StoreOpsClient running in LIVE mode (useDoubles: false)
 * over real network sockets via Node.js HTTP server:
 * 1. Wire headers: Sends Bearer token, X-Workspace-Id, and auto-generated RFC4122 Idempotency-Key on POST.
 * 2. Real entity deserialization: Correctly decodes JSON responses over live HTTP.
 * 3. Real 409 OCC mapping: Maps HTTP 409 JSON body into typed VersionConflictError.
 * 4. Fail-closed authentication: Throws UNAUTHENTICATED error when token is missing on protected routes.
 */

import test from "node:test";
import assert from "node:assert/strict";
import http from "node:http";
import { StoreOpsClient, VersionConflictError, ApiRequestError } from "../src/lib/api-client";

const TEST_WORKSPACE = "00000000-0000-0000-0000-000000000001";
const TEST_TOKEN = "test-live-session-bearer-token";

test("StoreOpsClient in live mode (non-double) executes requests over real HTTP sockets", async () => {
  let receivedHeaders: Record<string, string | string[] | undefined> = {};
  let receivedMethod = "";
  let receivedUrl = "";

  const server = http.createServer((req, res) => {
    receivedHeaders = req.headers;
    receivedMethod = req.method || "";
    receivedUrl = req.url || "";

    if (req.url === "/stores/str-001" && req.method === "GET") {
      res.writeHead(200, { "Content-Type": "application/json" });
      res.end(
        JSON.stringify({
          id: "str-001",
          workspace_id: TEST_WORKSPACE,
          version: 1,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          code: "STR-001",
          name: "Live Test Store",
          retailer: "FairPrice",
          region: "Central",
          format: "SUPERMARKET",
          timezone: "Asia/Singapore",
          distributor_location_id: null,
        })
      );
      return;
    }

    if (req.url === "/visits" && req.method === "POST") {
      res.writeHead(201, { "Content-Type": "application/json" });
      res.end(
        JSON.stringify({
          id: "vis-live-001",
          workspace_id: TEST_WORKSPACE,
          version: 1,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          store_id: "str-001",
          visitor_id: "usr-live-001",
          status: "IN_PROGRESS",
          scheduled_for: new Date().toISOString(),
          arrived_at: new Date().toISOString(),
          completed_at: null,
          notes: "Live visit",
          promotions_reviewed: false,
          investigation_ids: [],
        })
      );
      return;
    }

    if (req.url === "/investigations/inv-001/actions/act-001" && req.method === "PATCH") {
      res.writeHead(409, { "Content-Type": "application/json" });
      res.end(
        JSON.stringify({
          error: {
            code: "VERSION_CONFLICT",
            message: "Optimistic concurrency conflict: action was modified by another user",
            details: { expected_version: 1, actual_version: 2 },
          },
        })
      );
      return;
    }

    res.writeHead(404, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ error: { code: "NOT_FOUND", message: "Route not found" } }));
  });

  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address() as { port: number };
  const baseUrl = `http://127.0.0.1:${address.port}`;

  try {
    const client = new StoreOpsClient({
      baseUrl,
      useDoubles: false,
      getAuthToken: async () => TEST_TOKEN,
      getWorkspaceId: () => TEST_WORKSPACE,
    });

    // 1. GET request over real HTTP socket
    const store = await client.getStore("str-001");
    assert.equal(store.id, "str-001");
    assert.equal(store.name, "Live Test Store");
    assert.equal(receivedMethod, "GET");
    assert.equal(receivedUrl, "/stores/str-001");
    assert.equal(receivedHeaders["authorization"], `Bearer ${TEST_TOKEN}`);
    assert.equal(receivedHeaders["x-workspace-id"], TEST_WORKSPACE);

    // 2. POST request over real HTTP socket (verifying auto-injected Idempotency-Key)
    const visit = await client.createVisit({
      store_id: "str-001",
      notes: "Live visit",
    });
    assert.equal(visit.id, "vis-live-001");
    assert.equal(receivedMethod, "POST");
    assert.ok(receivedHeaders["idempotency-key"], "Mutating POST must send Idempotency-Key");

    // 3. POST request resulting in HTTP 409 mapped into VersionConflictError
    await assert.rejects(
      async () => {
        await client.updateAction("inv-001", "act-001", {
          expected_version: 1,
          status: "CLAIMED_DONE",
        });
      },
      (err: unknown) => {
        assert.ok(err instanceof VersionConflictError, "Must throw typed VersionConflictError on HTTP 409");
        assert.equal(err.status, 409);
        assert.equal(err.code, "VERSION_CONFLICT");
        assert.ok(err.message.includes("Optimistic concurrency conflict"));
        return true;
      }
    );

    // 4. Fail-closed authentication when token is null
    const unauthedClient = new StoreOpsClient({
      baseUrl,
      useDoubles: false,
      getAuthToken: async () => null,
      getWorkspaceId: () => TEST_WORKSPACE,
    });

    await assert.rejects(
      async () => {
        await unauthedClient.getStore("str-001");
      },
      (err: unknown) => {
        assert.ok(err instanceof ApiRequestError, "Must throw ApiRequestError when unauthenticated");
        assert.equal(err.status, 401);
        assert.equal(err.code, "UNAUTHENTICATED");
        return true;
      }
    );
  } finally {
    await new Promise<void>((resolve) => server.close(() => resolve()));
  }
});
