# Project Operational Rules & Sub-Agent Team Protocol

This project is a modern **Next.js** application. To ensure enterprise-grade code quality, architectural consistency, and security, operations should adhere to the following guidelines and sub-agent team protocols.

---

## 1. Sub-Agent Roster & Delegation Protocol

When tackling complex workflows, the lead agent delegates specialized responsibilities to dedicated sub-agents:

| Agent Name | Role | Model Tier | Write Access | Workspace Mode | Primary Responsibility |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`security-reviewer`** | AppSec & Code Reviewer | `pro` | **Read-only** | `inherit` | Audits diffs, PRs, Server Actions, auth checks, and OWASP Top 10 vulnerabilities before merging code. |
| **`qa-engineer`** | Test & Quality Specialist | `pro` | **Write + Exec** | `branch` | Writes unit, component, API, and E2E tests (Vitest, RTL, Playwright). Runs test suites in isolated branches. |
| **`debugger`** | Next.js Fullstack Debugger | `pro` | **Write + Exec** | `inherit` | Diagnoses hydration errors, RSC boundary serialization bugs, cache invalidation issues, and runtime panics. |
| **`architect`** | System & App Router Architect | `pro` | **Read-only** | `inherit` | Designs route hierarchies, Data Access Layer (DAL), Prisma/Drizzle schemas, and RFC/ADRs. |
| **`doc-writer`** | Technical & API Doc Writer | `flash` | **Write (Docs)** | `inherit` | Maintains API references, Server Action docs, environment schemas, and developer onboarding runbooks. |

### Delegation Rules:
1. **Never merge major features without review**: Invoke `security-reviewer` to audit any new routes, database queries, or Server Actions.
2. **Isolate test development**: When delegating heavy test suite generation or fixing failing tests, spawn `qa-engineer` with `Workspace: 'branch'` to prevent polluting the active working tree until tests are passing.
3. **Plan before building**: For architectural shifts, database schema migrations, or new App Router patterns, consult `architect` first.
4. **Subagent Skills**: Each sub-agent has a dedicated runbook located in `.agents/skills/<agent-name>/SKILL.md`.

---

## 2. Next.js App Router Engineering Standards

### A. Component Boundaries & Rendering
* **Default to Server Components (RSC)**: Keep components on the server unless client-side interactivity (`useState`, `useEffect`, event listeners) or browser APIs are required.
* **Push Client Boundaries to Leaves**: Never mark an entire page or layout as `"use client"`. Encapsulate interactivity in small leaf components and pass server-rendered children.
* **Serialization Boundary Safety**: Never pass non-serializable objects (functions, class instances, complex prototypes) across the RSC-to-Client boundary.

### B. Data Fetching & Data Access Layer (DAL)
* **Centralized DAL**: Do not execute raw database queries or ORM calls directly inside UI presentation components. Encapsulate queries in `lib/dal/` or `server/data-access/`.
* **Security & Auth Verification**: Validate user authentication and role permissions inside each Server Action or DAL function. Never rely solely on client-side state or route middleware for data mutation security.
* **Input Validation**: Every Server Action and API Route Handler (`route.ts`) MUST validate incoming inputs using **Zod** or equivalent schema validation before processing.

### C. Performance & Caching
* **Explicit Caching**: Be explicit with Next.js caching semantics (`force-dynamic`, `revalidateTag`, `unstable_cache`). Avoid accidental stale data caching in dynamic store operations.
* **Streaming & Suspense**: Wrap asynchronous data-fetching components in `<Suspense fallback={<Skeleton />}>` to enable incremental streaming.

---

## 3. Tool Execution & Environment Safety
* Never commit secrets or credentials. All environment variables must be registered in `.env.example`.
* Private server credentials must never start with `NEXT_PUBLIC_`.
* Use `import 'server-only'` in data access modules and secrets utilities to prevent accidental leakage into client bundles.
