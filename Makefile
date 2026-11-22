# One entry point for local work. Needs Docker, uv and Node.js (see SETUP.md).

# Make builds .env with the rule below if it is missing, then reads it, so every
# command started from here sees the local settings.
include .env
export

.PHONY: audit burst db dev lint smoke sync test

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
	cd backend && uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --no-server-header

# One full scan of PokéAPI into the local database.
sync: db
	cd backend && uv run python -m app.scan

# Drive the real app through its API, scanning the live PokéAPI. Not part of `make test`:
# it needs the network and takes over a minute.
smoke: db
	cd backend && uv run python scripts/smoke.py

# Bursts of reads against a throwaway database held to the deployed size, checking that
# the app refuses with 429 and keeps its health check answering. Not part of `make test`:
# it takes about a minute.
burst: .env
	docker compose --profile burst up --detach --wait db-burst
	cd backend && uv run python scripts/burst.py; status=$$?; \
		cd .. && docker compose --profile burst rm --stop --force db-burst; exit $$status

# Known vulnerabilities in every locked backend package and in the frontend's packages.
# pipefail, so a failed export cannot pass as "nothing found".
audit:
	cd backend && bash -o pipefail -c \
		'uv export --frozen --no-emit-project --format requirements-txt \
		| uvx pip-audit@2.10.1 --disable-pip -r /dev/stdin'
	@if [ -f frontend/package.json ]; then npm --prefix frontend audit --audit-level=high; fi

lint:
	cd backend && uv run ruff check .
	cd backend && uv run ruff format --check .
	cd backend && uv run mypy
	cd backend && uv run python scripts/check_limits.py
	@if [ -f frontend/package.json ]; then \
		npm --prefix frontend run lint && npm --prefix frontend run typecheck; \
	fi

# uv installs the backend's locked packages on first use; the frontend's are installed
# from its lock file only when missing, as in a clean clone.
test: db
	cd backend && uv run pytest
	@if [ -f frontend/package.json ]; then \
		[ -d frontend/node_modules ] || npm --prefix frontend ci; \
		npm --prefix frontend test; \
	fi
