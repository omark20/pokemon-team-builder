# Running it locally

You need **Docker** (with Compose), **uv** and **Node.js 24** with npm. Everything else
(Python 3.13, the Python and npm packages, Postgres 18) is fetched by the commands below.
Use Chrome or Firefox locally: the visitor cookie is marked Secure, which those browsers
accept on `http://localhost`.

## Tests

```bash
make test
```

On first use this writes a git-ignored `.env` with freshly generated local secrets, starts
Postgres in Docker on `127.0.0.1:5433`, installs the packages and runs the backend tests
(against a separate `pokemon_test` database) and then the frontend tests. No network
access to PokéAPI is needed.

```bash
make lint
```

runs ruff, mypy, the size checks and the frontend's ESLint and type check.

## The app

```bash
make sync
```

fills the local database from PokéAPI (one full scan, about 15 seconds). Then, in two
terminals:

```bash
make dev
```

```bash
npm --prefix frontend run dev
```

The first serves the API on `http://127.0.0.1:8000`; the second serves the page on
`http://localhost:5173` and forwards `/api` to the first. Restart `make dev` after a
`make sync`, because the running server keeps its own in-memory copy of the Pokémon list.

## The whole path in one command

```bash
make smoke
```

starts the app on port 8765 against the local database, runs a live scan of PokéAPI, and
then drives the API as visitors and as the scheduler would: a team, its counter team, an
injected change, the alert for one visitor and none for another, and the reset. It prints
`ok` or `FAIL` per step and cleans up after itself. It needs the network and takes under
a minute, so it is not part of `make test`.

## Settings

| Name | Used for |
|---|---|
| `DATABASE_URL` | the Postgres connection |
| `SCAN_TOKEN` | bearer token for `POST /api/admin/scan`, and nothing else |
| `ADMIN_TOKEN` | bearer token for the demo controls (`/api/admin/demo/...`) |

Locally they come from `.env`. On the host they are environment settings; `SCAN_TOKEN` is
also a GitHub Actions secret, and the scheduled workflow reads the site address from the
`APP_URL` variable. `.env.example` lists the names with placeholder values.
