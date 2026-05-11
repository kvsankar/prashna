# syntax=docker/dockerfile:1.7

# ----- builder: resolve deps with uv into a venv -----
FROM python:3.12-slim AS builder

# uv is a fast resolver; copy the static binary in.
COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /usr/local/bin/uv

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Resolve and install only deps first so this layer caches across code edits.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Now bring in the app code.
COPY app ./app
COPY static ./static

# ----- runtime: slim image with just python + the venv -----
FROM python:3.12-slim AS runtime

# tini gives us a proper PID 1; libpq isn't needed but curl is for HEALTHCHECK.
RUN apt-get update && apt-get install -y --no-install-recommends \
        tini curl \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --system --gid 1001 prashna \
 && useradd  --system --uid 1001 --gid prashna --home /app --shell /usr/sbin/nologin prashna

WORKDIR /app
COPY --from=builder --chown=prashna:prashna /app /app

# SQLite DB lives on a volume; uploads on another.
ENV PRASHNA_DB_PATH=/data/prashna.db \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

RUN install -d -o prashna -g prashna /data /app/uploads
VOLUME ["/data", "/app/uploads"]

USER prashna
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/api/admin/status >/dev/null || exit 1

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
