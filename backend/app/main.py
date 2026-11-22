"""The web application: API routes, the built frontend, and the rules every request passes.

Every response carries the security headers. A write whose Origin header names another
site is refused. An unhandled error is logged by class and frames and answered with a
generic 500 carrying only a request ID the visitor can quote.
"""

import logging
import secrets
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

import psycopg
from fastapi import Depends, FastAPI, Request, Response
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from psycopg_pool import PoolTimeout

from app import db, limits, logs
from app.config import Settings, load_settings
from app.routes import admin, alerts, counter, demo_controls, pokemon, teams

logger = logging.getLogger(__name__)

# The frontend build, at the same place relative to this file locally and in the image.
STATIC_DIR = Path(__file__).resolve().parents[2] / "frontend" / "dist"

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
    async def apply_schema_at_start(_: FastAPI) -> AsyncIterator[None]:
        pool = db.open_pool(settings.database_url)
        try:
            with db.connect(settings.database_url) as conn:
                db.apply_schema(conn)
            pool.open(wait=True, timeout=db.CONNECT_TIMEOUT_SECONDS * 2)
        except (psycopg.OperationalError, PoolTimeout) as exc:
            # Re-raised without its message, which can name the host or the user.
            logs.log_event(logger, logging.ERROR, "db_unreachable", error_class=type(exc).__name__)
            raise RuntimeError("database unreachable at start-up") from None
        app.state.pool = pool
        yield
        pool.close()

    app = FastAPI(
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=apply_schema_at_start,
        dependencies=[Depends(limits.limit_reads)],
    )
    app.state.settings = settings
    app.state.limiter = limits.RateLimiter()
    app.middleware("http")(guard_request)
    app.add_middleware(GZipMiddleware)
    app.get("/healthz")(healthz)
    app.include_router(admin.router)
    app.include_router(pokemon.router)
    app.include_router(teams.router)
    app.include_router(counter.router)
    app.include_router(alerts.router)
    app.include_router(demo_controls.router)
    if STATIC_DIR.is_dir():
        app.mount("/", StaticFiles(directory=STATIC_DIR, html=True))
    return app


async def healthz() -> dict[str, bool]:
    """Says the process is up. Touches no database and, being async, needs no worker
    thread, so it answers even while every worker thread is waiting on the database."""
    return {"ok": True}


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
