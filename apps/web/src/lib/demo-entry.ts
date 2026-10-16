/**
 * Chooses the two landing-page entry points from real workspace records:
 * - a completed example: the investigation attached to a CLOSED visit
 * - a hands-on visit: an OPEN visit, preferring one with a before photo ready
 *
 * Returns null for an entry point the workspace cannot back with data.
 */

import type { Investigation, Visit } from "@storeops/contracts";

export const VALUE_STATEMENT =
  "StoreOps finds why a promotion is failing in a store, helps the rep fix it, and verifies the fix from shelf photos.";

export interface DemoEntryPoints {
  completedExample: { visitId: string; investigationId: string; href: string } | null;
  tryItYourself: { visitId: string; href: string } | null;
}

const RESOLVED_FIRST: Record<string, number> = {
  RESOLVED: 0,
  NEEDS_WORK: 1,
  VERIFYING: 2,
  ACCEPTED: 3,
  PROPOSED: 4,
};

function byNewest(a: { created_at: string }, b: { created_at: string }): number {
  return b.created_at.localeCompare(a.created_at);
}

function stateRank(inv: Investigation): number {
  return RESOLVED_FIRST[inv.state] ?? 10;
}

function investigationsForVisit(visit: Visit, investigations: Investigation[]): Investigation[] {
  return investigations.filter(
    (inv) => inv.visit_id === visit.id || inv.id === visit.active_investigation_id
  );
}

function pickCompletedExample(
  visits: Visit[],
  investigations: Investigation[]
): DemoEntryPoints["completedExample"] {
  const candidates = visits
    .filter((v) => v.status === "CLOSED")
    .flatMap((visit) => investigationsForVisit(visit, investigations).map((inv) => ({ visit, inv })));

  if (candidates.length === 0) return null;

  const [best] = [...candidates].sort((a, b) => {
    const verifiedDiff = Number(Boolean(b.inv.latest_verification_id)) - Number(Boolean(a.inv.latest_verification_id));
    if (verifiedDiff !== 0) return verifiedDiff;
    const rankDiff = stateRank(a.inv) - stateRank(b.inv);
    if (rankDiff !== 0) return rankDiff;
    return byNewest(a.inv, b.inv);
  });

  return {
    visitId: best.visit.id,
    investigationId: best.inv.id,
    href: `/investigations/${best.inv.id}`,
  };
}

function pickTryItYourself(visits: Visit[]): DemoEntryPoints["tryItYourself"] {
  const open = visits.filter((v) => v.status === "OPEN");
  if (open.length === 0) return null;

  const [best] = [...open].sort((a, b) => {
    const photoDiff = Number(b.before_media_ids.length > 0) - Number(a.before_media_ids.length > 0);
    if (photoDiff !== 0) return photoDiff;
    return byNewest(a, b);
  });

  return { visitId: best.id, href: `/visits/${best.id}` };
}

export function selectDemoEntryPoints(visits: Visit[], investigations: Investigation[]): DemoEntryPoints {
  return {
    completedExample: pickCompletedExample(visits, investigations),
    tryItYourself: pickTryItYourself(visits),
  };
}
