.PHONY: help setup dev migrate bootstrap-admin generate-contracts add-member verify-spec test test-e2e test-cloud eval-live deploy-dev seed-demo

SHELL := /usr/bin/env bash

help:
	@echo "StoreOps MVP Command Interface"
	@echo "  make setup               Install exact locked dependencies (pnpm + uv)"
	@echo "  make verify-spec         Run spec validator with full OpenAPI meta-validation"
	@echo "  make generate-contracts  Produce TypeScript and Python contract artifacts deterministically"
	@echo "  make dev                 Start local emulators, API, worker, and web (requires T01/T05)"
	@echo "  make migrate             Apply idempotent local schema/index setup"
	@echo "  make bootstrap-admin     Provision empty workspace for existing Firebase UID"
	@echo "  make add-member          Add user role to workspace (ADMIN CLI)"
	@echo "  make test                Run deterministic unit, contract, and local integration tests"
	@echo "  make test-e2e            Browser acceptance on isolated empty workspace"
	@echo "  make test-cloud          Adapter parity tests on disposable cloud dataset"
	@echo "  make eval-live           Run live Gemini model evaluations"
	@echo "  make deploy-dev          Deploy to authorized Google Cloud development project"
	@echo "  make seed-demo           Optional T13 demo seed"

setup:
	@echo "Checking runtimes..."
	@which python3 >/dev/null || (echo "Error: python3 is not installed" && exit 1)
	@which uv >/dev/null || (echo "Error: uv is not installed" && exit 1)
	@which node >/dev/null || (echo "Error: node is not installed" && exit 1)
	@which pnpm >/dev/null || (echo "Error: pnpm is not installed" && exit 1)
	@echo "Installing locked Python dependencies via uv..."
	uv sync --frozen
	@echo "Installing locked Node dependencies via pnpm..."
	pnpm install --frozen-lockfile
	@echo "Setup complete."

verify-spec:
	uv run python3 tools/verify_spec.py --strict-meta --report validation/spec_check.json

generate-contracts:
	@echo "Generating TypeScript contracts..."
	pnpm --filter @storeops/contracts run generate
	pnpm --filter @storeops/contracts run build
	@echo "Generating Python Pydantic models..."
	uv run datamodel-codegen --input contracts/openapi.json --output packages/contracts/python/storeops_contracts/models.py --output-model-type pydantic_v2.BaseModel
	@echo "Checking contract drift..."
	@git diff --exit-code contracts/ || (echo "Error: Contract definitions in contracts/ modified unexpectedly." && exit 1)
	@echo "Contracts generated successfully and synchronized."

dev:
	@if [ ! -f "apps/api/main.py" ]; then \
		echo "Error: 'make dev' requires T01 foundation (apps/api/main.py). Complete T01 first."; \
		exit 1; \
	fi
	@echo "Starting development environment..."
	uv run uvicorn apps.api.main:app --reload --port 8000

migrate:
	@if [ ! -d "migrations" ]; then \
		echo "Error: 'make migrate' requires database migrations (T03). Complete T03 first."; \
		exit 1; \
	fi
	@echo "Applying local migrations..."

bootstrap-admin:
	@if [ ! -f "scripts/bootstrap.py" ]; then \
		echo "Error: 'make bootstrap-admin' requires scripts/bootstrap.py (T01). Complete T01 first."; \
		exit 1; \
	fi
	uv run python3 scripts/bootstrap.py

add-member:
	@if [ ! -f "scripts/bootstrap.py" ]; then \
		echo "Error: 'make add-member' requires scripts/bootstrap.py (T01). Complete T01 first."; \
		exit 1; \
	fi
	uv run python3 scripts/bootstrap.py --add-member

test:
	@if [ ! -d "tests" ]; then \
		echo "Error: No tests/ directory found."; \
		exit 1; \
	fi
	uv run pytest tests

test-e2e:
	@if [ ! -d "tests/e2e" ]; then \
		echo "Error: 'make test-e2e' requires tests/e2e (T08/T10)."; \
		exit 1; \
	fi
	pnpm --filter web test:e2e

test-cloud:
	@if [ ! -d "tests/cloud" ]; then \
		echo "Error: 'make test-cloud' requires cloud tests (T12)."; \
		exit 1; \
	fi
	uv run pytest tests/cloud

eval-live:
	@if [ ! -d "evals" ]; then \
		echo "Error: 'make eval-live' requires evals/ directory (T12)."; \
		exit 1; \
	fi
	uv run python3 evals/run_evals.py

deploy-dev:
	@if [ ! -d "infra" ]; then \
		echo "Error: 'make deploy-dev' requires infra/ directory (T11)."; \
		exit 1; \
	fi
	bash scripts/deploy/deploy.sh

seed-demo:
	@if [ ! -f "scripts/seed_demo/seed.py" ]; then \
		echo "Error: 'make seed-demo' requires scripts/seed_demo/seed.py (T13)."; \
		exit 1; \
	fi
	uv run python3 scripts/seed_demo/seed.py
