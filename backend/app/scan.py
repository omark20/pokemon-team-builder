"""The scan of PokéAPI, and its record in scan_runs.

A trigger first inserts a `running` row; the database allows only one at a time, so
a second trigger fails on insert. For now a run does no work and is marked finished.
"""

from typing import Any

import psycopg

from app import db


def start_run(conn: psycopg.Connection[Any], scope: str) -> int:
    """Record a new run as running and return its ID.

    Raises psycopg.errors.UniqueViolation if another run is already in progress.
    """
    row = conn.execute(
        "INSERT INTO scan_runs (status, scope) VALUES ('running', %s) RETURNING id", (scope,)
    ).fetchone()
    assert row is not None  # INSERT ... RETURNING always returns the new row
    run_id: int = row[0]
    return run_id


def finish_run(database_url: str, run_id: int) -> None:
    """Mark the run as finished without problems."""
    with db.connect(database_url) as conn:
        conn.execute(
            "UPDATE scan_runs SET status = 'ok', finished_at = now() WHERE id = %s", (run_id,)
        )
