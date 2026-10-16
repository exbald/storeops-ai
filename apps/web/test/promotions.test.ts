/**
 * Agreement-to-rules flow tests: agreement upload, promotion creation with an agreement,
 * Gemini extraction job polling, human-in-the-loop approval and extraction gaps.
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

import PromotionsPage from "../src/app/(dashboard)/promotions/page";
import PromotionDetailPage from "../src/app/(dashboard)/promotions/[id]/page";
import { AuthProvider } from "../src/lib/auth-context";
import { apiClient } from "../src/lib/api-client";
import { uploadAgreementPdf } from "../src/components/promotions/agreement-upload";
import { MOCK_PROMOTIONS, MOCK_PRODUCTS, MOCK_STORES } from "../src/lib/doubles";
import type { Job, Media, Promotion, Rule, Schemas } from "@storeops/contracts";

const AGREEMENT_ID = "00000000-0000-0000-0000-0000000000a1";
const PROMO_ID = "00000000-0000-0000-0000-0000000000b1";
const JOB_ID = "00000000-0000-0000-0000-0000000000c1";
const PRODUCT_A = MOCK_PRODUCTS[0].id;
const PRODUCT_B = MOCK_PRODUCTS[1].id;

const originalFetch = globalThis.fetch;
const restorers: Array<() => void> = [];

/** Replaces an apiClient method for one test; restored in afterEach. */
function stub<K extends keyof typeof apiClient>(name: K, impl: (typeof apiClient)[K]) {
  const original = apiClient[name];
  (apiClient as any)[name] = impl;
  restorers.push(() => {
    (apiClient as any)[name] = original;
  });
}

afterEach(() => {
  restorers.splice(0).forEach((restore) => restore());
  globalThis.fetch = originalFetch;
  apiClient.resetDoubles();
  apiClient.setUseDoubles(true);
});

function media(overrides: Partial<Media> = {}): Media {
  return {
    id: AGREEMENT_ID,
    workspace_id: MOCK_PROMOTIONS[0].workspace_id,
    version: 1,
    created_at: "2026-10-01T00:00:00Z",
    updated_at: "2026-10-01T00:00:00Z",
    kind: "AGREEMENT",
    filename: "aquapure_agreement.pdf",
    mime_type: "application/pdf",
    status: "PENDING_UPLOAD",
    store_id: null,
    visit_id: null,
    product_id: null,
    zone_id: null,
    zone_kind: null,
    captured_at: null,
    original_sha256: "a".repeat(64),
    normalized_sha256: null,
    byte_size: 8,
    width: null,
    height: null,
    rejection: null,
    download_url: "https://storage.example.test/agreement.pdf",
    download_url_expires_at: "2026-10-01T01:00:00Z",
    ...overrides,
  } as Media;
}

function rule(id: string, overrides: Partial<Rule>): Rule {
  return {
    rule_id: id,
    kind: "MIN_FACINGS",
    zone_id: "ENDCAP-1",
    zone_kind: "SHELF",
    product_id: PRODUCT_A,
    min_facings: 4,
    source: { kind: "DOCUMENT", media_id: AGREEMENT_ID, page: 2, quote: "Maintain four facings.", reviewer_note: null },
    ...overrides,
  };
}

function promotion(overrides: Partial<Promotion> = {}): Promotion {
  return {
    ...MOCK_PROMOTIONS[0],
    id: PROMO_ID,
    version: 3,
    name: "AquaPure Endcap",
    agreement_media_id: AGREEMENT_ID,
    extracted_rules: [],
    extraction_gaps: [],
    approved_policy: null,
    ...overrides,
  };
}

function job(status: Job["status"], stage: string): Job {
  return {
    id: JOB_ID,
    workspace_id: MOCK_PROMOTIONS[0].workspace_id,
    version: 1,
    created_at: "2026-10-01T00:00:00Z",
    updated_at: "2026-10-01T00:00:00Z",
    type: "POLICY_EXTRACT",
    status,
    resource_id: PROMO_ID,
    resource_type: "PROMOTION",
    attempt: 0,
    stage,
    started_at: null,
    finished_at: null,
    error: null,
    linked_previous_job_id: null,
    model_id: null,
    usage: null,
  } as Job;
}

function render(component: React.ReactElement, params: Record<string, string> = {}) {
  const pushes: string[] = [];
  const router = {
    back: () => {},
    forward: () => {},
    refresh: () => {},
    push: (href: string) => pushes.push(href),
    replace: () => {},
    prefetch: () => {},
  } as any;
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  const tree = React.createElement(
    AuthProvider,
    null,
    React.createElement(
      AppRouterContext.Provider,
      { value: router },
      React.createElement(
        SearchParamsContext.Provider,
        { value: new URLSearchParams() },
        React.createElement(PathParamsContext.Provider, { value: params }, component)
      )
    )
  );
  return {
    container,
    pushes,
    async mount() {
      await act(async () => root.render(tree));
      await settle();
    },
    async unmount() {
      await act(async () => root.unmount());
      container.remove();
    },
  };
}

async function settle(ms = 60) {
  await act(async () => {
    await new Promise((r) => setTimeout(r, ms));
  });
}

function findButton(container: HTMLElement, text: string): HTMLButtonElement {
  const button = Array.from(container.querySelectorAll("button")).find((b) => b.textContent?.includes(text));
  assert.ok(button, `Expected a button containing "${text}"`);
  return button as HTMLButtonElement;
}

async function click(el: HTMLElement) {
  await act(async () => {
    el.click();
  });
  await settle();
}

async function typeInto(input: HTMLInputElement, value: string) {
  const setter = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(input), "value")!.set!;
  await act(async () => {
    setter.call(input, value);
    input.dispatchEvent(new (window as any).Event("input", { bubbles: true }));
  });
}

test("uploadAgreementPdf: inits AGREEMENT media, PUTs the bytes, then completes it", async () => {
  apiClient.setUseDoubles(false);
  const calls: string[] = [];
  let initPayload: Schemas["MediaInit"] | null = null;
  let putRequest: { url: string; method?: string } | null = null;

  stub("initMedia", async (data) => {
    calls.push("init");
    initPayload = data;
    return {
      media: media(),
      upload_url: "https://upload.example.test/agreement",
      method: "PUT",
      headers: { "Content-Type": "application/pdf" },
      expires_at: "2026-10-01T01:00:00Z",
    };
  });
  globalThis.fetch = (async (url: string, init?: RequestInit) => {
    calls.push("put");
    putRequest = { url: String(url), method: init?.method };
    return new Response(null, { status: 200 });
  }) as typeof fetch;
  stub("completeMedia", async (id, data) => {
    calls.push(`complete:${id}:v${data.expected_version}`);
    return media({ status: "READY", version: 2 });
  });

  const file = new File([new Uint8Array([37, 80, 68, 70, 45, 49, 46, 52])], "deal.pdf", { type: "application/pdf" });
  const result = await uploadAgreementPdf(file);

  assert.deepEqual(calls, ["init", "put", `complete:${AGREEMENT_ID}:v1`]);
  assert.equal(result.status, "READY");
  const init = initPayload as unknown as Schemas["MediaInit"];
  assert.equal(init.kind, "AGREEMENT");
  assert.equal(init.mime_type, "application/pdf");
  assert.equal(init.byte_size, 8);
  assert.match(init.sha256, /^[a-f0-9]{64}$/);
  assert.equal(init.store_id, null);
  assert.equal(init.visit_id, null);
  assert.equal(init.zone_id, null);
  assert.equal(init.captured_at, null);
  assert.deepEqual(putRequest, { url: "https://upload.example.test/agreement", method: "PUT" });
});

test("uploadAgreementPdf: rejects non-PDF files before calling the API", async () => {
  let called = false;
  stub("initMedia", async () => {
    called = true;
    throw new Error("should not be called");
  });
  const file = new File(["hello"], "notes.txt", { type: "text/plain" });
  await assert.rejects(uploadAgreementPdf(file), /must be a PDF/);
  assert.equal(called, false);
});

test("PromotionsPage: lists stores and creates a promotion with an uploaded AGREEMENT media id", async () => {
  apiClient.setUseDoubles(true);
  const order: string[] = [];
  let createPayload: Schemas["PromotionCreate"] | null = null;

  globalThis.fetch = (async (url: string) => {
    assert.equal(String(url), "/samples/aquapure_agreement.pdf");
    return new Response(new Uint8Array([37, 80, 68, 70]), { status: 200, headers: { "Content-Type": "application/pdf" } });
  }) as typeof fetch;
  stub("initMedia", async (data) => {
    order.push(`init:${data.kind}`);
    return {
      media: media(),
      upload_url: "https://upload.example.test/agreement",
      method: "PUT",
      headers: {},
      expires_at: "2026-10-01T01:00:00Z",
    };
  });
  stub("completeMedia", async () => {
    order.push("complete");
    return media({ status: "READY", version: 2 });
  });
  stub("createPromotion", async (data) => {
    order.push("create");
    createPayload = data;
    return promotion({ name: data.name });
  });

  const view = render(React.createElement(PromotionsPage));
  try {
    await view.mount();
    await click(findButton(view.container, "Create promotion"));

    const storeOptions = view.container.querySelector("[data-testid='store-options']");
    assert.ok(storeOptions, "Store selector must render");
    for (const store of MOCK_STORES.filter((s) => s.active)) {
      assert.ok(storeOptions.textContent?.includes(store.name), `Store selector must list ${store.name}`);
    }

    await typeInto(view.container.querySelector("input[name='promotion-name']") as HTMLInputElement, "AquaPure Endcap");
    await typeInto(view.container.querySelector("input[name='starts-on']") as HTMLInputElement, "2026-11-01");
    await typeInto(view.container.querySelector("input[name='ends-on']") as HTMLInputElement, "2026-11-30");

    await click(findButton(view.container, "Use sample agreement"));
    assert.ok(view.container.innerHTML.includes("aquapure_agreement.pdf"), "Selected sample file name must show");

    const form = view.container.querySelector("form") as HTMLFormElement;
    await act(async () => {
      form.dispatchEvent(new (window as any).Event("submit", { bubbles: true, cancelable: true }));
    });
    await settle(120);

    assert.deepEqual(order, ["init:AGREEMENT", "complete", "create"]);
    const payload = createPayload as unknown as Schemas["PromotionCreate"];
    assert.equal(payload.agreement_media_id, AGREEMENT_ID);
    assert.equal(payload.name, "AquaPure Endcap");
    assert.equal(payload.starts_on, "2026-11-01");
    assert.ok(payload.store_ids.length >= 1);
    assert.deepEqual(view.pushes, [`/promotions/${PROMO_ID}`]);
  } finally {
    await view.unmount();
  }
});

test("PromotionDetailPage: extract calls extractPolicy with expected_version, polls the job and reloads", async () => {
  apiClient.setUseDoubles(true);
  let current = promotion();
  let extractArgs: { id: string; version: number } | null = null;
  const polled: string[] = [];

  stub("getPromotion", async () => current);
  stub("getMedia", async () => media({ status: "READY", version: 2 }));
  stub("listPolicyVersions", async () => ({ items: [] }));
  stub("extractPolicy", async (id, data) => {
    extractArgs = { id, version: data.expected_version };
    return job("QUEUED", "QUEUED");
  });
  stub("getJob", async (id) => {
    polled.push(id);
    current = promotion({
      version: 4,
      draft_revision: 2,
      extracted_rules: [rule("00000000-0000-0000-0000-0000000000d1", {})],
    });
    return job("SUCCEEDED", "EXTRACTED");
  });
  stub("getJobEvents", async () => ({
    items: [
      { sequence: 1, job_id: JOB_ID, at: "2026-10-01T00:00:00Z", stage: "QUEUED", summary: "Queued", status: "QUEUED" },
      { sequence: 2, job_id: JOB_ID, at: "2026-10-01T00:00:01Z", stage: "EXTRACTED", summary: "Extracted 1 rules and 0 gaps", status: "SUCCEEDED" },
    ],
    last_sequence: 2,
  }));

  const view = render(React.createElement(PromotionDetailPage), { id: PROMO_ID });
  try {
    await view.mount();
    assert.ok(view.container.innerHTML.includes("Nothing applies until you approve it"));
    const extractBtn = findButton(view.container, "Extract rules with Gemini");
    assert.equal(extractBtn.disabled, false, "Extract must be enabled for a READY agreement");

    await click(extractBtn);
    await settle(120);

    assert.deepEqual(extractArgs, { id: PROMO_ID, version: 3 });
    assert.deepEqual(polled, [JOB_ID]);
    const eventsList = view.container.querySelector("[data-testid='extraction-events']");
    assert.ok(eventsList?.textContent?.includes("Extracted 1 rules and 0 gaps"), "Job events must render");
    assert.equal(view.container.querySelectorAll("[data-testid='proposed-rule']").length, 1, "Reloaded rules must render");
    assert.ok(view.container.querySelector("[data-testid='rule-citation']")?.textContent?.includes("page 2"));
  } finally {
    await view.unmount();
  }
});

test("PromotionDetailPage: extract is disabled until an agreement is attached", async () => {
  apiClient.setUseDoubles(true);
  stub("getPromotion", async () => promotion({ agreement_media_id: null }));
  stub("listPolicyVersions", async () => ({ items: [] }));

  const view = render(React.createElement(PromotionDetailPage), { id: PROMO_ID });
  try {
    await view.mount();
    assert.equal(findButton(view.container, "Extract rules with Gemini").disabled, true);
    assert.ok(view.container.innerHTML.includes("Upload the agreement PDF first."));
  } finally {
    await view.unmount();
  }
});

test("PromotionDetailPage: approve sends only included rules and the products they reference", async () => {
  apiClient.setUseDoubles(true);
  const ruleA = rule("00000000-0000-0000-0000-0000000000e1", { product_id: PRODUCT_A });
  const ruleB = rule("00000000-0000-0000-0000-0000000000e2", {
    kind: "REQUIRED_PRODUCT",
    product_id: PRODUCT_B,
    min_facings: null,
    source: { kind: "DOCUMENT", media_id: AGREEMENT_ID, page: 3, quote: "Stock the sparkling variant.", reviewer_note: null },
  });
  const ruleC = rule("00000000-0000-0000-0000-0000000000e3", {
    kind: "REQUIRED_DISPLAY",
    zone_id: "DISPLAY-1",
    zone_kind: "DISPLAY",
    product_id: null,
    min_facings: null,
  });
  let approvePayload: Schemas["ApprovePolicy"] | null = null;

  stub("getPromotion", async () => promotion({ extracted_rules: [ruleA, ruleB, ruleC] }));
  stub("getMedia", async () => media({ status: "READY", version: 2 }));
  stub("listPolicyVersions", async () => ({ items: [] }));
  stub("approvePolicy", async (_id, data) => {
    approvePayload = data;
    return { ...MOCK_PROMOTIONS[0].approved_policy!, rules: data.rules };
  });

  const view = render(React.createElement(PromotionDetailPage), { id: PROMO_ID });
  try {
    await view.mount();
    const rows = Array.from(view.container.querySelectorAll("[data-testid='proposed-rule']"));
    assert.equal(rows.length, 3);
    const checkboxes = rows.map((r) => r.querySelector("input[type='checkbox']") as HTMLInputElement);
    assert.ok(checkboxes.every((c) => c.checked), "Every proposed rule is included by default");

    await click(checkboxes[1]); // exclude the REQUIRED_PRODUCT rule for product B
    assert.equal(checkboxes[1].checked, false);

    await click(findButton(view.container, "Approve rules (2)"));

    const payload = approvePayload as unknown as Schemas["ApprovePolicy"];
    assert.ok(payload, "approvePolicy must be called");
    assert.equal(payload.expected_version, 3);
    assert.deepEqual(
      payload.rules.map((r) => r.rule_id),
      [ruleA.rule_id, ruleC.rule_id]
    );
    assert.deepEqual(payload.catalog_product_ids, [PRODUCT_A]);
  } finally {
    await view.unmount();
  }
});

test("PromotionDetailPage: extraction gaps render as 'Needs your input'", async () => {
  apiClient.setUseDoubles(true);
  stub("getPromotion", async () =>
    promotion({
      extracted_rules: [rule("00000000-0000-0000-0000-0000000000f1", {})],
      extraction_gaps: ["Rule proposal gap (Missing zone_id): Place a chiller near checkout."],
    })
  );
  stub("getMedia", async () => media({ status: "READY", version: 2 }));
  stub("listPolicyVersions", async () => ({ items: [] }));

  const view = render(React.createElement(PromotionDetailPage), { id: PROMO_ID });
  try {
    await view.mount();
    const gaps = view.container.querySelector("[data-testid='extraction-gaps']");
    assert.ok(gaps, "Gaps section must render");
    assert.ok(gaps.textContent?.includes("Needs your input (1)"));
    assert.ok(gaps.textContent?.includes("Place a chiller near checkout."));
  } finally {
    await view.unmount();
  }
});

test("PromotionDetailPage: shows the approved policy and version history", async () => {
  apiClient.setUseDoubles(true);
  const approved = MOCK_PROMOTIONS[0].approved_policy!;
  stub("getPromotion", async () => promotion({ approved_policy: approved }));
  stub("getMedia", async () => media({ status: "READY", version: 2 }));
  stub("listPolicyVersions", async () => ({ items: [approved] }));

  const view = render(React.createElement(PromotionDetailPage), { id: PROMO_ID });
  try {
    await view.mount();
    assert.ok(view.container.innerHTML.includes(`Approved v${approved.version}`));
    assert.ok(view.container.querySelector("[data-testid='approved-policy']"));
    assert.equal(view.container.querySelectorAll("[data-testid='policy-versions'] li").length, 1);
    assert.equal(view.container.querySelectorAll("[data-testid='proposed-rule']").length, 0);
  } finally {
    await view.unmount();
  }
});

test("StoreOpsClient doubles: extractPolicy fails closed instead of fabricating rules", async () => {
  apiClient.setUseDoubles(true);
  await assert.rejects(apiClient.extractPolicy(PROMO_ID, { expected_version: 1 }), /live StoreOps API/);
});
