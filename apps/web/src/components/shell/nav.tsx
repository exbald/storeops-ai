"use client";

import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "../../lib/auth-context";

interface NavItem {
  href: string;
  label: string;
  adminOnly?: boolean;
}

const NAV_ITEMS: NavItem[] = [
  { href: "/setup", label: "Setup", adminOnly: true },
  { href: "/stores", label: "Stores", adminOnly: false },
  { href: "/catalog", label: "Catalog & Products", adminOnly: true },
  { href: "/imports", label: "CSV Imports", adminOnly: true },
  { href: "/promotions", label: "Promotions & Policy", adminOnly: true },
];

export function Nav() {
  const pathname = usePathname();
  const { isAdmin } = useAuth();

  return (
    <nav className="bg-white border-b border-gray-200" aria-label="Main Navigation">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex space-x-8 overflow-x-auto py-2 scrollbar-none">
          {NAV_ITEMS.map((item) => {
            const isActive = pathname === item.href || pathname?.startsWith(`${item.href}/`);
            const isRestricted = item.adminOnly && !isAdmin;

            if (isRestricted) {
              return null;
            }

            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={isActive ? "page" : undefined}
                className={`whitespace-nowrap px-3 py-2 text-sm font-medium rounded-md transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 ${
                  isActive
                    ? "bg-blue-50 text-blue-700 font-semibold"
                    : "text-gray-600 hover:text-gray-900 hover:bg-gray-50"
                }`}
              >
                {item.label}
              </Link>
            );
          })}
        </div>
      </div>
    </nav>
  );
}
