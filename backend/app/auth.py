"""Who the caller is: a visitor by cookie, or an admin caller by bearer token.

A visitor is identified only by the `uid` cookie this server issued: 32 random bytes,
of which the database keeps only the SHA-256, so a copy of the database cannot be
turned into a working cookie. The cookie holds either an anonymous visitor's token,
found on their own record, or a signed-in browser's session token, found in `sessions`
and good for 30 days. A value the server did not issue, or an expired session, matches
no one and counts as no cookie. No endpoint accepts a user ID from the caller. A visitor
record is created only with the first team or an account, never on a read.

The bearer tokens are compared in constant time. A wrong or missing token is a 401 and
one warning line saying whether a token was absent or wrong, never the token itself.
An endpoint whose token is not set stays closed.
"""

import hashlib
import hmac
import logging
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import psycopg
from fastapi import HTTPException, Request, Response

from app import limits
from app.logs import log_event, route_template

logger = logging.getLogger(__name__)

COOKIE_NAME = "uid"
# Visitor records in all. About 14 KB each with 20 full teams (measured on 2026-11-22:
# 100 such visitors grew the three tables by 1.39 MB), so this ceiling is about 0.7 GB.
MAX_VISITORS = 50_000
COOKIE_MAX_AGE = 365 * 24 * 60 * 60  # an anonymous visitor's cookie: one year, in seconds
SESSION_LIFETIME = timedelta(days=30)  # a signed-in browser's, from sign-in

# Both kinds of token in one query; the hash is unique within each table and a value of
# 32 random bytes is in at most one of them.
IDENTITY_QUERY = """
    SELECT id, false FROM users WHERE token_hash = %(hash)s
    UNION ALL
    SELECT user_id, true FROM sessions WHERE token_hash = %(hash)s AND created_at > %(since)s
    LIMIT 1
"""


@dataclass(frozen=True)
class Identity:
    user_id: int
    signed_in: bool  # True for an account's session, False for an anonymous visitor


def identify(request: Request, conn: psycopg.Connection[Any], now: datetime) -> Identity | None:
    """Who the cookie belongs to at `now`, or None for no, an unknown or an expired cookie."""
    token_hash = cookie_hash(request)
    if token_hash is None:
        return None
    params = {"hash": token_hash, "since": now - SESSION_LIFETIME}
    row = conn.execute(IDENTITY_QUERY, params).fetchone()
    return None if row is None else Identity(int(row[0]), bool(row[1]))


def current_user(request: Request, conn: psycopg.Connection[Any]) -> int | None:
    """The visitor's record ID from their cookie, or None for no or an unknown cookie."""
    identity = identify(request, conn, datetime.now(UTC))
    return None if identity is None else identity.user_id


def create_user(request: Request, response: Response, conn: psycopg.Connection[Any]) -> int:
    """Create an anonymous visitor record and set its cookie; counts as a new visitor."""
    admit_new_visitor(request, conn)
    value, token_hash = new_token()
    row = conn.execute(
        "INSERT INTO users (token_hash) VALUES (%s) RETURNING id", (token_hash,)
    ).fetchone()
    assert row is not None  # INSERT ... RETURNING always returns the new row
    set_cookie(response, value, COOKIE_MAX_AGE)
    return int(row[0])


def admit_new_visitor(request: Request, conn: psycopg.Connection[Any]) -> None:
    """Allow one more visitor record, anonymous or an account, or raise.

    Limited per address, then for all addresses together, then by a ceiling on visitor
    records in all; at the ceiling the answer is 503 and nothing is created.
    """
    limits.enforce(request, "new_visitor")
    limits.enforce(request, "new_visitor_total", key="all")
    _refuse_at_the_ceiling(request, conn)


def new_token() -> tuple[str, bytes]:
    """A fresh cookie value and the SHA-256 that is all the database keeps of it."""
    value = secrets.token_urlsafe(32)
    return value, _hash(value)


def cookie_hash(request: Request) -> bytes | None:
    """The SHA-256 of the caller's cookie, or None without one."""
    value = request.cookies.get(COOKIE_NAME)
    return _hash(value) if value else None


def set_cookie(response: Response, value: str, max_age: int) -> None:
    """Set the one visitor cookie, with the same attributes for both kinds of token."""
    response.set_cookie(
        COOKIE_NAME, value, max_age=max_age, path="/", secure=True, httponly=True, samesite="lax"
    )


def clear_cookie(response: Response) -> None:
    """Tell the browser to drop the cookie, with the attributes it was set with."""
    response.delete_cookie(COOKIE_NAME, path="/", secure=True, httponly=True, samesite="lax")


def _refuse_at_the_ceiling(request: Request, conn: psycopg.Connection[Any]) -> None:
    # The lock makes the count and the insert one step, so two creations cannot both
    # pass the ceiling; creations are at most ten a minute, so it costs nothing.
    conn.execute("LOCK TABLE users IN SHARE ROW EXCLUSIVE MODE")
    row = conn.execute("SELECT count(*) FROM users").fetchone()
    count = int(row[0]) if row else 0
    if count < MAX_VISITORS:
        return
    if request.app.state.limiter.first_refusal("new_visitor_total", "ceiling"):
        log_event(
            logger, logging.WARNING, "visitor_ceiling_reached", count=count, limit=MAX_VISITORS
        )
    raise HTTPException(503, "No new visitors can be saved at the moment")


def _hash(cookie_value: str) -> bytes:
    return hashlib.sha256(cookie_value.encode()).digest()


def require_scan_token(request: Request) -> None:
    """Dependency: allow only a caller presenting SCAN_TOKEN."""
    _require_bearer(request, request.app.state.settings.scan_token)


def require_admin_token(request: Request) -> None:
    """Dependency: allow only a caller presenting ADMIN_TOKEN (the demo controls)."""
    _require_bearer(request, request.app.state.settings.admin_token)


def _require_bearer(request: Request, expected: str | None) -> None:
    header = request.headers.get("authorization")
    if header is not None and expected is not None and _bearer_matches(header, expected):
        return
    address = limits.client_address(request)
    if request.app.state.limiter.first_refusal("admin", address):
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
