"""Who may call what: the bearer token that guards the scheduler's scan trigger.

The token is compared in constant time. A wrong or missing token is a 401 and one
warning line saying whether a token was absent or wrong, never the token itself.
An endpoint whose token is not set stays closed.
"""

import hmac
import logging

from fastapi import HTTPException, Request

from app.logs import log_event, route_template

logger = logging.getLogger(__name__)


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
