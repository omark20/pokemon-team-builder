"""The scan's last step: every Pokémon's four moves and every field Pokémon's baseline.

Full runs only, after removals, from what is stored: the four each Pokémon carries
(domain/default_moves.py), then for each Pokémon of the field its duel margins against
the whole field added up (domain/counter_score.py). The field is who may be a counter:
default forms PokéAPI still lists. The baselines are the long part, so the loop sleeps
a few milliseconds after each Pokémon and the web requests running beside it in the
same process are not slowed. Both are stored in place of the last ones in one
transaction. If this step is skipped or fails, the stored rows stay as they were and
the run ends incomplete; nothing else in the scan is undone.
"""

import logging
import time
from collections.abc import Callable
from dataclasses import replace

from app import duel_store
from app.db import Conn
from app.domain.counter import candidate_pool
from app.domain.counter_score import margin_sum
from app.domain.default_moves import default_four, field_types
from app.domain.moves import Move
from app.domain.pokemon import Pokemon
from app.domain.types import Chart
from app.logs import log_event, log_exception
from app.scan_store import Run

logger = logging.getLogger(__name__)

PAUSE_SECONDS = 0.005  # after each baseline, so requests served meanwhile are not slowed


def refresh(conn: Conn, run: Run, sleep: Callable[[float], None] = time.sleep) -> bool:
    """Work out and store every four and baseline; True if they were stored."""
    try:
        return _refresh(conn, run, sleep)
    except Exception as exc:  # the scan's other results stand; only this step failed
        log_exception(logger, "duel_data_failed", exc, run_id=run.run_id)
        return False


def _refresh(conn: Conn, run: Run, sleep: Callable[[float], None]) -> bool:
    chart, moves = duel_store.load_chart(conn), duel_store.load_moves(conn)
    if chart is None or not moves:
        reason = "chart_incomplete" if chart is None else "no_moves"
        log_event(logger, logging.WARNING, "duel_data_skipped", run_id=run.run_id, reason=reason)
        return False
    started = time.monotonic()
    armed = _with_fours(duel_store.load_learnable(conn), moves, chart)
    armed_at = time.monotonic()
    field = candidate_pool(armed)
    baselines = {}
    for candidate in field:
        baselines[candidate.id] = margin_sum(candidate, field, chart)
        sleep(PAUSE_SECONDS)
    rows = [(p.id, [move.id for move in p.moves], baselines.get(p.id)) for p in armed]
    duel_store.replace_duel_data(conn, rows)
    log_event(
        logger,
        logging.INFO,
        "duel_data_stored",
        run_id=run.run_id,
        pokemon=len(rows),
        field=len(field),
        fours_s=f"{armed_at - started:.1f}",
        baselines_s=f"{time.monotonic() - armed_at:.1f}",
    )
    return True


def _with_fours(
    learnable: list[tuple[Pokemon, list[int]]], moves: dict[int, Move], chart: Chart
) -> list[Pokemon]:
    """Every Pokémon carrying its four, chosen from the stored moves its list names."""
    field = field_types(pokemon for pokemon, _ in learnable)
    armed = []
    for pokemon, move_ids in learnable:
        known = [moves[move_id] for move_id in move_ids if move_id in moves]
        four = default_four(pokemon, known, field, chart)
        armed.append(replace(pokemon, moves=tuple(moves[move_id] for move_id in four)))
    return armed
