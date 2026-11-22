# One image serves the API and the built frontend from one origin.
# No ARG is declared, so the host's build arguments cannot reach the build.

# Stage 1: build the frontend with the same Node.js major version used locally.
FROM node:24-slim AS frontend
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: the backend, installed from its lock file, plus the built frontend.
FROM python:3.13-slim
COPY --from=ghcr.io/astral-sh/uv:0.11.11 /uv /usr/local/bin/uv
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock backend/.python-version ./
RUN uv sync --locked --no-dev --no-install-project
COPY backend/app ./app
# Same place relative to the backend as in the repository (app/main.py, STATIC_DIR).
COPY --from=frontend /src/frontend/dist /app/frontend/dist
RUN useradd --system --no-create-home app
USER app
ENV PATH="/app/backend/.venv/bin:$PATH"
# The host sets PORT; 10000 is its documented default. One worker, so the in-memory
# list cache and rate limits are exact. No Server header, so the software is not announced.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-10000} --workers 1 --no-server-header"]
