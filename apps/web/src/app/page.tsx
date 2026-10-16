"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "../lib/auth-context";

export default function RootPage() {
  const router = useRouter();
  const { user, isUnprovisioned, isLoading } = useAuth();

  useEffect(() => {
    if (isLoading) return;
    if (!user || isUnprovisioned) {
      router.replace("/sign-in");
    } else {
      router.replace("/home");
    }
  }, [user, isUnprovisioned, isLoading, router]);

  return (
    <div className="flex items-center justify-center min-h-screen">
      <p className="text-sm text-gray-500 animate-pulse">Loading workspace…</p>
    </div>
  );
}
