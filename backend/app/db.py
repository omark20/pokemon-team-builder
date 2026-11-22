"""Database access: one connection per request, and applying schema.sql at start-up.

There is no pool and no ORM. A psycopg connection used as a context manager commits
when the block ends normally, rolls back on an exception, and closes.
"""

import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Annotated, Any

import psycopg
from fastapi import Depends, HTTPException, Request

from app.logs import log_event

logger = logging.getLogger(__name__)

SCHEMA_FILE = Path(__file__).with_name("schema.sql")


def connect(database_url: str) -> psycopg.Connection[Any]:
    """Open a connection. Every connection the app makes goes through here."""
    return psycopg.connect(database_url)


def apply_schema(conn: psycopg.Connection[Any]) -> None:
    """Create any missing table or index. Every statement in the file is idempotent."""
    conn.execute(SCHEMA_FILE.read_bytes())


def connect_for_request(request: Request) -> psycopg.Connection[Any]:
    """Open a connection for a request, or answer 503.

    A failure to connect is logged by error class only (its message can name the host
    or the user) and the visitor gets a plain 503.
    """
    try:
        return connect(request.app.state.settings.database_url)
    except psycopg.OperationalError as exc:
        log_event(
            logger,
            logging.ERROR,
            "db_unreachable",
            request_id=request.state.request_id,
            error_class=type(exc).__name__,
        )
        raise HTTPException(503, "Service unavailable") from None


def request_connection(request: Request) -> Iterator[psycopg.Connection[Any]]:
    """Give a route one connection, committed before the response is sent."""
    with connect_for_request(request) as conn:
        yield conn


# scope="function" ends the dependency, and so commits, before the response is sent.
# FastAPI's default ends it after the response, when a failed commit could not be reported.
Connection = Annotated[psycopg.Connection[Any], Depends(request_connection, scope="function")]
