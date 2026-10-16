/**
 * Judge-facing polish tests:
 * - landing entry-point selection (completed example / try it yourself) and HomePage CTAs
 * - header "View as" toggle (no dev-sim wording) and nav "Guide" label
 * - live-mode auth never renders test-double memberships; role comes from GET /me
 * - investigation evidence thumbnails and verify-modal sample after-photos
 */

import "./setup-dom";
import test, { afterEach } from "node:test";
import assert from "node:assert/strict";
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import {
  PathParamsContext,
  SearchParamsContext,
} from "next/dist/shared/lib/hooks-client-context.shared-runtime";
import { AppRouterContext } from "next/dist/shared/lib/app-router-context.shared-runtime";
import type { Evidence, Investigation, Membership, Visit } from "@storeops/contracts";

import HomePage from "../src/app/(dashboard)/home/page";
import InvestigationDetailPage from "../src/app/(dashboard)/investigations/[id]/page";
import DashboardLayout from "../src/app/(dashboard)/layout";
import { Header } from "../src/components/shell/header";
import { Nav } from "../src/components/shell/nav";
import {
  AuthContext,
  AuthProvider,
  resolveInitialAuthState,
  type AuthContextType,
  type UserRole,
} from "../src/lib/auth-context";
import { apiClient } from "../src/lib/api-client";
import { selectDemoEntryPoints, VALUE_STATEMENT } from "../src/lib/demo-entry";
import { MOCK_MEMBERSHIPS } from "../src/lib/doubles";

const mockRouter = {
  back: () => {},
  forward: () => {},
  refresh: () => {},
  push: () => {},
  replace: () => {},
  prefetch: () => {},
} as any;

const originalFetch = globalThis.fetch;

afterEach(() => {
  apiClient.resetDoubles();
  apiClient.setUseDoubles(true);
  globalThis.fetch = originalFetch;
  delete process.env.NEXT_PUBLIC_AUTH_TOKEN;
});

// ---------- helpers ----------

function makeVisit(overrides: Partial<Visit>): Visit {
  return {
    id: "11111111-0000-0000-0000-000000000000",
    workspace_id: "00000000-0000-0000-0000-000000000001",
    version: 1,
    created_at: "2026-10-01T10:00:00Z",
    updated_at: "2026-10-01T10:00:00Z",
    store_id: "22222222-0000-0000-0000-000000000000",
    notes: "",
    visit_started_at: "2026-10-01T10:00:00Z",
    status: "OPEN",
    before_media_ids: [],
    after_media_ids: [],
    active_investigation_id: null,
    report_ids: [],
    ...overrides,
  };
}

function makeInvestigation(overrides: Partial<Investigation>): Investigation {
  const base = apiClient.getDoubleInvestigations()[0];
  return { ...base, ...overrides };
}

function wrap(children: React.ReactElement, params: Record<string, string> = {}) {
  return React.createElement(
    AppRouterContext.Provider,
    { value: mockRouter },
    React.createElement(
      SearchParamsContext.Provider,
      { value: new URLSearchParams() },
      React.createElement(PathParamsContext.Provider, { value: params }, children)
    )
  );
}

async function settle(ms = 60) {
  await act(async () => {
    await new Promise((r) => setTimeout(r, ms));
  });
}

async function render(element: React.ReactElement) {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  await act(async () => {
    root.render(element);
  });
  return {
    container,
    async unmount() {
      await act(async () => root.unmount());
      container.remove();
    },
  };
}

async function click(el: Element) {
  await act(async () => {
    el.dispatchEvent(new Event("click", { bubbles: true }));
  });
}

function findButton(container: Element, text: string): HTMLButtonElement {
  const btn = Array.from(container.querySelectorAll("button")).find((b) => b.textContent?.trim() === text);
  assert.ok(btn, `Expected a button labelled "${text}"`);
  return btn as HTMLButtonElement;
}

function authValue(overrides: Partial<AuthContextType> = {}): AuthContextType {
  return {
    user: { id: "u1", email: "judge@storeops.ai" },
    token: "t",
    workspaceId: "00000000-0000-0000-0000-000000000001",
    role: "ADMIN",
    isAdmin: true,
    isRep: true,
    activeWorkspaceName: "Live Demo Retail",
    memberships: [],
    isLoading: false,
    isUnprovisioned: false,
    switchWorkspace: () => {},
    setRole: () => {},
    signOut: () => {},
    ...overrides,
  };
}

// ---------- landing entry points ----------

test("selectDemoEntryPoints: picks the CLOSED visit's investigation and the OPEN visit with a before photo", () => {
  const closed = makeVisit({ id: "aaaaaaaa-0000-0000-0000-000000000001", status: "CLOSED" });
  const closedNoInv = makeVisit({ id: "aaaaaaaa-0000-0000-0000-000000000002", status: "CLOSED" });
  const openNoPhoto = makeVisit({
    id: "aaaaaaaa-0000-0000-0000-000000000003",
    status: "OPEN",
    created_at: "2026-10-05T10:00:00Z",
  });
  const openWithPhoto = makeVisit({
    id: "aaaaaaaa-0000-0000-0000-000000000004",
    status: "OPEN",
    before_media_ids: ["bbbbbbbb-0000-0000-0000-000000000001"],
  });
  const completedInv = makeInvestigation({
    id: "cccccccc-0000-0000-0000-000000000001",
    visit_id: closed.id,
    state: "RESOLVED",
    latest_verification_id: "dddddddd-0000-0000-0000-000000000001",
  });
  const openInv = makeInvestigation({ id: "cccccccc-0000-0000-0000-000000000002", visit_id: openWithPhoto.id });

  const result = selectDemoEntryPoints([openNoPhoto, closedNoInv, closed, openWithPhoto], [openInv, completedInv]);

  assert.deepEqual(result.completedExample, {
    visitId: closed.id,
    investigationId: completedInv.id,
    href: `/investigations/${completedInv.id}`,
  });
  assert.deepEqual(result.tryItYourself, { visitId: openWithPhoto.id, href: `/visits/${openWithPhoto.id}` });
});

test("selectDemoEntryPoints: returns nulls when no CLOSED visit has an investigation and no visit is OPEN", () => {
  const closed = makeVisit({ status: "CLOSED" });
  const result = selectDemoEntryPoints([closed], []);
  assert.equal(result.completedExample, null);
  assert.equal(result.tryItYourself, null);
});

test("HomePage: renders value statement and both CTAs linking to real records", async () => {
  const closed = makeVisit({ id: "aaaaaaaa-0000-0000-0000-000000000011", status: "CLOSED" });
  const open = makeVisit({
    id: "aaaaaaaa-0000-0000-0000-000000000012",
    status: "OPEN",
    before_media_ids: ["bbbbbbbb-0000-0000-0000-000000000011"],
  });
  const inv = makeInvestigation({ id: "cccccccc-0000-0000-0000-000000000011", visit_id: closed.id });
  apiClient.listVisits = async () => ({ items: [closed, open], next_cursor: null });
  apiClient.listInvestigations = async () => ({ items: [inv], next_cursor: null });

  const { container, unmount } = await render(
    React.createElement(AuthContext.Provider, { value: authValue() }, wrap(React.createElement(HomePage)))
  );
  try {
    await settle();
    assert.ok(container.textContent?.includes(VALUE_STATEMENT));
    const links = Array.from(container.querySelectorAll("a"));
    const example = links.find((a) => a.textContent?.includes("See a completed example"));
    const tryIt = links.find((a) => a.textContent?.includes("Try it yourself"));
    assert.equal(example?.getAttribute("href"), `/investigations/${inv.id}`);
    assert.equal(tryIt?.getAttribute("href"), `/visits/${open.id}`);
  } finally {
    delete (apiClient as any).listVisits;
    delete (apiClient as any).listInvestigations;
    await unmount();
  }
});

test("HomePage: falls back to the setup checklist when the workspace has no visits", async () => {
  apiClient.listVisits = async () => ({ items: [], next_cursor: null });
  apiClient.listInvestigations = async () => ({ items: [], next_cursor: null });

  const { container, unmount } = await render(
    React.createElement(AuthContext.Provider, { value: authValue() }, wrap(React.createElement(HomePage)))
  );
  try {
    await settle();
    assert.ok(!container.textContent?.includes("See a completed example"));
    const setupLink = Array.from(container.querySelectorAll("a")).find((a) => a.getAttribute("href") === "/setup");
    assert.ok(setupLink, "Expected a link to the setup checklist");
    assert.ok(setupLink.textContent?.includes("Open the setup checklist"));
  } finally {
    delete (apiClient as any).listVisits;
    delete (apiClient as any).listInvestigations;
    await unmount();
  }
});

// ---------- header and nav ----------

test("Header: shows a 'View as: Admin | Rep' toggle, no Dev Sim or Handbook, and switches role", async () => {
  const calls: UserRole[] = [];
  const { container, unmount } = await render(
    React.createElement(
      AuthContext.Provider,
      { value: authValue({ setRole: (r: UserRole) => calls.push(r) }) },
      wrap(React.createElement(Header))
    )
  );
  try {
    const html = container.innerHTML;
    assert.ok(container.textContent?.includes("View as:"));
    assert.ok(!html.includes("Dev Sim"), "Header must not mention Dev Sim");
    assert.ok(!html.includes("Handbook"), "Header must not link to the Handbook");
    assert.ok(!html.includes("AC-38") && !html.includes("T08"), "Header must not show internal task IDs");

    const adminBtn = findButton(container, "Admin");
    assert.equal(adminBtn.getAttribute("aria-pressed"), "true");
    await click(findButton(container, "Rep"));
    assert.deepEqual(calls, ["REP"]);
  } finally {
    await unmount();
  }
});

test("Header: doubles-mode banner is plain language without internal task IDs", async () => {
  apiClient.setUseDoubles(true);
  const { container, unmount } = await render(
    React.createElement(AuthContext.Provider, { value: authValue() }, wrap(React.createElement(Header)))
  );
  try {
    assert.ok(container.textContent?.includes("Demo data mode"));
    assert.ok(!container.innerHTML.includes("Wave 4"));
  } finally {
    await unmount();
  }
});

test("Nav: labels the guide 'Guide' and includes Home", async () => {
  const { container, unmount } = await render(
    React.createElement(AuthContext.Provider, { value: authValue() }, wrap(React.createElement(Nav)))
  );
  try {
    const labels = Array.from(container.querySelectorAll("a")).map((a) => a.textContent);
    assert.ok(labels.includes("Guide"));
    assert.ok(!labels.includes("User Guide"));
    assert.ok(labels.includes("Home"));
  } finally {
    await unmount();
  }
});

// ---------- live-mode auth ----------

test("resolveInitialAuthState: live mode starts empty and loading; doubles mode seeds doubles", () => {
  const live = resolveInitialAuthState(false, "live-token");
  assert.deepEqual(live.memberships, []);
  assert.equal(live.user, null);
  assert.equal(live.workspaceId, null);
  assert.equal(live.isLoading, true);

  const doubles = resolveInitialAuthState(true, null);
  assert.equal(doubles.memberships, MOCK_MEMBERSHIPS);
  assert.equal(doubles.isLoading, false);
});

test("AuthProvider (live): shows 'Loading workspace…' without mock membership, then uses server role", async () => {
  apiClient.setUseDoubles(false);
  process.env.NEXT_PUBLIC_AUTH_TOKEN = "live-token";

  let resolveMe: (v: { user_id: string; email: string; memberships: Membership[] }) => void = () => {};
  const origGetMe = apiClient.getMe.bind(apiClient);
  apiClient.getMe = () =>
    new Promise((resolve) => {
      resolveMe = resolve;
    });

  const { container, unmount } = await render(
    React.createElement(
      AuthProvider,
      null,
      wrap(React.createElement(DashboardLayout, null, React.createElement("div", null, "Child content")))
    )
  );
  try {
    const initialHtml = container.innerHTML;
    for (const m of MOCK_MEMBERSHIPS) {
      assert.ok(!initialHtml.includes(m.workspace_name ?? "@@none"), `Must not render mock membership ${m.workspace_name}`);
    }
    assert.ok(container.textContent?.includes("Loading workspace"));
    assert.ok(!container.textContent?.includes("Sign In Required"));
    assert.ok(!container.textContent?.includes("Child content"));

    await act(async () => {
      resolveMe({
        user_id: "33333333-0000-0000-0000-000000000001",
        email: "rep@storeops.ai",
        memberships: [
          { workspace_id: "44444444-0000-0000-0000-000000000001", workspace_name: "Live Demo Retail", role: "REP" },
        ],
      });
    });
    await settle(20);

    assert.ok(container.textContent?.includes("Live Demo Retail"));
    assert.ok(container.textContent?.includes("Child content"));
    const repBtns = Array.from(container.querySelectorAll("button")).filter((b) => b.textContent?.trim() === "Rep");
    assert.ok(repBtns.length > 0);
    assert.equal(repBtns[0].getAttribute("aria-pressed"), "true", "Role must come from the server membership");
  } finally {
    apiClient.getMe = origGetMe;
    apiClient.setAuthToken(null);
    await unmount();
  }
});

// ---------- investigation page ----------

function readyInvestigation(): Investigation {
  apiClient.resetDoubles(); // work on copies, never the shared MOCK_* records
  const inv = apiClient.getDoubleInvestigations()[0];
  inv.state = "ACCEPTED";
  inv.actions = inv.actions.map((a) => ({ ...a, status: "CLAIMED_DONE", required_zone_ids: ["ZONE-BEV-01"] }));
  return inv;
}

test("InvestigationDetailPage: renders cited photo evidence as thumbnails next to claims", async () => {
  apiClient.resetDoubles();
  const inv = apiClient.getDoubleInvestigations()[0];
  const evidenceId = inv.diagnosis!.claims[0].evidence_ids[0];
  const mediaId = "55555555-0000-0000-0000-000000000001";
  const ev: Evidence = {
    id: evidenceId,
    investigation_id: inv.id,
    kind: "PHOTO",
    observed_at: "2026-10-01T10:00:00Z",
    retrieved_at: "2026-10-01T10:00:00Z",
    freshness: "CURRENT",
    summary: "Before photo of ZONE-BEV-01 showing 2 facings",
    source_id: mediaId,
    source_sha256: "a".repeat(64),
    locator: {
      media_id: mediaId,
      page: null,
      quote: null,
      box: null,
      row_ids: [],
      batch_ids: [],
      query_template_id: null,
      query_job_id: null,
      query_parameters: {},
    },
  };
  apiClient.getDoubleEvidence().push(ev);

  const { container, unmount } = await render(
    React.createElement(AuthProvider, null, wrap(React.createElement(InvestigationDetailPage), { id: inv.id }))
  );
  try {
    await settle(100);
    const img = container.querySelector(`img[alt="${ev.summary}"]`);
    assert.ok(img, "Expected a thumbnail for the cited photo");
    assert.ok(img.getAttribute("src")?.includes(mediaId), "Thumbnail must use the media download_url");
    assert.ok(!container.textContent?.includes("visual citation(s)"), "Must show photos, not just a count");
  } finally {
    await unmount();
  }
});

async function runSampleButton(label: string, expectedFile: string) {
  const inv = readyInvestigation();
  const fetched: string[] = [];
  globalThis.fetch = (async (input: any) => {
    fetched.push(String(input));
    return new Response(new Uint8Array([0xff, 0xd8, 0xff, 0xe0, 1, 2, 3, 4]), {
      status: 200,
      headers: { "Content-Type": "image/jpeg" },
    });
  }) as typeof fetch;

  const initCalls: any[] = [];
  const origInit = apiClient.initMedia.bind(apiClient);
  apiClient.initMedia = async (data) => {
    initCalls.push(data);
    return origInit(data);
  };

  const { container, unmount } = await render(
    React.createElement(AuthProvider, null, wrap(React.createElement(InvestigationDetailPage), { id: inv.id }))
  );
  try {
    await settle();
    await click(findButton(container, "Verify the fix"));
    const before = Date.now();
    await click(findButton(container, label));
    await settle(60);

    assert.ok(fetched.some((u) => u.endsWith(`/samples/${expectedFile}`)), `Expected fetch of ${expectedFile}`);
    assert.equal(initCalls.length, 1);
    const call = initCalls[0];
    assert.equal(call.kind, "VISIT_AFTER");
    assert.equal(call.filename, expectedFile);
    assert.equal(call.visit_id, inv.visit_id);
    assert.equal(call.store_id, inv.store_id);
    assert.equal(call.zone_id, "ZONE-BEV-01");
    const captured = Date.parse(call.captured_at);
    assert.ok(Math.abs(captured - before) < 5000, "captured_at must be stamped at click time");

    const selected = container.querySelector('[aria-label="Selected after photos"]');
    assert.ok(selected?.textContent?.includes(expectedFile), "Sample must be selected for verification");
  } finally {
    apiClient.initMedia = origInit;
    await unmount();
  }
}

test("VerifyModal: 'Use sample photo: fixed' uploads shelf_after.jpg as a fresh VISIT_AFTER photo", async () => {
  await runSampleButton("Use sample photo: fixed", "shelf_after.jpg");
});

test("VerifyModal: 'Use sample photo: still not fixed' uploads shelf_after_fail.jpg as a fresh VISIT_AFTER photo", async () => {
  await runSampleButton("Use sample photo: still not fixed", "shelf_after_fail.jpg");
});

test("InvestigationDetailPage: after a failed check (NEEDS_WORK) the rep can verify again", async () => {
  const inv = readyInvestigation();
  inv.state = "NEEDS_WORK";
  const { container, unmount } = await render(
    React.createElement(AuthProvider, null, wrap(React.createElement(InvestigationDetailPage), { id: inv.id }))
  );
  try {
    await settle();
    const btn = findButton(container, "Verify again");
    assert.equal((btn as HTMLButtonElement).disabled, false);
    await click(btn);
    assert.ok(findButton(container, "Use sample photo: fixed"), "Verify dialog must open from NEEDS_WORK");
  } finally {
    await unmount();
  }
});
