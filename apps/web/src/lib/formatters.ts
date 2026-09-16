/**
 * Presentation formatters strictly adhering to specs/04-ui.md:
 * - No sales is “No sales data”, not zero sales.
 * - Missing stock is “Stock unknown”, not out of stock.
 * - A null opportunity proxy is “Insufficient comparison data”, not SGD 0.00.
 * - Distributor and store stock always have separate labels.
 */

export function formatSales(units: number | null | undefined): string {
  if (units === null || units === undefined) {
    return "No sales data";
  }
  return `${units.toLocaleString()} units`;
}

export function formatRevenue(revenue: number | null | undefined, currency = "SGD"): string {
  if (revenue === null || revenue === undefined) {
    return "No sales data";
  }
  return new Intl.NumberFormat("en-SG", {
    style: "currency",
    currency,
    currencyDisplay: "code",
  }).format(revenue);
}

export function formatStock(units: number | null | undefined): string {
  if (units === null || units === undefined) {
    return "Stock unknown";
  }
  return `${units.toLocaleString()} units`;
}

export function formatOpportunityProxy(
  opportunityAmount: number | null | undefined,
  currency = "SGD"
): string {
  if (opportunityAmount === null || opportunityAmount === undefined) {
    return "Insufficient comparison data";
  }
  return new Intl.NumberFormat("en-SG", {
    style: "currency",
    currency,
    currencyDisplay: "code",
  }).format(opportunityAmount);
}

export function formatFreshness(timestamp: string | null | undefined): string {
  if (!timestamp) return "Unknown";
  try {
    const d = new Date(timestamp);
    return d.toLocaleString("en-SG", {
      dateStyle: "short",
      timeStyle: "short",
    });
  } catch {
    return timestamp;
  }
}
