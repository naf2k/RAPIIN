# BERESIN production image - API and worker only.
FROM ghcr.io/astral-sh/uv:latest AS uv
FROM python:3.13-alpine

# Copy only the standalone package manager, not its build image's Python packages.
COPY --from=uv /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    BERESIN_ENV=production

WORKDIR /app

# Pull current distribution security fixes into the immutable release image.
RUN apk upgrade --no-cache

# Server package
COPY server/pyproject.toml server/uv.lock* ./server/
WORKDIR /app/server
RUN uv sync --no-dev --no-install-project \
    && uv cache clean \
    && python -m pip uninstall --yes pip
COPY server/beresin ./beresin
COPY server/run.py ./run.py
COPY server/.env.example ./.env.example

# Runtime data directory (SQLite + sandbox)
RUN mkdir -p /app/server/data
RUN addgroup -S -g 10001 beresin \
    && adduser -S -D -H -u 10001 -G beresin beresin \
    && chown -R beresin:beresin /app/server/data
VOLUME ["/app/server/data"]

EXPOSE 8000
USER 10001:10001
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD [".venv/bin/python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/ready', timeout=3)"]
CMD [".venv/bin/python", "run.py"]
