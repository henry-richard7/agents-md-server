# syntax=docker/dockerfile:1
FROM python:3.13-slim AS builder

# Install uv from official image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Enable bytecode compilation and copy link mode for build speed
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

# Copy dependency manifests first for Docker layer caching
COPY pyproject.toml uv.lock README.md /app/

# Install dependencies into virtualenv (cached until manifests change)
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

# Copy application source
COPY src/ /app/src/

# Install project package into virtualenv
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# Final production image
FROM python:3.13-slim AS runner

WORKDIR /app

# Create a non-privileged user for security
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Copy virtualenv and dependencies from builder
COPY --from=builder --chown=appuser:appuser /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

# Copy source code, skills, and configuration
COPY --chown=appuser:appuser src/ /app/src/
COPY --chown=appuser:appuser skills/ /app/skills/
COPY --chown=appuser:appuser tools/ /app/tools/
COPY --chown=appuser:appuser AGENTS.md /app/AGENTS.md
COPY --chown=appuser:appuser pyproject.toml /app/pyproject.toml
COPY --chown=appuser:appuser README.md /app/README.md

USER appuser

# Default configuration
ENV HOST=0.0.0.0 \
    PORT=8000 \
    TRANSPORT=http \
    LOG_LEVEL=INFO \
    PYTHONUNBUFFERED=1

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/mcp').read()" || exit 1

ENTRYPOINT ["agents-md-server", "run"]
CMD ["--transport", "http", "--host", "0.0.0.0", "--port", "8000"]
