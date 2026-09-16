"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "../../../lib/auth-context";
import { Button } from "../../../components/ui/button";
import { Input } from "../../../components/ui/input";

export default function SignInPage() {
  const router = useRouter();
  const { user, isUnprovisioned, memberships, switchWorkspace, workspaceId } = useAuth();
  const [email, setEmail] = useState("admin@storeops.local");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSignIn = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    // Simulating Firebase Auth Token exchange
    setTimeout(() => {
      setIsSubmitting(false);
      router.push("/setup");
    }, 400);
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 py-12 px-4 sm:px-6 lg:px-8">
      <div className="max-w-md w-full space-y-8 bg-white p-8 rounded-lg shadow-md border border-gray-200">
        <div className="text-center">
          <h1 className="text-3xl font-extrabold text-blue-600">StoreOps</h1>
          <h2 className="mt-2 text-xl font-semibold text-gray-900">Sign in to your workspace</h2>
          <p className="mt-1 text-sm text-gray-500">
            Enterprise authentication via Firebase Identity Platform
          </p>
        </div>

        {isUnprovisioned ? (
          <div
            className="rounded-md bg-amber-50 p-4 border border-amber-200"
            role="alert"
            aria-live="polite"
          >
            <div className="flex">
              <div className="ml-3">
                <h3 className="text-sm font-medium text-amber-800">Account Not Provisioned</h3>
                <div className="mt-2 text-sm text-amber-700">
                  <p>
                    Your account has been authenticated, but you are not assigned to any workspace.
                    Please contact your system administrator to provision access.
                  </p>
                </div>
              </div>
            </div>
          </div>
        ) : user && memberships.length > 0 ? (
          <div className="space-y-4">
            <div className="rounded-md bg-blue-50 p-4 border border-blue-200">
              <p className="text-sm text-blue-800">
                Signed in as <span className="font-semibold">{user.email}</span>
              </p>
            </div>

            <div>
              <label htmlFor="workspace-select" className="block text-sm font-medium text-gray-700">
                Select Workspace
              </label>
              <select
                id="workspace-select"
                value={workspaceId || ""}
                onChange={(e) => switchWorkspace(e.target.value)}
                className="mt-1 block w-full pl-3 pr-10 py-2 text-base border-gray-300 focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm rounded-md"
              >
                {memberships.map((m) => (
                  <option key={m.workspace_id} value={m.workspace_id}>
                    {m.workspace_name || m.workspace_id} ({m.role})
                  </option>
                ))}
              </select>
            </div>

            <Button
              type="button"
              className="w-full"
              onClick={() => router.push("/setup")}
            >
              Continue to Workspace
            </Button>
          </div>
        ) : (
          <form className="mt-8 space-y-6" onSubmit={handleSignIn}>
            <div className="space-y-4">
              <Input
                label="Corporate Email"
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="representative@retailer.com"
                helperText="Federated single sign-on with your enterprise Google / Firebase identity."
              />
            </div>

            <Button
              type="submit"
              className="w-full"
              isLoading={isSubmitting}
            >
              Sign In with Firebase
            </Button>
          </form>
        )}
      </div>
    </div>
  );
}
