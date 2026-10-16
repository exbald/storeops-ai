/**
 * Authentication and Workspace Context for StoreOps Web Shell.
 *
 * Provides:
 * - Current authenticated user details and active workspace
 * - Multi-tenant workspace switcher based on GET /me memberships
 * - Role-based authorization state (ADMIN vs REP), seeded from the server
 *   membership and switchable with the "View as" toggle
 * - Meaningful loading, unauthenticated and unprovisioned state handling
 *
 * In live mode nothing is shown from test doubles: the session stays in a
 * loading state until GET /me returns, and a failed /me is surfaced as an error.
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
  /** Set when GET /me fails in live mode. */
  sessionError?: string | null;
  switchWorkspace: (workspaceId: string) => void;
  setRole: (role: UserRole) => void;
  signOut: () => void;
}

export interface InitialAuthState {
  token: string | null;
  user: { id: string; email: string } | null;
  memberships: Membership[];
  workspaceId: string | null;
  isLoading: boolean;
}

const DOUBLES_DEV_TOKEN = "storeops-dev-session-token";

/**
 * Initial session state before GET /me resolves.
 * Doubles mode seeds the in-memory test-double session; live mode starts empty
 * and loading so no placeholder workspace or role is ever rendered.
 */
export function resolveInitialAuthState(useDoubles: boolean, configuredToken: string | null): InitialAuthState {
  if (useDoubles) {
    const token = configuredToken || DOUBLES_DEV_TOKEN;
    return {
      token,
      user: { id: "usr-admin-001", email: "admin@storeops.local" },
      memberships: MOCK_MEMBERSHIPS,
      workspaceId: DEFAULT_WORKSPACE_ID,
      isLoading: false,
    };
  }
  return {
    token: configuredToken,
    user: null,
    memberships: [],
    workspaceId: null,
    isLoading: configuredToken !== null,
  };
}

/** Picks the membership to activate after GET /me: current, then configured, then first. */
export function chooseMembership(
  memberships: Membership[],
  currentWorkspaceId: string | null,
  preferredWorkspaceId: string | null
): Membership | null {
  return (
    memberships.find((m) => m.workspace_id === currentWorkspaceId) ||
    memberships.find((m) => m.workspace_id === preferredWorkspaceId) ||
    memberships[0] ||
    null
  );
}

function readConfiguredToken(): string | null {
  return (typeof process !== "undefined" ? process.env.NEXT_PUBLIC_AUTH_TOKEN : null) || null;
}

function readConfiguredWorkspaceId(): string | null {
  return (typeof process !== "undefined" ? process.env.NEXT_PUBLIC_WORKSPACE_ID : null) || null;
}

function toUserRole(role: string | undefined): UserRole {
  return role === "REP" ? "REP" : "ADMIN";
}

export const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [initial] = useState(() => resolveInitialAuthState(apiClient.useDoubles, readConfiguredToken()));
  const [token, setToken] = useState<string | null>(initial.token);
  const [user, setUser] = useState<{ id: string; email: string } | null>(initial.user);
  const [memberships, setMemberships] = useState<Membership[]>(initial.memberships);
  const [workspaceId, setWorkspaceId] = useState<string | null>(initial.workspaceId);
  const [role, setRole] = useState<UserRole>("ADMIN");
  const [isLoading, setIsLoading] = useState(initial.isLoading);
  const [sessionError, setSessionError] = useState<string | null>(null);

  // Synchronously prime apiClient singleton so child components can fetch immediately on mount
  if (token && !apiClient.getAuthTokenDirect()) {
    apiClient.setAuthToken(token);
  }
  if (workspaceId) {
    apiClient.setWorkspaceId(workspaceId);
  }

  // Load /me when a token is available; role and workspace come from the server membership.
  useEffect(() => {
    if (!token) {
      setIsLoading(false);
      return;
    }
    let cancelled = false;
    async function loadMe() {
      try {
        const me = await apiClient.getMe();
        if (cancelled) return;
        setUser({ id: me.user_id, email: me.email });
        setMemberships(me.memberships);
        const active = chooseMembership(me.memberships, workspaceId, readConfiguredWorkspaceId());
        if (active) {
          setWorkspaceId(active.workspace_id);
          apiClient.setWorkspaceId(active.workspace_id);
          setRole(toUserRole(active.role));
        }
        setSessionError(null);
      } catch (err) {
        if (cancelled) return;
        console.error("Failed to load user session:", err);
        if (!apiClient.useDoubles) {
          setSessionError(err instanceof Error ? err.message : "Failed to load your workspace session");
        }
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    }
    loadMe();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  // Sync workspaceId and authToken to apiClient singleton
  useEffect(() => {
    if (workspaceId) {
      apiClient.setWorkspaceId(workspaceId);
    }
    apiClient.setAuthToken(token);
  }, [workspaceId, token]);

  const switchWorkspace = useCallback((newId: string) => {
    setWorkspaceId(newId);
    apiClient.setWorkspaceId(newId);
    const m = memberships.find((mem) => mem.workspace_id === newId);
    if (m) {
      setRole(toUserRole(m.role));
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
  const activeWorkspaceName = activeMembership?.workspace_name || (isLoading ? "" : "Select Workspace");
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
        sessionError,
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
