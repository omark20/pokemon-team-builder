"""The app's own start: a full scan when the last one is too old.

The scheduled workflow calls the scan endpoint every six hours, but GitHub's schedule
has skipped and delayed runs. So the app also looks every ten minutes, starting ten
minutes after it starts (never at start-up), and starts a full scan itself when one is
due. It uses the endpoint's own `scan.start_run`, whose unique index on running runs is
the only guard against two scans at once, from either trigger or a second instance: no
flag is kept in the process. A look that fails is logged and the next one comes as
usual, so the loop can neither end nor spin.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

import psycopg
from psycopg_pool import ConnectionPool

from app import db, demo, scan
from app.logs import log_event, log_exception

logger = logging.getLogger(__name__)

DUE_AFTER = timedelta(hours=7)  # since the last full scan that finished started
RETRY_AFTER = timedelta(hours=1)  # since any full scan started, so failures retry hourly
LOOK_EVERY_SECONDS = 10 * 60

Decision = Literal["due", "not_due", "paused_for_demo"]

# The start of the last full scan that finished, and of the last full scan of any outcome.
FACTS_QUERY = """
    SELECT max(started_at) FILTER (WHERE status IN ('ok', 'incomplete')), max(started_at)
    FROM scan_runs WHERE scope = 'full'
"""


@dataclass(frozen=True)
class Facts:
    last_finished: datetime | None  # started_at of the last full ok or incomplete run
    last_attempt: datetime | None  # started_at of the last full run, whatever its outcome
    demo_active: bool


def decide(now: datetime, facts: Facts) -> Decision:
    """Whether a scan is due at `now`: the last finished one started over 7 hours ago (or
    there is none), no full scan started in the last hour, and no demo is active."""
    stale = facts.last_finished is None or now - facts.last_finished > DUE_AFTER
    tried = facts.last_attempt is not None and now - facts.last_attempt < RETRY_AFTER
    if not stale or tried:
        return "not_due"
    return "paused_for_demo" if facts.demo_active else "due"


def look(pool: ConnectionPool[db.Conn], now: datetime, run: Callable[[int], object]) -> int | None:
    """Read the facts and, if a scan is due, start it and run it with `run`; the run's ID,
    or None when nothing was started. The connection is given back before the scan runs."""
    try:
        with pool.connection() as conn:
            facts = _facts(conn)
            decision = decide(now, facts)
            if decision == "paused_for_demo":
                log_event(logger, logging.INFO, "self_scan_paused", reason="demo_active")
            if decision != "due":
                return None
            run_id = scan.start_run(conn, "full", now, started_by="app")
    except psycopg.errors.UniqueViolation:  # a run is in progress, from either trigger
        return None
    log_event(logger, logging.INFO, "self_scan_started", run_id=run_id, **_age(now, facts))
    run(run_id)
    return run_id


async def keep_scanned(
    look_once: Callable[[], object],
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> None:
    """Forever: sleep, then look in a worker thread. Ends only when cancelled."""
    while True:
        await sleep(LOOK_EVERY_SECONDS)
        try:
            await asyncio.to_thread(look_once)
        except Exception as exc:  # a bad look must not end the loop
            log_exception(logger, "self_scan_failed", exc)


def _facts(conn: db.Conn) -> Facts:
    row = conn.execute(FACTS_QUERY).fetchone()
    last_finished, last_attempt = row if row else (None, None)
    return Facts(last_finished, last_attempt, demo.is_active(conn))


def _age(now: datetime, facts: Facts) -> dict[str, int | str]:
    """How many whole hours old the last finished scan was, for the log line."""
    if facts.last_finished is None:
        return {"last_finished_hours_ago": "never"}
    return {"last_finished_hours_ago": int((now - facts.last_finished) / timedelta(hours=1))}
