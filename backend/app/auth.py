"""Who the caller is: an anonymous visitor by cookie, or an admin caller by bearer token.

A visitor is identified only by the `uid` cookie this server issued: 32 random bytes,
of which the database keeps only the SHA-256, so a copy of the database cannot be
turned into a working cookie. A value the server did not issue matches no one and
counts as no cookie. No endpoint accepts a user ID from the caller. A visitor record is
created only with the first team, never on a read.

The bearer tokens are compared in constant time. A wrong or missing token is a 401 and
one warning line saying whether a token was absent or wrong, never the token itself.
An endpoint whose token is not set stays closed.
"""

import hashlib
import hmac
import logging
import secrets
from typing import Any

import psycopg
from fastapi import HTTPException, Request, Response

from app import limits
from app.logs import log_event, route_template

logger = logging.getLogger(__name__)

COOKIE_NAME = "uid"
COOKIE_MAX_AGE = 365 * 24 * 60 * 60  # one year, in seconds


def current_user(request: Request, conn: psycopg.Connection[Any]) -> int | None:
    """The visitor's record ID from their cookie, or None for no or an unknown cookie."""
    value = request.cookies.get(COOKIE_NAME)
    if not value:
        return None
    row = conn.execute("SELECT id FROM users WHERE token_hash = %s", (_hash(value),)).fetchone()
    return None if row is None else int(row[0])


def create_user(request: Request, response: Response, conn: psycopg.Connection[Any]) -> int:
    """Create a visitor record and set its cookie on the response; counts as a new visitor."""
    limits.enforce(request, "new_visitor")
    value = secrets.token_urlsafe(32)
    row = conn.execute(
        "INSERT INTO users (token_hash) VALUES (%s) RETURNING id", (_hash(value),)
    ).fetchone()
    assert row is not None  # INSERT ... RETURNING always returns the new row
    response.set_cookie(
        COOKIE_NAME,
        value,
        max_age=COOKIE_MAX_AGE,
        path="/",
        secure=True,
        httponly=True,
        samesite="lax",
    )
    return int(row[0])


def _hash(cookie_value: str) -> bytes:
    return hashlib.sha256(cookie_value.encode()).digest()


def require_scan_token(request: Request) -> None:
    """Dependency: allow only a caller presenting SCAN_TOKEN."""
    _require_bearer(request, request.app.state.settings.scan_token)


def _require_bearer(request: Request, expected: str | None) -> None:
    header = request.headers.get("authorization")
    if header is not None and expected is not None and _bearer_matches(header, expected):
        return
    log_event(
        logger,
        logging.WARNING,
        "admin_unauthorized",
        request_id=request.state.request_id,
        route=route_template(request),
        token="absent" if header is None else "wrong",
    )
    raise HTTPException(401, "Unauthorized", headers={"WWW-Authenticate": "Bearer"})


def _bearer_matches(header: str, expected: str) -> bool:
    scheme, _, presented = header.partition(" ")
    # Bytes, because compare_digest refuses non-ASCII text and a header may hold any.
    same = hmac.compare_digest(presented.encode(), expected.encode())
    return scheme.lower() == "bearer" and same
