"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { apiClient } from "../../../lib/api-client";
import { useAuth } from "../../../lib/auth-context";
import { selectDemoEntryPoints, VALUE_STATEMENT, type DemoEntryPoints } from "../../../lib/demo-entry";
import { Button } from "../../../components/ui/button";

const STEPS = [
  {
    title: "Diagnose",
    body: "Reads the approved vendor agreement, sales and stock data, and the rep's shelf photo to explain what is going wrong.",
  },
  {
    title: "Fix",
    body: "Gives the rep a short list of concrete actions, each tied to the evidence behind it.",
  },
  {
    title: "Verify",
    body: "Checks a new shelf photo against every rule in the agreement and records a pass or fail for each one.",
  },
];

export default function HomePage() {
  const { isAdmin } = useAuth();
  const [entries, setEntries] = useState<DemoEntryPoints | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [visitsRes, invRes] = await Promise.all([
        apiClient.listVisits({ limit: 100 }),
        apiClient.listInvestigations({ limit: 100 }),
      ]);
      setEntries(selectDemoEntryPoints(visitsRes.items, invRes.items));
    } catch (err: unknown) {
      console.error("Failed to load home entry points:", err);
      setError(err instanceof Error ? err.message : "Failed to load visits");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const hasEntry = Boolean(entries?.completedExample || entries?.tryItYourself);

  return (
    <div className="space-y-8">
      <section className="rounded-xl bg-gradient-to-br from-blue-900 via-indigo-900 to-slate-900 text-white p-6 sm:p-10 shadow-lg">
        <p className="text-xs font-semibold uppercase tracking-wider text-blue-200">StoreOps AI</p>
        <h1 className="mt-2 text-2xl sm:text-3xl font-bold leading-tight max-w-3xl">{VALUE_STATEMENT}</h1>

        {loading && (
          <div className="mt-6 flex flex-col sm:flex-row gap-3" aria-busy="true">
            <div className="h-12 w-full sm:w-56 rounded-md bg-white/10 animate-pulse" />
            <div className="h-12 w-full sm:w-56 rounded-md bg-white/10 animate-pulse" />
          </div>
        )}

        {!loading && hasEntry && entries && (
          <div className="mt-6 flex flex-col sm:flex-row gap-3">
            {entries.completedExample && (
              <Link href={entries.completedExample.href} className="w-full sm:w-auto">
                <Button size="lg" className="w-full sm:w-auto bg-emerald-500 hover:bg-emerald-400 text-white font-semibold">
                  See a completed example
                </Button>
              </Link>
            )}
            {entries.tryItYourself && (
              <Link href={entries.tryItYourself.href} className="w-full sm:w-auto">
                <Button size="lg" variant="outline" className="w-full sm:w-auto bg-white text-blue-900 font-semibold hover:bg-blue-50">
                  Try it yourself
                </Button>
              </Link>
            )}
          </div>
        )}
      </section>

      {error && (
        <div role="alert" className="p-4 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <span className="font-semibold">Failed to load visits:</span> {error}
          </div>
          <Button variant="outline" size="sm" onClick={() => load()}>
            Retry
          </Button>
        </div>
      )}

      {!loading && !error && !hasEntry && (
        <div className="p-6 bg-white border border-gray-200 rounded-lg shadow-sm space-y-3">
          <h2 className="text-lg font-semibold text-gray-900">No store visits yet</h2>
          <p className="text-sm text-gray-600">
            {isAdmin
              ? "Set up a store, a product and an approved promotion, then open a store visit to run your first audit."
              : "Ask your admin to finish workspace setup, then open a store visit to run your first audit."}
          </p>
          <Link href={isAdmin ? "/setup" : "/stores"}>
            <Button>{isAdmin ? "Open the setup checklist" : "Go to stores"}</Button>
          </Link>
        </div>
      )}

      <section aria-label="How it works" className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {STEPS.map((step, i) => (
          <div key={step.title} className="p-5 bg-white border border-gray-200 rounded-lg shadow-sm">
            <div className="flex items-center gap-2">
              <span className="w-6 h-6 rounded-full bg-blue-600 text-white text-xs font-bold flex items-center justify-center">
                {i + 1}
              </span>
              <h2 className="text-base font-semibold text-gray-900">{step.title}</h2>
            </div>
            <p className="mt-2 text-sm text-gray-600">{step.body}</p>
          </div>
        ))}
      </section>
    </div>
  );
}
