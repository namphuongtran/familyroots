# syntax=docker/dockerfile:1.7
# ============================================================
# builder — compile native extensions + install all deps
# ============================================================
# Pin both the Python patch version and the Debian variant for
# fully reproducible builds.  Update the tag deliberately.
FROM python:3.14-slim-bookworm AS builder

# Native-extension build deps (psycopg v3 + cryptography wheels, etc.)
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc g++ libc6-dev \
    && rm -rf /var/lib/apt/lists/*

# Pin uv to an explicit release — never use :latest in production.
COPY --from=ghcr.io/astral-sh/uv:0.6.3 /uv /usr/local/bin/uv

# UV flags
#   UV_COMPILE_BYTECODE       — pre-compile .pyc during install → faster cold start
#   UV_LINK_MODE=copy         — required when cache mount and sync target are on
#                               different filesystems (BuildKit cache mounts)
#   UV_PYTHON_PREFERENCE      — accept the system Python shipped by the base image
#                               without strict patch-version matching against the lock file
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_PREFERENCE=only-system

WORKDIR /app

# ── Layer A: third-party dependencies only ───────────────────────────────────
# bind-mount the lock files so no COPY layer is created here.
# This layer is invalidated only when uv.lock or pyproject.toml changes.
# --python python3 points uv at the base-image binary, bypassing strict
# patch-version matching against the lock file (lock records 3.14.2 locally
# but Docker Hub's python:3.14 tag may ship a different patch release).
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-dev --no-install-project --python python3

# ── Layer B: install the project itself ──────────────────────────────────────
# COPY . invalidates this layer on any source change, but Layer A is still
# reused from cache, so only the (fast) project-wheel step re-runs.
# --no-editable installs app/ as a proper wheel including i18n/*.json assets.
COPY . /app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable --python python3

# ============================================================
# runtime — minimal final image, zero build tools
# ============================================================
FROM python:3.14-slim-bookworm AS runtime

# Activate the venv globally — no "source activate" required at runtime
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

# Non-root user — principle of least privilege
RUN groupadd --gid 1001 appuser \
    && useradd --uid 1001 --gid appuser --shell /bin/false --no-create-home appuser

WORKDIR /app

# Virtual environment with app + all deps already compiled to bytecode
COPY --from=builder --chown=appuser:appuser /app/.venv /app/.venv

# Alembic config + migration scripts — small, needed for pre-flight upgrades
COPY --chown=appuser:appuser alembic.ini ./
COPY --chown=appuser:appuser migrations/ ./migrations/

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

USER appuser

# Invoke uvicorn directly from the venv — no uv bootstrapper overhead at startup
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
