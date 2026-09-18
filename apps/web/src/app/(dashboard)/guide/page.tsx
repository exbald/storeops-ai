"use client";

import React, { useState } from "react";
import Link from "next/link";
import { Badge } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";

type SectionTab = "overview" | "problem" | "workflow" | "rep" | "admin" | "metrics";

export default function GuidePage() {
  const [activeTab, setActiveTab] = useState<SectionTab>("overview");
  const [expandedFaq, setExpandedFaq] = useState<number | null>(null);

  const toggleFaq = (index: number) => {
    setExpandedFaq(expandedFaq === index ? null : index);
  };

  return (
    <div className="max-w-6xl mx-auto space-y-8 pb-16">
      {/* Hero Header */}
      <div className="bg-gradient-to-r from-blue-900 via-indigo-900 to-slate-900 rounded-2xl p-8 sm:p-10 text-white shadow-xl relative overflow-hidden">
        <div className="relative z-10 space-y-4 max-w-3xl">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-blue-500/20 border border-blue-400/30 text-blue-200 text-xs font-semibold uppercase tracking-wider">
            <span>Platform & User Handbook</span>
          </div>
          <h1 className="text-3xl sm:text-4xl font-extrabold tracking-tight">
            StoreOps User Guide & Documentation
          </h1>
          <p className="text-blue-100/90 text-base sm:text-lg leading-relaxed">
            Understand what StoreOps is all about, why we built it, how it bridges the gap
            between contractual trade agreements and shelf reality, and how to use it in the field and office.
          </p>
          <div className="flex flex-wrap gap-3 pt-2">
            <Link href="/stores">
              <Button variant="primary" className="bg-blue-600 hover:bg-blue-500 text-white">
                Explore Store Network
              </Button>
            </Link>
            <Link href="/setup">
              <Button
                variant="inverse"
                className="backdrop-blur-sm shadow-sm"
              >
                Workspace Setup Checklist
              </Button>
            </Link>
          </div>
        </div>
      </div>

      {/* Navigation Pills */}
      <div className="flex flex-wrap gap-2 border-b border-gray-200 pb-4">
        {[
          { id: "overview", label: "1. Overview & Vision" },
          { id: "problem", label: "2. The Retail Gap (Why Built)" },
          { id: "workflow", label: "3. How It Works (Workflow)" },
          { id: "rep", label: "4. Field Rep Guide (In Aisle)" },
          { id: "admin", label: "5. Operations Guide (Admin)" },
          { id: "metrics", label: "6. Metrics Guide & FAQ" },
        ].map((tab) => (
          <button
            key={tab.id}
            type="button"
            onClick={() => setActiveTab(tab.id as SectionTab)}
            className={`px-4 py-2 text-sm font-medium rounded-lg transition-all ${
              activeTab === tab.id
                ? "bg-blue-600 text-white shadow-sm font-semibold"
                : "bg-white text-gray-700 border border-gray-200 hover:bg-gray-50"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* TAB 1: OVERVIEW & VISION */}
      {activeTab === "overview" && (
        <div className="space-y-6">
          <div className="bg-white rounded-xl border border-gray-200 p-6 sm:p-8 space-y-6">
            <div className="flex items-center gap-3">
              <span className="p-2.5 rounded-lg bg-blue-50 text-blue-600">
                <svg className="w-6 h-6" width="24" height="24" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
                </svg>
              </span>
              <div>
                <h2 className="text-xl font-bold text-gray-900">What is StoreOps?</h2>
                <p className="text-sm text-gray-500">Autonomous retail operations intelligence platform</p>
              </div>
            </div>

            <p className="text-gray-700 leading-relaxed">
              <strong>StoreOps</strong> is an autonomous intelligence platform built to close the loop between{" "}
              <strong>contractual trade agreements</strong>, <strong>daily sales transactions</strong>,{" "}
              <strong>warehouse supply chains</strong>, and <strong>physical supermarket shelves</strong>.
            </p>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-6 pt-2">
              <div className="bg-blue-50/50 rounded-xl p-5 border border-blue-100 space-y-2">
                <div className="font-semibold text-blue-900 flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-blue-600"></span>
                  Contract to Policy
                </div>
                <p className="text-sm text-gray-600 leading-relaxed">
                  Translates signed vendor PDF agreements into clear, structured, and auditable planogram rules using Gemini AI.
                </p>
              </div>

              <div className="bg-indigo-50/50 rounded-xl p-5 border border-indigo-100 space-y-2">
                <div className="font-semibold text-indigo-900 flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-indigo-600"></span>
                  Autonomous Diagnosis
                </div>
                <p className="text-sm text-gray-600 leading-relaxed">
                  Fuses physical shelf photos, daily POS sales, and backroom stock telemetry to identify the exact root cause of missing sales.
                </p>
              </div>

              <div className="bg-emerald-50/50 rounded-xl p-5 border border-emerald-100 space-y-2">
                <div className="font-semibold text-emerald-900 flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-emerald-600"></span>
                  Multimodal Verification
                </div>
                <p className="text-sm text-gray-600 leading-relaxed">
                  Verifies physical restocking with computer vision before certifying completion. Eliminates fake checkbox compliance.
                </p>
              </div>
            </div>
          </div>

          {/* User Personas */}
          <div className="bg-white rounded-xl border border-gray-200 p-6 sm:p-8 space-y-6">
            <h3 className="text-lg font-bold text-gray-900">Designed for Two Core Roles</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div className="border border-gray-200 rounded-xl p-5 space-y-3">
                <div className="flex items-center justify-between">
                  <h4 className="font-bold text-gray-900">👔 The Operations Lead</h4>
                  <Badge variant="neutral">ADMIN Role</Badge>
                </div>
                <p className="text-sm text-gray-600">
                  Trade marketing leads, brand managers, and commercial operations analysts who manage product master data, upload sales feeds, and approve promotion policies.
                </p>
                <ul className="text-xs text-gray-500 space-y-1.5 list-disc list-inside">
                  <li>Manages store directories & SKU packaging units</li>
                  <li>Uploads daily POS sales & stock snapshots</li>
                  <li>Reviews AI contract extractions & approves policies</li>
                  <li>Monitors commercial opportunity loss across regions</li>
                </ul>
              </div>

              <div className="border border-gray-200 rounded-xl p-5 space-y-3">
                <div className="flex items-center justify-between">
                  <h4 className="font-bold text-gray-900">📱 The Field Representative</h4>
                  <Badge variant="info">REP Role</Badge>
                </div>
                <p className="text-sm text-gray-600">
                  Territory sales reps, field merchandisers, and third-party auditors visiting physical stores with smartphones or tablets.
                </p>
                <ul className="text-xs text-gray-500 space-y-1.5 list-disc list-inside">
                  <li>Opens in-store audit visits on mobile view</li>
                  <li>Snaps shelf baseline &quot;before&quot; photographs</li>
                  <li>Receives instant AI root-cause diagnosis &amp; 3-step action plan</li>
                  <li>Uploads &quot;after&quot; photos for automated computer vision verification</li>
                </ul>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* TAB 2: THE RETAIL EXECUTION GAP */}
      {activeTab === "problem" && (
        <div className="space-y-6">
          <div className="bg-white rounded-xl border border-gray-200 p-6 sm:p-8 space-y-6">
            <h2 className="text-xl font-bold text-gray-900">The Problem: Why We Built StoreOps</h2>
            <p className="text-gray-700 leading-relaxed">
              Consumer Packaged Goods (CPG) brands invest <strong>over 20% of their gross revenue</strong> into retail trade promotions, endcap displays, and slotting fees. Yet on the store floor, execution breaks down dramatically.
            </p>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-6 pt-2">
              <div className="bg-red-50/60 border border-red-200 rounded-xl p-5 space-y-2">
                <div className="font-bold text-red-900 text-sm flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-full bg-red-500"></span>
                  1. The 40%+ Execution Failure Rate
                </div>
                <p className="text-sm text-gray-700">
                  Industry studies show more than 40% of contracted retail promotions are either never set up, executed late, or under-faced on shelves. Brands pay for premium visibility they never receive.
                </p>
              </div>

              <div className="bg-amber-50/60 border border-amber-200 rounded-xl p-5 space-y-2">
                <div className="font-bold text-amber-900 text-sm flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-full bg-amber-500"></span>
                  2. &quot;Phantom Inventory&quot; Trapped in Backrooms
                </div>
                <p className="text-sm text-gray-700">
                  Retailer inventory systems often register items as in-stock, but the product is sitting on an unworked pallet in the backroom. To the shopper, it&apos;s out-of-stock; to the computer, it&apos;s unsold.
                </p>
              </div>

              <div className="bg-slate-50 border border-slate-200 rounded-xl p-5 space-y-2">
                <div className="font-bold text-slate-900 text-sm flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-full bg-slate-500"></span>
                  3. Finger-Pointing &amp; Costly Disputes
                </div>
                <p className="text-sm text-gray-700">
                  When promotions underperform, retailers blame the brand for weak consumer demand; brands blame retailers for non-compliance. Without timestamped photographic evidence, disputes drag on unresolved.
                </p>
              </div>

              <div className="bg-purple-50/60 border border-purple-200 rounded-xl p-5 space-y-2">
                <div className="font-bold text-purple-900 text-sm flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-full bg-purple-500"></span>
                  4. Fake &quot;Checkbox Compliance&quot;
                </div>
                <p className="text-sm text-gray-700">
                  Traditional audit software allows reps to simply tap &quot;Work Completed&quot; on a form without proving physical shelf execution. StoreOps replaces checkboxes with verifiable computer vision.
                </p>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* TAB 3: HOW IT WORKS */}
      {activeTab === "workflow" && (
        <div className="space-y-6">
          <div className="bg-white rounded-xl border border-gray-200 p-6 sm:p-8 space-y-8">
            <div>
              <h2 className="text-xl font-bold text-gray-900">How StoreOps Works: 4-Stage Lifecycle</h2>
              <p className="text-sm text-gray-500 mt-1">From trade agreement to verified shelf execution in 4 steps</p>
            </div>

            <div className="space-y-8">
              {/* Step 1 */}
              <div className="flex gap-4">
                <div className="flex-shrink-0 w-10 h-10 rounded-full bg-blue-600 text-white font-bold flex items-center justify-center text-lg">
                  1
                </div>
                <div className="space-y-2">
                  <h3 className="text-base font-bold text-gray-900">Contract Digitization &amp; Policy Approval</h3>
                  <p className="text-sm text-gray-600 leading-relaxed">
                    Upload your signed vendor trade agreement (PDF). Gemini extracts planogram rules—including minimum facings, mandatory SKUs, and required endcaps—with exact page and quote citations. An administrator reviews the rules and locks in an approved policy version.
                  </p>
                </div>
              </div>

              {/* Step 2 */}
              <div className="flex gap-4">
                <div className="flex-shrink-0 w-10 h-10 rounded-full bg-indigo-600 text-white font-bold flex items-center justify-center text-lg">
                  2
                </div>
                <div className="space-y-2">
                  <h3 className="text-base font-bold text-gray-900">Daily Telemetry Ingestion &amp; Peer Baselines</h3>
                  <p className="text-sm text-gray-600 leading-relaxed">
                    StoreOps ingests daily point-of-sale transactions and inventory balance feeds. The system compares sales velocity against identical peer stores (same format, region, and promotion) to calculate exact commercial opportunity proxies in code/SQL—never guessing numbers.
                  </p>
                </div>
              </div>

              {/* Step 3 */}
              <div className="flex gap-4">
                <div className="flex-shrink-0 w-10 h-10 rounded-full bg-amber-500 text-white font-bold flex items-center justify-center text-lg">
                  3
                </div>
                <div className="space-y-2">
                  <h3 className="text-base font-bold text-gray-900">Autonomous In-Store Investigation</h3>
                  <p className="text-sm text-gray-600 leading-relaxed">
                    When a field rep arrives at a store and takes a shelf photo, the <strong>Investigator Agent</strong> cross-references the photo with POS velocity, backroom inventory, and distributor stock. It pinpoints the exact failure reason (e.g., &quot;Restocking delay: 5 cases in backroom, 0 on shelf&quot;) and generates up to 3 prioritized physical action items.
                  </p>
                </div>
              </div>

              {/* Step 4 */}
              <div className="flex gap-4">
                <div className="flex-shrink-0 w-10 h-10 rounded-full bg-emerald-600 text-white font-bold flex items-center justify-center text-lg">
                  4
                </div>
                <div className="space-y-2">
                  <h3 className="text-base font-bold text-gray-900">Multimodal Visual Verification &amp; Closure</h3>
                  <p className="text-sm text-gray-600 leading-relaxed">
                    The rep restocks the shelf and snaps an &quot;after&quot; photo. The <strong>Execution Verifier</strong> uses computer vision to detect SKUs and count facings. Only when all contractual rules pass is the visit closed with an <strong>Execution Verified</strong> badge and an immutable audit report.
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* TAB 4: FIELD REP GUIDE */}
      {activeTab === "rep" && (
        <div className="space-y-6">
          <div className="bg-white rounded-xl border border-gray-200 p-6 sm:p-8 space-y-6">
            <div className="flex items-center justify-between border-b border-gray-200 pb-4">
              <div>
                <h2 className="text-xl font-bold text-gray-900">Field Representative Quick Start</h2>
                <p className="text-sm text-gray-500">How to conduct an in-store audit using your phone or tablet</p>
              </div>
              <Badge variant="info">REP Mode</Badge>
            </div>

            <div className="space-y-6">
              <div className="p-4 rounded-lg bg-gray-50 border border-gray-200 space-y-2">
                <div className="font-bold text-gray-900 text-sm">Step 1: Arrive at Store &amp; Begin Visit</div>
                <p className="text-sm text-gray-600">
                  Open StoreOps on your mobile browser. Go to <strong>Stores</strong> and select the store you are visiting. Review the recent sales trends and data freshness checklist, then tap <strong>Begin Visit</strong>.
                </p>
              </div>

              <div className="p-4 rounded-lg bg-gray-50 border border-gray-200 space-y-2">
                <div className="font-bold text-gray-900 text-sm">Step 2: Snap &amp; Upload the &quot;Before&quot; Shelf Photo</div>
                <p className="text-sm text-gray-600">
                  Under <strong>Visit Media &amp; Photos</strong>, select the zone (e.g. <em>Shelf</em> or <em>Endcap</em>). Tap <strong>Select &amp; Upload Photo</strong> and capture the brand&apos;s current display. StoreOps automatically normalizes orientation and removes personal location metadata.
                </p>
              </div>

              <div className="p-4 rounded-lg bg-gray-50 border border-gray-200 space-y-2">
                <div className="font-bold text-gray-900 text-sm">Step 3: Trigger the AI Investigation</div>
                <p className="text-sm text-gray-600">
                  Tap <strong>Trigger Investigation</strong> and select the active promotion. Within seconds, StoreOps analyzes the image against store stock and sales data. Read the diagnosis and tap <strong>Accept Action Plan</strong> (up to 3 prioritized tasks).
                </p>
              </div>

              <div className="p-4 rounded-lg bg-gray-50 border border-gray-200 space-y-2">
                <div className="font-bold text-gray-900 text-sm">Step 4: Do the Physical Restocking Work</div>
                <p className="text-sm text-gray-600">
                  Retrieve product cases from the backroom or display area as instructed. Restock the shelf to meet the required facings. In StoreOps, tap <strong>Claim Done</strong> on the completed action tasks.
                </p>
              </div>

              <div className="p-4 rounded-lg bg-gray-50 border border-gray-200 space-y-2">
                <div className="font-bold text-gray-900 text-sm">Step 5: Snap &quot;After&quot; Photo &amp; Verify Execution</div>
                <p className="text-sm text-gray-600">
                  Select photo type <strong>After Photo (Verification)</strong> and upload a clear picture of the restocked shelf. Tap <strong>Request Execution Verification</strong>. The AI verifier inspects the shelf in real-time. Once verified, your visit is closed with a certified audit report!
                </p>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* TAB 5: ADMIN GUIDE */}
      {activeTab === "admin" && (
        <div className="space-y-6">
          <div className="bg-white rounded-xl border border-gray-200 p-6 sm:p-8 space-y-6">
            <div className="flex items-center justify-between border-b border-gray-200 pb-4">
              <div>
                <h2 className="text-xl font-bold text-gray-900">Operations Lead &amp; Admin Guide</h2>
                <p className="text-sm text-gray-500">Master data, CSV imports, and promotion policy management</p>
              </div>
              <Badge variant="neutral">ADMIN Mode</Badge>
            </div>

            <div className="space-y-6">
              <div className="p-4 rounded-lg bg-gray-50 border border-gray-200 space-y-2">
                <div className="font-bold text-gray-900 text-sm">1. Managing Catalog &amp; Packaging Units</div>
                <p className="text-sm text-gray-600">
                  Under <strong>Catalog &amp; Products</strong>, configure distributor hubs and retail stores. Register SKUs with their mandatory <strong>Case Units</strong> factor (e.g. 24 units/case). Case sizes are permanently immutable once transactions occur to protect financial audit trails.
                </p>
              </div>

              <div className="p-4 rounded-lg bg-gray-50 border border-gray-200 space-y-2">
                <div className="font-bold text-gray-900 text-sm">2. Importing Sales &amp; Stock Telemetry</div>
                <p className="text-sm text-gray-600">
                  Under <strong>CSV Imports</strong>, upload daily sales transactions or inventory balances. StoreOps performs real-time validation: if a row contains an unknown store or SKU, it highlights the exact error. Validated feeds are committed to DuckDB/BigQuery in a single atomic transaction.
                </p>
              </div>

              <div className="p-4 rounded-lg bg-gray-50 border border-gray-200 space-y-2">
                <div className="font-bold text-gray-900 text-sm">3. Digitizing Agreements into Approved Policies</div>
                <p className="text-sm text-gray-600">
                  Under <strong>Promotions &amp; Policy</strong>, create a promotion and upload the agreement PDF. Review the AI-extracted rules (min facings, required SKUs, endcaps) alongside exact page citations. Make any edits and click <strong>Approve Policy</strong> to activate version 1.
                </p>
              </div>

              <div className="p-4 rounded-lg bg-gray-50 border border-gray-200 space-y-2">
                <div className="font-bold text-gray-900 text-sm">4. Reviewing Audit Reports for Joint Business Reviews</div>
                <p className="text-sm text-gray-600">
                  Each completed field visit generates a permanent audit report with side-by-side before/after photos, verified bounding boxes, time stamps, and lost opportunity recovery. Use these reports in joint retailer meetings to defend trade investment.
                </p>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* TAB 6: METRICS & FAQ */}
      {activeTab === "metrics" && (
        <div className="space-y-6">
          {/* Honest Metrics Card */}
          <div className="bg-white rounded-xl border border-gray-200 p-6 sm:p-8 space-y-6">
            <h2 className="text-xl font-bold text-gray-900">Understanding What You See on Screen</h2>
            <p className="text-sm text-gray-600">
              StoreOps follows an <strong>honest transparency principle</strong>: we never show guessed numbers, placeholder zeros, or fake statistics.
            </p>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-2">
              <div className="p-4 rounded-lg bg-gray-50 border border-gray-200 space-y-1">
                <div className="font-bold text-gray-900 text-sm">Commercial Opportunity Amount</div>
                <p className="text-xs text-gray-600">
                  The estimated retail revenue lost because this store underperformed identical peer stores during an on-shelf out-of-stock. If fewer than 3 peer stores exist with valid sales, it displays <em>&quot;Insufficient comparison data&quot;</em> rather than guessing.
                </p>
              </div>

              <div className="p-4 rounded-lg bg-gray-50 border border-gray-200 space-y-1">
                <div className="font-bold text-gray-900 text-sm">Data Freshness (FRESH / STALE)</div>
                <p className="text-xs text-gray-600">
                  Indicates whether sales and inventory feeds were uploaded within the last 48 hours. If stale, audits can still proceed, but the investigation notes that telemetry is older.
                </p>
              </div>

              <div className="p-4 rounded-lg bg-gray-50 border border-gray-200 space-y-1">
                <div className="font-bold text-gray-900 text-sm">Stock Unknown</div>
                <p className="text-xs text-gray-600">
                  Indicates that no stock balance feed has been uploaded for this specific backroom or distributor location. StoreOps does not assume zero stock.
                </p>
              </div>

              <div className="p-4 rounded-lg bg-gray-50 border border-gray-200 space-y-1">
                <div className="font-bold text-gray-900 text-sm">Execution Verified Badge</div>
                <p className="text-xs text-gray-600">
                  Appears only when computer vision confirms that 100% of contractual rules (facings, SKUs, display) are met in the &quot;after&quot; photo.
                </p>
              </div>
            </div>
          </div>

          {/* FAQ Accordion */}
          <div className="bg-white rounded-xl border border-gray-200 p-6 sm:p-8 space-y-4">
            <h3 className="text-lg font-bold text-gray-900">Frequently Asked Questions</h3>

            {[
              {
                q: "Does StoreOps replace human sales reps?",
                a: "No. StoreOps empowers human reps by doing the heavy cognitive analysis for them. Instead of analyzing spreadsheets or searching through contract binders, reps receive an immediate diagnosis and clear action items so they can focus on merchandising and retailer relationships.",
              },
              {
                q: "What if a store has poor mobile internet connectivity?",
                a: "StoreOps is built with resilient optimistic state management. Data is staged securely in the mobile client, and network retries are handled gracefully. Uploads and status changes are guaranteed not to duplicate.",
              },
              {
                q: "Can a rep cheat by submitting the same photo twice?",
                a: "No. StoreOps computes cryptographic visual hashes on all uploaded media. If an after-photo is identical or near-identical to the before-photo, the system rejects it immediately with a 'Reused Before Media' error.",
              },
              {
                q: "What if an after-photo is blurry or taken in bad lighting?",
                a: "The verification agent will return 'INCONCLUSIVE' with clear guidance on what was obstructed (e.g., 'Glare obscured top shelf facings'), prompting the rep to take a clearer shot before leaving.",
              },
              {
                q: "How are promotional rules extracted from vendor contracts?",
                a: "When an agreement PDF is uploaded, Gemini reads the document text and extracts proposed rules along with exact page numbers and quotes. A human manager must review and approve the policy before any rules take effect.",
              },
            ].map((faq, i) => (
              <div key={i} className="border border-gray-200 rounded-lg overflow-hidden">
                <button
                  type="button"
                  onClick={() => toggleFaq(i)}
                  className="w-full text-left px-4 py-3 bg-gray-50 hover:bg-gray-100 flex items-center justify-between text-sm font-semibold text-gray-900 transition"
                >
                  <span>{faq.q}</span>
                  <span className="text-gray-500 font-mono text-base">{expandedFaq === i ? "−" : "+"}</span>
                </button>
                {expandedFaq === i && (
                  <div className="px-4 py-3 bg-white text-sm text-gray-600 leading-relaxed border-t border-gray-200">
                    {faq.a}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
