"""Database access: a small fixed set of reused connections, and schema.sql at start-up.

Opening a Postgres connection costs the database far more than a query: on a test
database held to the deployed size (0.1 CPU, TLS), about 7 new connections a second
against about 3,800 queries a second on an open one. So requests borrow one of a few
connections opened once, and wait at most two seconds for one before answering 503.
A borrowed connection commits when the request succeeds and rolls back when it fails.
There is no ORM.
"""

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import psycopg
from fastapi import HTTPException, Request
from psycopg_pool import ConnectionPool, PoolTimeout, TooManyRequests

from app.logs import log_event

logger = logging.getLogger(__name__)

Conn = psycopg.Connection[Any]

SCHEMA_FILE = Path(__file__).with_name("schema.sql")
POOL_SIZE = 4  # each read holds a connection for well under a millisecond of database work
POOL_WAIT_SECONDS = 2.0  # then 503, rather than holding a worker thread longer
CONNECT_TIMEOUT_SECONDS = 5  # a struggling database fails fast instead of hanging


def connect(database_url: str) -> psycopg.Connection[Any]:
    """Open one connection, for start-up and for a scan (one per run)."""
    return psycopg.connect(database_url, connect_timeout=CONNECT_TIMEOUT_SECONDS)


def open_pool(database_url: str) -> ConnectionPool[psycopg.Connection[Any]]:
    """The connections requests borrow, each checked before it is lent."""
    pool: ConnectionPool[psycopg.Connection[Any]] = ConnectionPool(
        database_url,
        min_size=POOL_SIZE,
        max_size=POOL_SIZE,
        open=False,
        check=ConnectionPool.check_connection,
        timeout=POOL_WAIT_SECONDS,
        kwargs={"connect_timeout": CONNECT_TIMEOUT_SECONDS},
        name="requests",
    )
    return pool


def apply_schema(conn: psycopg.Connection[Any]) -> None:
    """Create any missing table or index. Every statement in the file is idempotent."""
    conn.execute(SCHEMA_FILE.read_bytes())


@contextmanager
def connection_for(request: Request) -> Iterator[psycopg.Connection[Any]]:
    """Borrow a connection for a request, or answer 503 if none is free in time or too
    many requests are already waiting for one.

    The failure is logged by error class only: a database error's message can name
    the host or the user.
    """
    try:
        with request.app.state.pool.connection() as conn:
            yield conn
    except (PoolTimeout, TooManyRequests) as exc:
        log_event(
            logger,
            logging.ERROR,
            "db_unreachable",
            request_id=request.state.request_id,
            error_class=type(exc).__name__,
        )
        raise HTTPException(503, "Service unavailable", headers={"Retry-After": "1"}) from None
