FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app"

WORKDIR /app

# Install uv package manager
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Copy dependency manifests
COPY pyproject.toml uv.lock ./
COPY packages/contracts/python ./packages/contracts/python

# Install dependencies deterministically
RUN uv sync --frozen --no-dev

# Copy application source code
COPY apps/api ./apps/api
COPY scripts/deploy ./scripts/deploy
COPY infra ./infra
COPY migrations ./migrations

EXPOSE 8000

CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
