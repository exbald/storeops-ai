"use client";

import React from "react";
import { usePathname } from "next/navigation";
import Link from "next/link";
import { Header } from "../../components/shell/header";
import { Nav } from "../../components/shell/nav";
import { useAuth } from "../../lib/auth-context";
import { Button } from "../../components/ui/button";

const ADMIN_RESTRICTED_PREFIXES = ["/setup", "/catalog", "/imports", "/promotions"];

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const { user, token, isAdmin, isLoading } = useAuth();

  // Explicit signed-out state: If not loading and missing user or token, require authentication
  if (!isLoading && (!user || !token)) {
    return (
      <div className="min-h-screen flex flex-col bg-gray-50">
        <Header />
        <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6">
          <div
            role="alert"
            className="p-8 bg-white border border-amber-200 rounded-lg shadow-sm text-center max-w-lg mx-auto my-12"
          >
            <div className="w-12 h-12 mx-auto mb-4 bg-amber-100 text-amber-600 rounded-full flex items-center justify-center font-bold text-xl">
              !
            </div>
            <h2 className="text-xl font-bold text-gray-900">Sign In Required</h2>
            <p className="text-sm text-gray-600 mt-2">
              You are currently signed out or your session has expired. Please sign in to access StoreOps operations.
            </p>
          </div>
        </main>
      </div>
    );
  }

  const isRestricted =
    ADMIN_RESTRICTED_PREFIXES.some((prefix) => pathname?.startsWith(prefix)) && !isAdmin;

  return (
    <div className="min-h-screen flex flex-col bg-gray-50">
      <Header />
      <Nav />
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {isRestricted ? (
          <div
            role="alert"
            className="p-8 bg-white border border-red-200 rounded-lg shadow-sm text-center max-w-lg mx-auto my-12"
          >
            <div className="w-12 h-12 mx-auto mb-4 bg-red-100 text-red-600 rounded-full flex items-center justify-center font-bold text-xl">
              !
            </div>
            <h2 className="text-xl font-bold text-gray-900">Access Restricted</h2>
            <p className="text-sm text-gray-600 mt-2">
              The screen at <code className="font-mono text-xs bg-gray-100 px-1 py-0.5 rounded">{pathname}</code> requires{" "}
              <strong>ADMIN</strong> privileges. Your active role in this workspace is <strong>REP</strong>.
            </p>
            <div className="mt-6 flex justify-center gap-4">
              <Link href="/stores">
                <Button>Return to Stores</Button>
              </Link>
            </div>
          </div>
        ) : (
          children
        )}
      </main>
    </div>
  );
}
