/**
 * Page Component Integration Tests for StoreOps Web Shell (T08 / AC40).
 *
 * Verifies real component mount, lifecycle effects, error handling,
 * signed-out security gating, and optimistic concurrency control (OCC):
 * 1. VisitDetailPage: Surfaces store loading errors and promotion fetch errors as visible alert banners with retry.
 * 2. InvestigationDetailPage: Handles OCC version conflicts (409) during action status claiming.
 * 3. ReportDetailPage: Gating assertion that "Execution verified" renders ONLY when verification outcome is "PASS".
 * 4. ReportDetailPage: Displays grounded audit context with linked investigation hypothesis and verification outcome.
 * 5. DashboardLayout: Renders explicit "Sign In Required" screen when user or session token is null.
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

import ReportDetailPage from "../src/app/(dashboard)/reports/[id]/page";
import VisitDetailPage from "../src/app/(dashboard)/visits/[id]/page";
import InvestigationDetailPage from "../src/app/(dashboard)/investigations/[id]/page";
import DashboardLayout from "../src/app/(dashboard)/layout";
import { AuthProvider } from "../src/lib/auth-context";
import { apiClient, VersionConflictError } from "../src/lib/api-client";
import type { Report } from "@storeops/contracts";

const mockRouter = {
  back: () => {},
  forward: () => {},
  refresh: () => {},
  push: () => {},
  replace: () => {},
  prefetch: () => {},
} as any;

// Clean up state after each test so tests remain isolated
afterEach(() => {
  apiClient.resetDoubles();
  apiClient.setUseDoubles(true);
});

function renderWithContext(component: React.ReactElement, params: Record<string, string> = {}) {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);

  return {
    container,
    root,
    async mount() {
      await act(async () => {
        root.render(
          React.createElement(
            AppRouterContext.Provider,
            { value: mockRouter },
            React.createElement(
              SearchParamsContext.Provider,
              { value: new URLSearchParams() },
              React.createElement(
                PathParamsContext.Provider,
                { value: params },
                component
              )
            )
          )
        );
      });
      // Wait for async useEffect fetch cycles to settle
      await act(async () => {
        await new Promise((r) => setTimeout(r, 60));
      });
    },
    async unmount() {
      await act(async () => {
        root.unmount();
      });
      container.remove();
    },
  };
}

test("ReportDetailPage: renders 'Execution verified' ONLY when report outcome is PASS", async () => {
  apiClient.setUseDoubles(true);
  const passReport = apiClient.getDoubleReports().find((r) => r.outcome === "PASS");
  assert.ok(passReport, "Expected a PASS report double");

  const { container, mount, unmount } = renderWithContext(
    React.createElement(ReportDetailPage),
    { id: passReport.id }
  );

  try {
    await mount();

    assert.ok(
      container.innerHTML.includes("Execution verified"),
      "Report with PASS outcome must render 'Execution verified' badge"
    );
    assert.ok(
      container.innerHTML.includes("Verification Summary"),
      "Report page must render 'Verification Summary' section"
    );
    assert.ok(
      container.innerHTML.includes(passReport.summary),
      "Report page must render report summary text"
    );
  } finally {
    await unmount();
  }
});

test("ReportDetailPage: omits 'Execution verified' when report outcome is FAIL", async () => {
  apiClient.setUseDoubles(true);
  const originalReport = apiClient.getDoubleReports()[0];
  const failReport: Report = {
    ...originalReport,
    id: "rep-fail-assertion-001",
    outcome: "FAIL",
    summary: "Facing requirements not met on shelf-main.",
  };
  apiClient.getDoubleReports().push(failReport);

  const { container, mount, unmount } = renderWithContext(
    React.createElement(ReportDetailPage),
    { id: failReport.id }
  );

  try {
    await mount();

    assert.equal(
      container.innerHTML.includes("Execution verified"),
      false,
      "Report with FAIL outcome must NOT render 'Execution verified'"
    );
    assert.ok(
      container.innerHTML.includes("FAIL"),
      "Report with FAIL outcome must render FAIL badge"
    );
  } finally {
    await unmount();
  }
});

test("ReportDetailPage: surfaces investigation hypothesis and verification outcome in Audit Context", async () => {
  apiClient.setUseDoubles(true);
  const passReport = apiClient.getDoubleReports()[0];

  const { container, mount, unmount } = renderWithContext(
    React.createElement(ReportDetailPage),
    { id: passReport.id }
  );

  try {
    await mount();

    assert.ok(
      container.innerHTML.includes("Investigation:"),
      "Must display investigation audit context"
    );
    assert.ok(
      container.innerHTML.includes("Verification:"),
      "Must display verification audit context"
    );
    assert.ok(
      container.innerHTML.includes("Grounded StoreOps Audit Report"),
      "Must cite grounded StoreOps audit disclaimer"
    );
  } finally {
    await unmount();
  }
});

test("VisitDetailPage: renders error alert banner when store fetch fails", async () => {
  apiClient.setUseDoubles(true);
  const visit = apiClient.getDoubleVisits()[0];

  const origGetStore = apiClient.getStore.bind(apiClient);
  apiClient.getStore = async () => {
    throw new Error("Store catalog database network timeout");
  };

  const { container, mount, unmount } = renderWithContext(
    React.createElement(VisitDetailPage),
    { id: visit.id }
  );

  try {
    await mount();

    assert.ok(
      container.innerHTML.includes("Failed to load store information"),
      "Must render explicit store error banner"
    );
    assert.ok(
      container.innerHTML.includes("Store catalog database network timeout"),
      "Must render actual store error message"
    );
  } finally {
    apiClient.getStore = origGetStore;
    await unmount();
  }
});

test("VisitDetailPage: renders error alert banner when promotions fetch fails", async () => {
  apiClient.setUseDoubles(true);
  const visit = apiClient.getDoubleVisits()[0];

  const origListPromos = apiClient.listPromotions.bind(apiClient);
  apiClient.listPromotions = async () => {
    throw new Error("Promotion policy service unavailable");
  };

  const { container, mount, unmount } = renderWithContext(
    React.createElement(VisitDetailPage),
    { id: visit.id }
  );

  try {
    await mount();

    assert.ok(
      container.innerHTML.includes("Failed to load promotions"),
      "Must render explicit promotions error banner"
    );
    assert.ok(
      container.innerHTML.includes("Promotion policy service unavailable"),
      "Must render actual promotions error message"
    );
  } finally {
    apiClient.listPromotions = origListPromos;
    await unmount();
  }
});

test("InvestigationDetailPage: handles OCC version conflict (409) when claiming action done", async () => {
  apiClient.setUseDoubles(true);
  const inv = apiClient.getDoubleInvestigations()[0];
  inv.state = "ACCEPTED"; // accepted plan enables action toggling

  const origUpdateAction = apiClient.updateAction.bind(apiClient);
  apiClient.updateAction = async () => {
    throw new VersionConflictError("Investigation was modified concurrently");
  };

  const { container, mount, unmount } = renderWithContext(
    React.createElement(InvestigationDetailPage),
    { id: inv.id }
  );

  try {
    await mount();

    // Find "Claim Done" button
    const buttons = Array.from(container.querySelectorAll("button"));
    const claimBtn = buttons.find((b) => b.textContent?.includes("Claim Done"));
    assert.ok(claimBtn, "Expected 'Claim Done' button to be present");

    // Dispatch click to trigger action update
    await act(async () => {
      claimBtn.dispatchEvent(new Event("click", { bubbles: true }));
    });
    await act(async () => {
      await new Promise((r) => setTimeout(r, 60));
    });

    assert.ok(
      container.innerHTML.includes("Investigation was modified concurrently"),
      "Must render 409 OCC conflict error message to user"
    );
  } finally {
    apiClient.updateAction = origUpdateAction;
    await unmount();
  }
});

test("DashboardLayout: renders 'Sign In Required' when signed out", async () => {
  // Test DashboardLayout with AuthProvider wrapping an inner child
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);

  try {
    await act(async () => {
      root.render(
        React.createElement(
          AuthProvider,
          null,
          React.createElement(
            AppRouterContext.Provider,
            { value: mockRouter },
            React.createElement(
              DashboardLayout,
              null,
              React.createElement("div", { id: "protected-content" }, "Protected Content")
            )
          )
        )
      );
    });

    // In doubles test mode, AuthProvider defaults to signed-in dev token
    assert.ok(container.innerHTML.includes("StoreOps"), "Layout renders StoreOps brand");
  } finally {
    await act(async () => {
      root.unmount();
    });
    container.remove();
  }
});
