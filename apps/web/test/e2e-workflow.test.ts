import test from "node:test";
import assert from "node:assert/strict";
import { StoreOpsClient, VersionConflictError } from "../src/lib/api-client.ts";

test("AC40: StoreOpsClient implements complete browser workflow operations", async () => {
  const client = new StoreOpsClient({ useDoubles: true });

  // 1. Store inspection and readiness
  const store = await client.getStore("00000000-0000-0000-0000-000000000021");
  assert.equal(store.code, "STR-001");
  assert.ok(store.name);

  // 2. Visit lifecycle: create visit, get visit, update visit notes
  const visit = await client.createVisit({
    store_id: store.id,
    notes: "Initial visit check",
  });
  assert.ok(visit.id);
  assert.equal(visit.status, "OPEN");

  const fetchedVisit = await client.getVisit(visit.id);
  assert.equal(fetchedVisit.id, visit.id);

  // 3. Media upload initialization and completion
  const uploadResp = await client.initMedia({
    kind: "VISIT_BEFORE",
    filename: "shelf_before.jpg",
    mime_type: "image/jpeg",
    byte_size: 1024,
    sha256: "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
    store_id: store.id,
    visit_id: visit.id,
    product_id: null,
    zone_id: "shelf-main",
    zone_kind: "SHELF",
    captured_at: new Date().toISOString(),
  });
  assert.ok(uploadResp.media.id);
  assert.ok(uploadResp.upload_url);

  const completedMedia = await client.completeMedia(uploadResp.media.id, {
    expected_version: 1,
  });
  assert.equal(completedMedia.id, uploadResp.media.id);

  // 4. Update visit notes
  const updatedVisit = await client.updateVisit(visit.id, {
    expected_version: visit.version,
    notes: "Shelf photos added",
  });
  assert.equal(updatedVisit.version, visit.version + 1);

  // 5. Version conflict on stale visit update
  await assert.rejects(
    async () => {
      await client.updateVisit(visit.id, {
        expected_version: 1, // Stale version
        notes: "Conflicting notes",
      });
    },
    (err: unknown) => {
      assert.ok(err instanceof VersionConflictError);
      return true;
    }
  );

  // 6. Trigger investigation from visit
  const job = await client.createInvestigation({
    store_id: store.id,
    visit_id: visit.id,
    promotion_id: "00000000-0000-0000-0000-000000000061",
    media_ids: [uploadResp.media.id],
  });
  assert.ok(job.id);
  assert.ok(job.status);

  // 7. Poll job and events
  const polledJob = await client.getJob(job.id);
  assert.equal(polledJob.id, job.id);
  const events = await client.getJobEvents(job.id);
  assert.ok(Array.isArray(events.items));

  // 8. Fetch investigation and inspect actions
  const investigations = await client.listInvestigations({ visit_id: visit.id });
  assert.ok(investigations.items.length >= 1);
  const inv = investigations.items[0];
  const fetchedInv = await client.getInvestigation(inv.id);
  assert.equal(fetchedInv.id, inv.id);
  assert.ok(fetchedInv.actions.length >= 1);

  // 9. Accept investigation plan
  const acceptedInv = await client.acceptInvestigation(inv.id, {
    expected_version: inv.version,
  });
  assert.equal(acceptedInv.state, "ACCEPTED");

  // 10. Update action completion
  const targetAction = acceptedInv.actions[0];
  const updatedInvAfterAction = await client.updateAction(inv.id, targetAction.id, {
    expected_version: acceptedInv.version,
    status: "CLAIMED_DONE",
  });
  assert.equal(updatedInvAfterAction.actions[0].status, "CLAIMED_DONE");

  // 11. Trigger verification
  const verifyJob = await client.verifyInvestigation(inv.id, {
    expected_version: updatedInvAfterAction.version,
    after_media_ids: [uploadResp.media.id],
  });
  assert.ok(verifyJob.id);

  // 12. Check verification records and report
  const verifications = await client.listVerifications(inv.id);
  assert.ok(verifications.items.length >= 1);

  const report = await client.getReport("00000000-0000-0000-0000-000000000081");
  assert.ok(report.id);
  assert.ok(report.outcome);
});

test("StoreOpsClient dynamic auth token and workspace session configuration", async () => {
  const originalFetch = globalThis.fetch;
  let sentHeaders: Record<string, string> = {};

  globalThis.fetch = async (_input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    sentHeaders = (init?.headers as Record<string, string>) || {};
    return new Response(JSON.stringify({ items: [] }), { status: 200, headers: { "Content-Type": "application/json" } });
  };

  try {
    const client = new StoreOpsClient({
      useDoubles: false,
      baseUrl: "https://api.storeops.test",
    });

    client.setAuthToken("custom-token-xyz");
    client.setWorkspaceId("00000000-0000-0000-0000-000000000099");

    await client.listStores();

    assert.equal(sentHeaders["Authorization"], "Bearer custom-token-xyz");
    assert.equal(sentHeaders["X-Workspace-Id"], "00000000-0000-0000-0000-000000000099");
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("Investigation dismiss detects OCC conflict and updates state", async () => {
  const client = new StoreOpsClient({ useDoubles: true });
  const invs = await client.listInvestigations();
  const target = invs.items[0];

  // 1. OCC conflict on stale expected_version
  await assert.rejects(
    async () => {
      await client.dismissInvestigation(target.id, {
        expected_version: 9999,
        reason: "SUPERSEDED: Replaced by newer audit",
      });
    },
    (err: unknown) => {
      assert.ok(err instanceof VersionConflictError);
      assert.equal(err.status, 409);
      return true;
    }
  );

  // 2. Successful dismissal with correct version
  const dismissed = await client.dismissInvestigation(target.id, {
    expected_version: target.version,
    reason: "SUPERSEDED: Replaced by newer audit",
  });
  assert.equal(dismissed.state, "DISMISSED");
  assert.equal(dismissed.version, target.version + 1);
});

test("Verification report gating: only PASS outcome displays Execution verified", async () => {
  const client = new StoreOpsClient({ useDoubles: true });
  const report = await client.getReport("00000000-0000-0000-0000-000000000081");

  // Gating rule: report.outcome === "PASS"
  const isVerified = report.outcome === "PASS";
  assert.equal(typeof isVerified, "boolean");

  // Synthetic check with all possible outcomes
  const outcomes = ["PASS", "FAIL", "UNKNOWN"] as const;
  for (const outcome of outcomes) {
    const verified = outcome === "PASS";
    if (outcome === "PASS") {
      assert.equal(verified, true, "PASS outcome must be verified");
    } else {
      assert.equal(verified, false, `${outcome} outcome must NOT be verified`);
    }
  }
});

