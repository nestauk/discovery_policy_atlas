# syntax=docker/dockerfile:1

# --- Build stage: compile C extensions (HDBSCAN, etc.) with build tools ---
FROM python:3.12-slim AS builder

RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

COPY pyproject.toml uv.lock ./

# Install production dependencies into a virtual environment from the locked versions
RUN uv sync --no-dev --no-install-project --frozen

# --- Runtime stage ---
FROM python:3.12-slim

# libgomp1 is required at runtime by HDBSCAN/numpy (OpenMP parallelism)
RUN apt-get update && apt-get install -y \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy the pre-built virtual environment from builder
COPY --from=builder /app/.venv ./.venv

# Copy application code
COPY . .

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
