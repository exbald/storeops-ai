# StoreOps · Specification-Driven MVP

StoreOps is an autonomous retail operations intelligence platform. Starting from an empty deployment, StoreOps ingests retail store catalogs, sales/stock CSVs, extracts merchandising rules from vendor agreements via Gemini AI, investigates audit visits, and verifies shelf compliance using multimodal computer vision.

---

## 🚀 Quick Start for Developers & Coding Agents

Follow these steps when cloning this repository to a new development machine:

### 1. Prerequisites
Ensure the following runtimes and tools are installed:
* **Python 3.11+** with [`uv`](https://docs.astral.sh/uv/) (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
* **Node.js 20+** with [`pnpm`](https://pnpm.io/) (`corepack enable && corepack prepare pnpm@latest --activate`)
* *(Optional for live cloud deployment)*: `gcloud`, `firebase-tools`, `terraform`

### 2. Environment Setup
Copy the example environment configuration:
```bash
cp .env.example .env.local
```

Populate the required secrets in `.env.local`:
* **`GEMINI_API_KEY`**: Obtain from [Google AI Studio](https://aistudio.google.com/app/apikey).
* **`GOOGLE_APPLICATION_CREDENTIALS`**: Path to your Google Cloud service account JSON key (e.g. `./service-account.json`).

> [!NOTE]
> `.env`, `.env.local`, and all `*service-account*.json` / `*credentials*.json` files are strictly gitignored to guarantee zero credential leakage to public repositories.

### 3. Install Dependencies
```bash
# Install Python backend dependencies into virtual environment
uv sync

# Install Node.js frontend workspace dependencies
pnpm install
```

### 4. Verify Spec & Run Tests
Verify specification integrity and link graph:
```bash
python3 tools/verify_spec.py
```

Run test suite:
```bash
uv run pytest
```

### 5. Start Local Development Server
```bash
# Start FastAPI backend
uv run uvicorn apps.api.main:app --reload --port 8000
```

---

## 🤖 Instructions for AI Coding Agents

When continuing development on a new machine:
1. **Read Core Protocols First**: Read [AGENTS.md](AGENTS.md), [specs/01-architecture.md](specs/01-architecture.md), and [contracts/openapi.json](contracts/openapi.json).
2. **Consult the Wave Plan**:
   * Current milestone: **Wave 1 (`T01`)** in [`prompts/waves/wave-01-t01.md`](prompts/waves/wave-01-t01.md).
   * Task definitions and acceptance criteria: [`plan/tasks.json`](plan/tasks.json) and [`plan/acceptance.json`](plan/acceptance.json).
3. **Design Tokens & UI**:
   * Pre-generated Stitch design tokens are locked in [`DESIGN.md`](DESIGN.md). Use these directly for `T05` without re-generating tokens.
4. **Autonomous Cloud Integration**:
   * Profile `LOCAL`: Runs in-memory state repository, local file system storage, and DuckDB analytics without external network calls.
   * Profile `CLOUD`: Connects to live Firestore, Cloud Storage, BigQuery, and Cloud Run using `service-account.json` credentials.

---

## 📚 Specification & Contract Directory

| File | Purpose |
|---|---|
| [AGENTS.md](AGENTS.md) | Binding working procedure for implementation agents |
| [DESIGN.md](DESIGN.md) | Dual-mode Obsidian & Ice Glass design tokens and UI specs |
| [specs/00-product.md](specs/00-product.md) | Required behavior and the definition of a complete MVP |
| [specs/01-architecture.md](specs/01-architecture.md) | Components, local/cloud profiles and adapter interfaces |
| [specs/02-domain.md](specs/02-domain.md) | Persistent entities, ownership, imports and temporal semantics |
| [specs/03-workflows.md](specs/03-workflows.md) | State transitions, atomicity, retries and concurrent edits |
| [specs/04-ui.md](specs/04-ui.md) | Screens, empty states, actions and error behavior |
| [specs/05-ai.md](specs/05-ai.md) | Two agents, tools, observations, grounding and model settings |
| [specs/06-quality.md](specs/06-quality.md) | Tests during implementation, live evaluations and release gates |
| [specs/07-delivery.md](specs/07-delivery.md) | Commands to implement, deployment and operational acceptance |
| [specs/08-parallel.md](specs/08-parallel.md) | Dependency waves, code ownership and integration protocol |
| [contracts/openapi.json](contracts/openapi.json) | Versioned public HTTP contract and request/response schemas |
| [contracts/tools.json](contracts/tools.json) | Typed agent inputs and evidence-returning tools |
| [contracts/ai-output.schema.json](contracts/ai-output.schema.json) | Model output contracts, separate from public API responses |
| [contracts/SEMANTICS.md](contracts/SEMANTICS.md) | Cross-field validation and retry rules |
| [contracts/imports.json](contracts/imports.json) | Exact CSV columns, field rules and correction behavior |
| [contracts/states.json](contracts/states.json) | Allowed application and job transitions |
| [plan/tasks.json](plan/tasks.json) | Assignable work packets with dependencies and acceptance IDs |
| [plan/acceptance.json](plan/acceptance.json) | Given/when/then cases linked to requirements and owners |
| [DECISIONS.md](DECISIONS.md) | Deliberate architectural changes and records |

---

## 🛡️ License
Private and confidential. Developed for StoreOps MVP.
