/**
 * Authentication and Workspace Context for StoreOps Web Shell.
 *
 * Provides:
 * - Current authenticated user details and active workspace
 * - Multi-tenant workspace switcher based on GET /me memberships
 * - Role-based authorization state (ADMIN vs REP)
 * - Meaningful unauthenticated and unprovisioned state handling
 */

"use client";

import React, { createContext, useContext, useState, useEffect, useCallback } from "react";
import type { Membership } from "@storeops/contracts";
import { apiClient } from "./api-client";
import { MOCK_MEMBERSHIPS, DEFAULT_WORKSPACE_ID } from "./doubles";

export type UserRole = "ADMIN" | "REP";

export interface AuthContextType {
  user: { id: string; email: string } | null;
  token: string | null;
  role: UserRole;
  workspaceId: string | null;
  activeWorkspaceName: string;
  memberships: Membership[];
  isAdmin: boolean;
  isRep: boolean;
  isLoading: boolean;
  isUnprovisioned: boolean;
  switchWorkspace: (workspaceId: string) => void;
  setRole: (role: UserRole) => void;
  signOut: () => void;
}

const isDoublesMode =
  typeof process !== "undefined" && process.env.NEXT_PUBLIC_USE_DOUBLES === "true";
const configuredToken =
  (typeof process !== "undefined" ? process.env.NEXT_PUBLIC_AUTH_TOKEN : null) || null;

// In live mode (NEXT_PUBLIC_USE_DOUBLES !== "true"), hardcoded fallback tokens are strictly disabled.
// Live deployments require NEXT_PUBLIC_AUTH_TOKEN or explicit user authentication.
const DEFAULT_AUTH_TOKEN =
  configuredToken || (isDoublesMode ? "storeops-dev-session-token" : null);

export const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [token, setToken] = useState<string | null>(DEFAULT_AUTH_TOKEN);
  const [user, setUser] = useState<{ id: string; email: string } | null>(
    DEFAULT_AUTH_TOKEN
      ? { id: "usr-admin-001", email: "admin@storeops.local" }
      : null
  );
  const [memberships, setMemberships] = useState<Membership[]>(
    DEFAULT_AUTH_TOKEN ? MOCK_MEMBERSHIPS : []
  );
  const [workspaceId, setWorkspaceId] = useState<string | null>(
    DEFAULT_WORKSPACE_ID
  );
  const [role, setRole] = useState<UserRole>("ADMIN");
  const [isLoading, setIsLoading] = useState(false);

  // Synchronously prime apiClient singleton so child components can fetch immediately on mount
  if (token && !apiClient.getAuthTokenDirect()) {
    apiClient.setAuthToken(token);
  }
  if (workspaceId) {
    apiClient.setWorkspaceId(workspaceId);
  }

  // Initialize or fetch /me when token is available
  useEffect(() => {
    async function loadMe() {
      if (!token) return;
      try {
        const me = await apiClient.getMe();
        setUser({ id: me.user_id, email: me.email });
        setMemberships(me.memberships);
        if (me.memberships.length > 0 && !workspaceId) {
          setWorkspaceId(me.memberships[0].workspace_id);
          setRole((me.memberships[0].role as UserRole) || "ADMIN");
        }
      } catch (err) {
        console.error("Failed to load user session:", err);
      }
    }
    loadMe();
  }, [token]);

  // Sync workspaceId and authToken to apiClient singleton
  useEffect(() => {
    apiClient.setWorkspaceId(workspaceId || DEFAULT_WORKSPACE_ID);
    apiClient.setAuthToken(token);
  }, [workspaceId, token]);

  const switchWorkspace = useCallback((newId: string) => {
    setWorkspaceId(newId);
    apiClient.setWorkspaceId(newId);
    const m = memberships.find((mem) => mem.workspace_id === newId);
    if (m) {
      setRole((m.role as UserRole) || "ADMIN");
    }
  }, [memberships]);

  const signOut = useCallback(() => {
    setUser(null);
    setWorkspaceId(null);
    setMemberships([]);
    setToken(null);
    apiClient.setWorkspaceId(null);
    apiClient.setAuthToken(null);
  }, []);

  const activeMembership = memberships.find((m) => m.workspace_id === workspaceId);
  const activeWorkspaceName = activeMembership?.workspace_name || "Select Workspace";
  const isUnprovisioned = user !== null && memberships.length === 0;
  const isAdmin = role === "ADMIN";
  const isRep = role === "REP" || role === "ADMIN"; // ADMIN has REP capabilities per contracts/SEMANTICS.md:10

  return (
    <AuthContext.Provider
      value={{
        user,
        role,
        workspaceId,
        token,
        activeWorkspaceName,
        memberships,
        isAdmin,
        isRep,
        isLoading,
        isUnprovisioned,
        switchWorkspace,
        setRole,
        signOut,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextType {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
