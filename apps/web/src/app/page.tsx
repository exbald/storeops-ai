"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "../lib/auth-context";

export default function RootPage() {
  const router = useRouter();
  const { user, isUnprovisioned, isAdmin } = useAuth();

  useEffect(() => {
    if (!user) {
      router.replace("/sign-in");
    } else if (isUnprovisioned) {
      router.replace("/sign-in");
    } else if (isAdmin) {
      router.replace("/setup");
    } else {
      router.replace("/stores");
    }
  }, [user, isUnprovisioned, isAdmin, router]);

  return (
    <div className="flex items-center justify-center min-h-screen">
      <p className="text-sm text-gray-500 animate-pulse">Redirecting to workspace...</p>
    </div>
  );
}
