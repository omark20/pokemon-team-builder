"""The list of every stored Pokémon, kept in memory once built.

`GET /api/pokemon` is public and unlimited, so it is answered from one serialised copy
instead of reading 1,351 rows each time. The copy is cleared whenever stored Pokémon
can have changed: at the end of a scan that wrote a Pokémon row, and after a demo reset.
The service is one process, so there is one copy, and the code that changes the rows
runs in that process and clears it. Building and clearing take the same lock, so a
build that began before a scan's last write cannot outlive the clear.
"""

import json
import logging
import threading
from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Any

import psycopg

from app.logs import log_event

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_body: bytes | None = None

LIST_QUERY = """
    SELECT id, name, is_default, types,
           ARRAY[hp, attack, defense, special_attack, special_defense, speed] AS stats,
           sprite_url, removed_at IS NOT NULL AS removed
    FROM pokemon ORDER BY id
"""


def get(connect: Callable[[], AbstractContextManager[psycopg.Connection[Any]]]) -> bytes:
    """The serialised list, built with one query on a connection from `connect` if not held."""
    global _body
    with _lock:
        if _body is None:
            with connect() as conn:
                _body = _serialise(conn)
        return _body


def clear(cause: str, **fields: int | str) -> None:
    """Drop the copy; the next request rebuilds it."""
    global _body
    with _lock:
        _body = None
    log_event(logger, logging.INFO, "list_cache_cleared", cause=cause, **fields)


def _serialise(conn: psycopg.Connection[Any]) -> bytes:
    columns = ("id", "name", "is_default", "types", "stats", "sprite_url", "removed")
    rows = conn.execute(LIST_QUERY).fetchall()
    entries = [dict(zip(columns, row, strict=True)) for row in rows]
    return json.dumps(entries, separators=(",", ":")).encode()
