"""The web application: API routes, the built frontend, and the rules every request passes.

Every response carries the security headers. A write whose Origin header names another
site is refused. A body that fails validation is answered without quoting it, so a
password sent in a malformed body never comes back. An unhandled error is logged by
class and frames and answered with a generic 500 carrying only a request ID the visitor
can quote.
"""

import asyncio
import contextlib
import logging
import secrets
import threading
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from functools import partial
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import psycopg
from fastapi import Depends, FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from psycopg_pool import ConnectionPool, PoolTimeout

from app import db, limits, logs, scan, self_scan, team_names
from app.config import Settings, load_settings
from app.routes import admin, alerts, counter, demo_controls, pokemon, sessions, teams

logger = logging.getLogger(__name__)

# The frontend build, at the same place relative to this file locally and in the image.
STATIC_DIR = Path(__file__).resolve().parents[2] / "frontend" / "dist"

# A team write, a dismissal or a scan trigger is well under a kilobyte; the demo's
# overrides document has its own, larger limit (routes/demo_controls.py).
MAX_BODY_BYTES = 16 * 1024

SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; img-src 'self' https://raw.githubusercontent.com data:; "
        "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    ),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Strict-Transport-Security": "max-age=31536000",
}


def create_app(settings: Settings) -> FastAPI:
    """Build the app for the given settings. Documentation routes are switched off."""

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        pool = db.open_pool(settings.database_url)
        try:
            with db.connect(settings.database_url) as conn:
                db.apply_schema(conn)
                _make_team_names_unique(conn)
            pool.open(wait=True, timeout=db.CONNECT_TIMEOUT_SECONDS * 2)
        except (psycopg.OperationalError, PoolTimeout) as exc:
            # Re-raised without its message, which can name the host or the user.
            logs.log_event(logger, logging.ERROR, "db_unreachable", error_class=type(exc).__name__)
            raise RuntimeError("database unreachable at start-up") from None
        app.state.pool = pool
        # The app's own scan start (self_scan.py): its first look is ten minutes from now.
        looking = asyncio.create_task(self_scan.keep_scanned(partial(_look, pool, settings)))
        yield
        looking.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await looking
        pool.close()

    app = FastAPI(
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
        dependencies=[Depends(limits.limit_reads)],
    )
    app.state.settings = settings
    app.state.limiter = limits.RateLimiter()
    app.state.counter_places = threading.BoundedSemaphore(counter.COUNTER_PLACES)
    app.state.hash_places = threading.BoundedSemaphore(sessions.HASH_PLACES)
    app.exception_handler(RequestValidationError)(validation_failed)
    app.middleware("http")(guard_request)
    app.add_middleware(GZipMiddleware)
    app.get("/healthz")(healthz)
    # Bodies over the limit are refused with 413 while being read: before they are parsed
    # or any token is checked. Set per route, so the refusal passes the middleware above.
    for routes in (admin, pokemon, teams, counter, alerts, demo_controls, sessions):
        app.include_router(routes.router, max_body_size=MAX_BODY_BYTES)
    if STATIC_DIR.is_dir():
        app.mount("/", StaticFiles(directory=STATIC_DIR, html=True))
    return app


def _make_team_names_unique(conn: db.Conn) -> None:
    """The start-up step of team_names.py. If it fails the app does not start, as with a
    schema that fails; the error is logged by class and place only, since its message
    can quote stored team names."""
    try:
        team_names.make_names_unique(conn)
    except psycopg.OperationalError:
        raise  # the database went away: reported as unreachable, like the schema
    except Exception as exc:
        logs.log_exception(logger, "team_names_failed", exc)
        raise RuntimeError("team names could not be made unique at start-up") from None


def _look(pool: ConnectionPool[Any], settings: Settings) -> None:
    """One look by the app's own scan start, scanning the real PokéAPI if one is due."""

    def run(run_id: int) -> str:
        return scan.scan_with_pokeapi(settings.database_url, run_id, None)

    self_scan.look(pool, scan.utc_now(), run)


async def healthz() -> dict[str, bool]:
    """Says the process is up. Touches no database and, being async, needs no worker
    thread, so it answers even while every worker thread is waiting on the database."""
    return {"ok": True}


# What a validation error keeps: its kind, where it is, and the library's sentence. The
# input it refused and the context, which can quote it, are left out for the whole app.
ERROR_KEYS = ("type", "loc", "msg")


async def validation_failed(_: Request, exc: Exception) -> JSONResponse:
    """422 listing each problem without the value that caused it."""
    assert isinstance(exc, RequestValidationError)  # registered for this class only
    detail = [{key: error[key] for key in ERROR_KEYS if key in error} for error in exc.errors()]
    return JSONResponse({"detail": detail}, status_code=422)


async def guard_request(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Give the request an ID, refuse cross-site writes, hide errors, add headers."""
    request.state.request_id = secrets.token_hex(8)
    if is_cross_site_write(request):
        response: Response = JSONResponse({"detail": "Forbidden"}, status_code=403)
    else:
        try:
            response = await call_next(request)
        except Exception as exc:
            logs.log_exception(
                logger,
                "request_failed",
                exc,
                request_id=request.state.request_id,
                method=request.method,
                route=logs.route_template(request),
            )
            body = {"detail": "Internal error", "request_id": request.state.request_id}
            response = JSONResponse(body, status_code=500)
    response.headers.update(SECURITY_HEADERS)
    return response


def is_cross_site_write(request: Request) -> bool:
    """True for a non-GET request whose Origin header does not match its Host.

    A request with no Origin header (curl, the scheduler) is not affected; it still
    meets the token or cookie check.
    """
    origin = request.headers.get("origin")
    if request.method == "GET" or origin is None:
        return False
    return urlsplit(origin).netloc != request.headers.get("host")


logs.configure()
app = create_app(load_settings())
