# ============================================================
# Production Dockerfile — Multi-stage build
#
# Stage 1 (builder): installs all Python dependencies.
# Stage 2 (runtime): copies only the installed packages and
#   application code — no build tools, smaller final image.
#
# Security:
#   - Runs as a non-root user (agent).
#   - No unnecessary packages in the final stage.
# ============================================================

# ── Stage 1: Builder ─────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

# Install build dependencies (gcc needed for some Python packages)
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first — leverages Docker layer cache.
# If requirements.txt hasn't changed, this layer is reused on rebuild.
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# ── Stage 2: Runtime ─────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

# Create a non-root user for security
RUN groupadd -r agent && useradd -r -g agent -d /app -s /sbin/nologin agent

WORKDIR /app

# Copy installed Python packages from the builder stage
COPY --from=builder /install /usr/local

# Copy application source
COPY app/ ./app/
COPY utils/ ./utils/

# Hand ownership to the non-root user
RUN chown -R agent:agent /app

USER agent

ENV PYTHONPATH=/app
# Disable .pyc files and enable unbuffered stdout (important for log streaming)
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

# Container health check (used by Docker Compose and orchestrators)
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c \
        "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" \
    || exit 1

# Start uvicorn — 2 workers per container is a safe default for a CPU-light agent.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
