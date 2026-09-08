# BERESIN production image - serves both the API and the frontend.
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    BERESIN_ENV=production

WORKDIR /app

# Frontend first (static assets served by FastAPI catch-all)
COPY index.html app.js chat.js styles.css supervisor.js login.html ./
COPY user/ ./user/
COPY supervisor/ ./supervisor/

# Server package
COPY server/pyproject.toml server/uv.lock* ./server/
WORKDIR /app/server
RUN uv sync --no-dev --no-install-project
COPY server/beresin ./beresin
COPY server/run.py ./run.py
COPY server/.env.example ./.env.example

# Runtime data directory (SQLite + sandbox)
RUN mkdir -p /app/server/data
RUN useradd --system --uid 10001 --home /nonexistent --shell /usr/sbin/nologin beresin \
    && chown -R beresin:beresin /app/server/data
VOLUME ["/app/server/data"]

EXPOSE 8000
USER 10001:10001
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD [".venv/bin/python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/ready', timeout=3)"]
CMD [".venv/bin/python", "run.py"]
