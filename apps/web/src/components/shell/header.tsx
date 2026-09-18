"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useAuth } from "../../lib/auth-context";
import { apiClient } from "../../lib/api-client";
import { Badge } from "../ui/badge";

export function Header() {
  const {
    user,
    role,
    workspaceId,
    activeWorkspaceName,
    memberships,
    switchWorkspace,
    setRole,
    signOut,
  } = useAuth();

  const [isWorkspaceOpen, setIsWorkspaceOpen] = useState(false);

  return (
    <header className="w-full bg-white border-b border-gray-200 sticky top-0 z-40">
      {apiClient.useDoubles && (
        <div className="bg-amber-100 border-b border-amber-300 text-amber-900 text-xs px-4 py-1 text-center font-medium">
          [TEST DOUBLE MODE] Running in-memory doubles per AC-38. Real backend integration occurs in Wave 4 (T08).
        </div>
      )}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        {/* Brand */}
        <div className="flex items-center gap-6">
          <Link
            href="/setup"
            className="flex items-center gap-2 focus:outline-none focus:ring-2 focus:ring-blue-500 rounded-md p-1"
          >
            <span className="font-bold text-xl tracking-tight text-blue-600">StoreOps</span>
            <span className="text-xs font-semibold px-2 py-0.5 rounded bg-gray-100 text-gray-700">
              AI Operations
            </span>
          </Link>

          {/* Workspace Switcher */}
          {user && memberships.length > 0 && (
            <div className="relative">
              <button
                type="button"
                onClick={() => setIsWorkspaceOpen(!isWorkspaceOpen)}
                aria-expanded={isWorkspaceOpen}
                aria-haspopup="listbox"
                className="inline-flex items-center gap-2 px-3 py-1.5 text-sm font-medium text-gray-700 bg-gray-50 border border-gray-300 rounded-md hover:bg-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <span className="text-gray-500 text-xs">Workspace:</span>
                <span className="truncate max-w-[160px] font-semibold">{activeWorkspaceName}</span>
                <svg
                  className="w-4 h-4 text-gray-400"
                  width="16"
                  height="16"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                  aria-hidden="true"
                >
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7" />
                </svg>
              </button>

              {isWorkspaceOpen && (
                <div
                  role="listbox"
                  className="absolute left-0 mt-2 w-64 bg-white border border-gray-200 rounded-md shadow-lg py-1 z-50 focus:outline-none"
                >
                  <div className="px-3 py-2 text-xs font-semibold text-gray-400 uppercase tracking-wider border-b border-gray-100">
                    Switch Workspace
                  </div>
                  {memberships.map((m) => (
                    <button
                      key={m.workspace_id}
                      role="option"
                      aria-selected={m.workspace_id === workspaceId}
                      onClick={() => {
                        switchWorkspace(m.workspace_id);
                        setIsWorkspaceOpen(false);
                      }}
                      className={`w-full text-left px-4 py-2 text-sm flex items-center justify-between hover:bg-gray-50 ${
                        m.workspace_id === workspaceId ? "bg-blue-50 text-blue-700 font-medium" : "text-gray-700"
                      }`}
                    >
                      <span className="truncate">{m.workspace_name || m.workspace_id}</span>
                      <span className="text-xs px-1.5 py-0.5 rounded bg-gray-100 text-gray-600 uppercase font-mono">
                        {m.role}
                      </span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        {/* User Info & Role Simulation */}
        <div className="flex items-center gap-4">
          {user ? (
            <>
              {/* Role Toggle for testing / dev convenience */}
              <div className="flex items-center gap-2">
                <span className="text-xs text-gray-500">Role:</span>
                <Badge variant={role === "ADMIN" ? "info" : "neutral"} labelPrefix="User Role:">
                  {role}
                </Badge>
                <button
                  type="button"
                  onClick={() => setRole(role === "ADMIN" ? "REP" : "ADMIN")}
                  className="text-xs text-blue-600 hover:text-blue-800 underline focus:outline-none focus:ring-1 focus:ring-blue-500 rounded px-1"
                  title="Dev simulation: Toggle between ADMIN and REP to verify UI authorization controls"
                >
                  [Dev Sim: Switch to {role === "ADMIN" ? "REP" : "ADMIN"}]
                </button>
              </div>

              <div className="hidden sm:block text-xs text-gray-500 border-l border-gray-200 pl-4">
                {user.email}
              </div>

              <button
                type="button"
                onClick={signOut}
                className="text-xs text-gray-600 hover:text-red-600 focus:outline-none focus:ring-2 focus:ring-red-500 rounded p-1"
              >
                Sign out
              </button>
            </>
          ) : (
            <Link
              href="/sign-in"
              className="text-sm font-medium text-blue-600 hover:text-blue-800 focus:outline-none focus:ring-2 focus:ring-blue-500 rounded p-1"
            >
              Sign In
            </Link>
          )}
        </div>
      </div>
    </header>
  );
}
