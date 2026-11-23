"""The scan's moves step: every move PokéAPI lists, fetched and stored as fetched.

Full runs only, before the Pokémon: one list request, then one request per listed move,
four at a time, in worker threads that return a small result each. Moves are not part
of a Pokémon's record, so nothing here is diffed or raises an alert. Failures never
erase or blank stored data: a move that cannot be read keeps its stored row and gets
one log line, and a list that cannot be read skips the step and leaves every stored
move as it is. Either way the step reports that it was not whole, and the run ends
incomplete. No move is ever deleted.
"""

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from functools import partial

from app import scan_store
from app.db import Conn
from app.domain.diff import ParseError
from app.domain.moves import Move, parse_move, parse_move_list
from app.logs import log_event
from app.pokeapi import WORKERS, UpstreamError
from app.scan_fetch import Fetch
from app.scan_store import Run

logger = logging.getLogger(__name__)

MOVE_LIST_PATH = "move?limit=100000"  # the request samples/move_list_full.json answers


@dataclass(frozen=True)
class Unread:
    """A move whose answer could not be used, and why."""

    move_id: int
    reason: str
    rule: str | None = None


def scan_moves(conn: Conn, fetch: Fetch, run: Run) -> bool:
    """Fetch the move list and every listed move and store each one read; True if all were."""
    listed = _read_move_list(fetch, run)
    if listed is None:
        return False
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        results = list(pool.map(partial(_fetch_move, fetch), listed.items()))
    moves = [result for result in results if isinstance(result, Move)]
    for result in results:
        if isinstance(result, Unread):
            _log_unread(run, result)
    scan_store.save_moves(conn, moves)
    unread = len(listed) - len(moves)
    level = logging.WARNING if unread else logging.INFO
    log_event(logger, level, "moves_scanned", run_id=run.run_id, stored=len(moves), unread=unread)
    return unread == 0


def _read_move_list(fetch: Fetch, run: Run) -> dict[int, str] | None:
    """The listed moves as ID to URL, or None, with a log line, if the list is unusable."""
    rule: str | None = None
    try:
        return parse_move_list(fetch(MOVE_LIST_PATH))
    except UpstreamError as exc:
        reason = exc.reason
    except ParseError as exc:
        reason, rule = "parse_error", exc.rule
    details = {"rule": rule} if rule else {}
    log_event(
        logger, logging.ERROR, "move_list_rejected", run_id=run.run_id, reason=reason, **details
    )
    return None


def _fetch_move(fetch: Fetch, item: tuple[int, str]) -> Move | Unread:
    """Runs in a worker: fetch one move by its listed URL and parse it; drop the body."""
    move_id, url = item
    try:
        payload = fetch(url)
    except UpstreamError as exc:
        return Unread(move_id, exc.reason)
    if payload is None:
        return Unread(move_id, "http_404")
    try:
        move = parse_move(payload)
    except ParseError as exc:
        return Unread(move_id, "parse_error", exc.rule)
    return move if move.id == move_id else Unread(move_id, "parse_error", "id_mismatch")


def _log_unread(run: Run, unread: Unread) -> None:
    rule = {"rule": unread.rule} if unread.rule else {}
    log_event(
        logger,
        logging.WARNING,
        "move_unread",
        run_id=run.run_id,
        move_id=unread.move_id,
        reason=unread.reason,
        **rule,
    )
