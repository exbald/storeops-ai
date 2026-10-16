"use client";

import React, { useId, useState } from "react";
import Link from "next/link";
import { useAuth, type UserRole } from "../../lib/auth-context";
import { apiClient } from "../../lib/api-client";

const VIEW_AS_OPTIONS: { value: UserRole; label: string }[] = [
  { value: "ADMIN", label: "Admin" },
  { value: "REP", label: "Rep" },
];

export function ViewAsToggle({ role, onChange }: { role: UserRole; onChange: (role: UserRole) => void }) {
  const labelId = useId();
  return (
    <div className="flex items-center gap-2">
      <span className="text-xs text-gray-500" id={labelId}>
        View as:
      </span>
      <div
        role="group"
        aria-labelledby={labelId}
        className="inline-flex rounded-md border border-gray-300 bg-gray-50 p-0.5"
      >
        {VIEW_AS_OPTIONS.map((opt) => {
          const active = role === opt.value;
          return (
            <button
              key={opt.value}
              type="button"
              aria-pressed={active}
              onClick={() => onChange(opt.value)}
              className={`px-2.5 py-1 text-xs font-medium rounded focus:outline-none focus:ring-2 focus:ring-blue-500 ${
                active ? "bg-white text-blue-700 shadow-sm" : "text-gray-600 hover:text-gray-900"
              }`}
            >
              {opt.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function WorkspaceSwitcher() {
  const { workspaceId, activeWorkspaceName, memberships, switchWorkspace } = useAuth();
  const [isOpen, setIsOpen] = useState(false);

  return (
    <div className="relative min-w-0">
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        aria-expanded={isOpen}
        aria-haspopup="listbox"
        className="inline-flex max-w-full items-center gap-2 px-2 sm:px-3 py-1.5 text-sm font-medium text-gray-700 bg-gray-50 border border-gray-300 rounded-md hover:bg-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
      >
        <span className="hidden sm:inline text-gray-500 text-xs">Workspace:</span>
        <span className="truncate max-w-[110px] sm:max-w-[160px] font-semibold">{activeWorkspaceName}</span>
        <svg
          className="w-4 h-4 shrink-0 text-gray-400"
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

      {isOpen && (
        <div
          role="listbox"
          className="absolute left-0 mt-2 w-64 max-w-[calc(100vw-2rem)] bg-white border border-gray-200 rounded-md shadow-lg py-1 z-50 focus:outline-none"
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
                setIsOpen(false);
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
  );
}

export function Header() {
  const { user, role, memberships, isLoading, setRole, signOut } = useAuth();
  const [isMenuOpen, setIsMenuOpen] = useState(false);

  return (
    <header className="w-full bg-white border-b border-gray-200 sticky top-0 z-40">
      {apiClient.useDoubles && (
        <div className="bg-amber-100 border-b border-amber-300 text-amber-900 text-xs px-4 py-1 text-center font-medium">
          Demo data mode: this screen uses built-in sample records, not the live StoreOps backend.
        </div>
      )}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between gap-3">
        {/* Brand + workspace */}
        <div className="flex items-center gap-3 sm:gap-6 min-w-0">
          <Link
            href="/home"
            className="flex items-center gap-2 shrink-0 focus:outline-none focus:ring-2 focus:ring-blue-500 rounded-md p-1"
          >
            <span className="font-bold text-xl tracking-tight text-blue-600">StoreOps</span>
            <span className="hidden sm:inline text-xs font-semibold px-2 py-0.5 rounded bg-gray-100 text-gray-700">
              AI Operations
            </span>
          </Link>

          {isLoading && (
            <span className="text-xs text-gray-400 animate-pulse truncate">Loading workspace…</span>
          )}
          {!isLoading && user && memberships.length > 0 && <WorkspaceSwitcher />}
        </div>

        {/* Desktop cluster */}
        <div className="hidden md:flex items-center gap-4 shrink-0">
          {user ? (
            <>
              <ViewAsToggle role={role} onChange={setRole} />
              <div className="text-xs text-gray-500 border-l border-gray-200 pl-4">{user.email}</div>
              <button
                type="button"
                onClick={signOut}
                className="text-xs text-gray-600 hover:text-red-600 focus:outline-none focus:ring-2 focus:ring-red-500 rounded p-1"
              >
                Sign out
              </button>
            </>
          ) : (
            !isLoading && (
              <Link
                href="/sign-in"
                className="text-sm font-medium text-blue-600 hover:text-blue-800 focus:outline-none focus:ring-2 focus:ring-blue-500 rounded p-1"
              >
                Sign In
              </Link>
            )
          )}
        </div>

        {/* Mobile menu button */}
        {(user || !isLoading) && (
          <div className="md:hidden shrink-0">
            <button
              type="button"
              aria-expanded={isMenuOpen}
              aria-controls="header-mobile-menu"
              onClick={() => setIsMenuOpen(!isMenuOpen)}
              className="inline-flex items-center gap-1 px-2.5 py-1.5 text-sm font-medium text-gray-700 border border-gray-300 rounded-md bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <svg className="w-4 h-4" width="16" height="16" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 6h16M4 12h16M4 18h16" />
              </svg>
              Menu
            </button>
          </div>
        )}
      </div>

      {isMenuOpen && (
        <div id="header-mobile-menu" className="md:hidden border-t border-gray-200 bg-white px-4 py-3 space-y-3">
          {user ? (
            <>
              <ViewAsToggle role={role} onChange={setRole} />
              <div className="text-xs text-gray-500 break-all">{user.email}</div>
              <button
                type="button"
                onClick={() => {
                  setIsMenuOpen(false);
                  signOut();
                }}
                className="text-sm text-gray-700 hover:text-red-600 focus:outline-none focus:ring-2 focus:ring-red-500 rounded p-1"
              >
                Sign out
              </button>
            </>
          ) : (
            <Link href="/sign-in" className="text-sm font-medium text-blue-600">
              Sign In
            </Link>
          )}
        </div>
      )}
    </header>
  );
}
