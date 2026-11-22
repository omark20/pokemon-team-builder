# One entry point for local work. Needs Docker, uv and Node.js (see SETUP.md).

# Make builds .env with the rule below if it is missing, then reads it, so every
# command started from here sees the local settings.
include .env
export

.PHONY: db dev lint test

# Local settings with freshly generated secrets. Git-ignored; never committed.
.env:
	@umask 077; password=$$(openssl rand -hex 16); { \
		echo "POSTGRES_PASSWORD=$$password"; \
		echo "DATABASE_URL=postgresql://pokemon:$$password@127.0.0.1:5433/pokemon"; \
		echo "SCAN_TOKEN=$$(openssl rand -hex 32)"; \
		echo "ADMIN_TOKEN=$$(openssl rand -hex 32)"; \
	} > .env
	@echo "wrote .env with generated local values"

# Start the local Postgres and wait until it accepts connections.
db:
	docker compose up --detach --wait db

# Run the backend on http://127.0.0.1:8000 with reload.
dev: db
	cd backend && uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

lint:
	cd backend && uv run ruff check .
	cd backend && uv run ruff format --check .
	cd backend && uv run mypy
	cd backend && uv run python scripts/check_limits.py
	@if [ -f frontend/package.json ]; then \
		npm --prefix frontend run lint && npm --prefix frontend run typecheck; \
	fi

test: db
	cd backend && uv run pytest
	@if [ -f frontend/package.json ]; then npm --prefix frontend test; fi
