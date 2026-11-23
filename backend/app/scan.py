"""The scan of PokéAPI. The first sync and every later run are the same function.

A run loads the type chart, then every move (full runs only, scan_moves.py), then the
list of Pokémon, then each Pokémon's details, four requests at a time, and hands each
result to scan_store to be compared and saved.
Failures never erase stored data or record a false change: a Pokémon that cannot be
read is skipped and counted, and a bad chart or list leaves what is stored as it was.
Every log line carries the run ID, so a run can be explained from its lines alone.
"""

import logging
import sys
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from functools import partial

from app import db, demo, logs, pokemon_list, scan_fetch, scan_moves, scan_store
from app.config import load_settings
from app.db import Conn
from app.domain.types import STANDARD_TYPES, ChartError, build_chart
from app.logs import log_event, log_exception, outside
from app.pokeapi import (
    RETRY_WAITS,
    WORKERS,
    PokeApiSource,
    Source,
    UpstreamError,
    get_with_retry,
    http_client,
)
from app.scan_fetch import Fetch
from app.scan_store import Run

logger = logging.getLogger(__name__)

TYPE_LIST_PATH = "type?limit=100"
POKEMON_LIST_PATH = "pokemon?limit=100000"
MIN_LIST_SHARE = 0.9  # a list this much shorter than what is stored looks truncated
STALE_AFTER = timedelta(minutes=30)  # a run still "running" after this was cut off


def utc_now() -> datetime:
    return datetime.now(UTC)


def start_run(conn: Conn, scope: str, now: datetime, started_by: str | None = None) -> int:
    """Record a new running run and return its ID, after failing runs cut off by a restart.

    `started_by` is 'api' for the trigger endpoint and 'app' for the app's own start.
    Raises psycopg.errors.UniqueViolation if another run is in progress.
    """
    conn.execute(
        "UPDATE scan_runs SET status = 'failed', finished_at = %s"
        " WHERE status = 'running' AND started_at < %s",
        (now, now - STALE_AFTER),
    )
    row = conn.execute(
        "INSERT INTO scan_runs (status, scope, started_at, started_by)"
        " VALUES ('running', %s, %s, %s) RETURNING id",
        (scope, now, started_by),
    ).fetchone()
    assert row is not None  # INSERT ... RETURNING always returns the new row
    run_id: int = row[0]
    return run_id


def run_scan(
    conn: Conn,
    source: Source,
    run_id: int,
    pokemon_ids: Sequence[int] | None = None,
    now: Callable[[], datetime] = utc_now,
    retry_waits: Sequence[float] = RETRY_WAITS,
) -> str:
    """Run a started scan to the end on an autocommit connection; return its status.

    With `pokemon_ids`, only those Pokémon are fetched, and none is judged removed for
    being absent from the list.
    """
    run = Run(run_id, now, now())
    on_retry = partial(_log_retry, run_id)
    fetch = partial(get_with_retry, source, waits=retry_waits, on_retry=on_retry)
    scope = "full" if pokemon_ids is None else "subset"
    log_event(logger, logging.INFO, "scan_started", run_id=run_id, scope=scope)
    try:
        status = _scan_steps(conn, fetch, run, pokemon_ids)
    except Exception as exc:
        log_exception(logger, "scan_crashed", exc, run_id=run_id)
        status = "failed"
    finally:
        if run.wrote_pokemon:
            pokemon_list.clear("scan", run_id=run_id)
    _finish(conn, run, status)
    return status


def scan_with_pokeapi(database_url: str, run_id: int, pokemon_ids: Sequence[int] | None) -> str:
    """Run a started scan against the real PokéAPI. Used by the trigger and `make sync`."""
    try:
        with db.connect(database_url) as conn, http_client() as client:
            conn.autocommit = True  # each Pokémon is its own transaction
            return run_scan(conn, PokeApiSource(client), run_id, pokemon_ids)
    except Exception as exc:
        # Reached only if the database fails; the run stays running until it goes stale.
        log_exception(logger, "scan_crashed", exc, run_id=run_id)
        return "failed"


def _scan_steps(conn: Conn, fetch: Fetch, run: Run, pokemon_ids: Sequence[int] | None) -> str:
    run.overrides = demo.load(conn)
    chart_ok = _scan_chart(conn, fetch, run)
    moves_ok = scan_moves.scan_moves(conn, fetch, run) if pokemon_ids is None else True
    listed = _read_list(conn, fetch, run)
    if listed is None:
        return "failed"
    wanted = listed if pokemon_ids is None else {i: listed[i] for i in pokemon_ids if i in listed}
    _scan_details(conn, fetch, run, wanted)
    if pokemon_ids is None:
        run.missing += scan_store.stored_not_listed(conn, listed)
    scan_store.apply_removals(conn, run)
    whole = chart_ok and moves_ok and run.complete and run.failed == 0
    return "ok" if whole else "incomplete"


def _scan_chart(conn: Conn, fetch: Fetch, run: Run) -> bool:
    """Fetch, check and store the type chart. On any problem the stored chart is kept."""
    try:
        listing = fetch(TYPE_LIST_PATH)
        urls = [entry["url"] for entry in listing["results"] if entry["name"] in STANDARD_TYPES]
        chart = build_chart([fetch(url) for url in urls])
    except UpstreamError as exc:
        _log_chart_rejected(run, f"fetch_{exc.reason}", "-")
        return False
    except ChartError as exc:
        _log_chart_rejected(run, exc.rule, outside(exc.detail))
        return False
    except (KeyError, TypeError):
        _log_chart_rejected(run, "malformed", "-")
        return False
    scan_store.save_chart(conn, run, run.overrides.apply_to_chart(chart))
    return True


def _read_list(conn: Conn, fetch: Fetch, run: Run) -> dict[int, str] | None:
    """Every listed Pokémon's ID and URL, or None if the list cannot be trusted."""
    count_row = conn.execute("SELECT count(*) FROM pokemon WHERE removed_at IS NULL").fetchone()
    stored = int(count_row[0]) if count_row else 0
    listed, reason = _fetch_list(fetch)
    if reason is None and len(listed) < MIN_LIST_SHARE * stored:
        reason = "shrunk"
    if reason is None:
        return listed
    log_event(
        logger,
        logging.ERROR,
        "list_rejected",
        run_id=run.run_id,
        reason=reason,
        listed=len(listed),
        stored=stored,
    )
    return None


def _fetch_list(fetch: Fetch) -> tuple[dict[int, str], str | None]:
    """The list as ID to URL, and the reason it is unusable, if it is."""
    try:
        listing = fetch(POKEMON_LIST_PATH)
        listed = {_id_from_url(entry["url"]): entry["url"] for entry in listing["results"]}
        counts_agree = len(listing["results"]) == len(listed) == listing["count"]
    except UpstreamError as exc:
        return {}, exc.reason
    except (KeyError, TypeError, ValueError):
        return {}, "malformed"
    return listed, None if counts_agree else "count_mismatch"


def _scan_details(conn: Conn, fetch: Fetch, run: Run, wanted: dict[int, str]) -> None:
    """Fetch and parse in four worker threads; save each result here, in list order."""
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for fetched in pool.map(partial(scan_fetch.fetch_one, fetch), wanted.items()):
            _apply_fetched(conn, run, fetched)


def _apply_fetched(conn: Conn, run: Run, fetched: scan_fetch.Fetched) -> None:
    """One of three cases: gone (a 404, or removed by the demo), read, or unreadable.

    A record read without its species flags or its move list is saved and also counted
    as unreadable; a move list that was not read leaves the stored one as it is.
    """
    gone = fetched.record is None and fetched.reason is None
    if gone or run.overrides.removes(fetched.pokemon_id):
        run.missing.append(fetched.pokemon_id)
        return
    if fetched.record is not None:
        scan_store.save_pokemon(conn, run, run.overrides.apply(fetched.record))
        if fetched.move_ids is not None:
            scan_store.save_move_list(conn, fetched.pokemon_id, fetched.move_ids)
    if fetched.reason is not None or fetched.moves_rule is not None:
        _count_unread(run, fetched)


def _count_unread(run: Run, fetched: scan_fetch.Fetched) -> None:
    """Part of this Pokémon could not be read: count it once in `failed`, log each part."""
    run.failed += 1
    ids = {"run_id": run.run_id, "pokemon_id": fetched.pokemon_id}
    if fetched.reason is not None:
        event = "pokemon_skipped" if fetched.record is None else "species_unread"
        rule = {"rule": fetched.rule} if fetched.rule else {}
        log_event(logger, logging.WARNING, event, **ids, reason=fetched.reason, **rule)
    if fetched.moves_rule is not None:
        log_event(logger, logging.WARNING, "moves_unread", **ids, rule=fetched.moves_rule)


def _finish(conn: Conn, run: Run, status: str) -> None:
    """Record how the run ended, unless a later trigger has already failed it as stale."""
    finished = run.now()
    recorded = conn.execute(
        "UPDATE scan_runs SET status = %s, finished_at = %s, scanned = %s, changed = %s,"
        " failed = %s WHERE id = %s AND status = 'running'",
        (status, finished, run.scanned, run.changed, run.failed, run.run_id),
    ).rowcount
    seconds = int((finished - run.started).total_seconds())
    log_event(
        logger,
        logging.ERROR if status == "failed" or not recorded else logging.INFO,
        "scan_finished" if recorded else "scan_finished_late",
        run_id=run.run_id,
        status=status,
        scanned=run.scanned,
        changed=run.changed,
        failed=run.failed,
        filled=run.filled,
        duration_s=seconds,
    )


def _log_retry(run_id: int, path: str, attempt: int, reason: str) -> None:
    log_event(
        logger,
        logging.INFO,
        "upstream_retry",
        run_id=run_id,
        path=outside(path),
        attempt=attempt,
        reason=reason,
    )


def _log_chart_rejected(run: Run, rule: str, detail: str) -> None:
    log_event(
        logger, logging.WARNING, "chart_rejected", run_id=run.run_id, rule=rule, detail=detail
    )


def _id_from_url(url: str) -> int:
    """The ID at the end of a list entry's URL, as in .../api/v2/pokemon/6/."""
    return int(url.rstrip("/").rsplit("/", 1)[1])


def main() -> int:
    """`make sync`: one full scan from the command line, for local development."""
    logs.configure()
    settings = load_settings()
    with db.connect(settings.database_url) as conn:
        db.apply_schema(conn)
        run_id = start_run(conn, "full", utc_now())
    status = scan_with_pokeapi(settings.database_url, run_id, None)
    return 1 if status == "failed" else 0


if __name__ == "__main__":
    sys.exit(main())
