import test from "node:test";
import assert from "node:assert/strict";
import {
  formatSales,
  formatRevenue,
  formatStock,
  formatOpportunityProxy,
  formatFreshness,
} from "../src/lib/formatters.ts";

test("formatSales handles null as 'No sales data'", () => {
  assert.equal(formatSales(null), "No sales data");
  assert.equal(formatSales(undefined), "No sales data");
  assert.equal(formatSales(150), "150 units");
});

test("formatRevenue handles null as 'No sales data'", () => {
  assert.equal(formatRevenue(null), "No sales data");
  assert.equal(formatRevenue(undefined), "No sales data");
  assert.match(formatRevenue(1234.5), /SGD/);
});

test("formatStock handles null as 'Stock unknown'", () => {
  assert.equal(formatStock(null), "Stock unknown");
  assert.equal(formatStock(undefined), "Stock unknown");
  assert.equal(formatStock(50), "50 units");
});

test("formatOpportunityProxy handles null as 'Insufficient comparison data'", () => {
  assert.equal(formatOpportunityProxy(null), "Insufficient comparison data");
  assert.equal(formatOpportunityProxy(undefined), "Insufficient comparison data");
  assert.match(formatOpportunityProxy(5400), /SGD/);
});

test("formatFreshness parses valid ISO dates", () => {
  assert.equal(formatFreshness(null), "Unknown");
  const formatted = formatFreshness("2026-09-16T12:00:00Z");
  assert.ok(formatted.length > 0);
});
