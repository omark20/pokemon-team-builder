"""What a scan writes to the database: Pokémon rows, chart cells, changes and removals,
and the moves and each Pokémon's move list, which are stored as fetched and never diffed.

Each Pokémon is saved in its own transaction with its row locked, so a change row exists
if and only if a stored value that had been seen before moved. The column lists are
built from PokemonRecord's fields, so a field added to the record needs no edit here.
"""

import logging
from collections.abc import Callable
from dataclasses import astuple, dataclass, field
from datetime import datetime
from typing import Any, NamedTuple

from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app.db import Conn
from app.demo import Overrides
from app.domain.diff import RECORD_FIELDS, PokemonRecord, diff_chart, diff_pokemon
from app.domain.moves import Move
from app.domain.types import Chart
from app.logs import log_event

logger = logging.getLogger(__name__)

MAX_REMOVALS = 20  # more disappearances than this in one run is more likely an upstream fault


COLUMNS = sql.SQL(", ").join(sql.Identifier(name) for name in RECORD_FIELDS)
SELECT_ROW = sql.SQL("SELECT {}, removed_at FROM pokemon WHERE id = %s FOR UPDATE").format(COLUMNS)
INSERT_ROW = sql.SQL("INSERT INTO pokemon ({}) VALUES ({})").format(
    COLUMNS, sql.SQL(", ").join([sql.Placeholder()] * len(RECORD_FIELDS))
)
UPDATE_ROW = sql.SQL(
    "UPDATE pokemon SET {}, removed_at = NULL, updated_at = %s WHERE id = %s"
).format(sql.SQL(", ").join(sql.SQL("{} = %s").format(sql.Identifier(n)) for n in RECORD_FIELDS))


@dataclass
class Run:
    """One run's counts, written to scan_runs when it ends."""

    run_id: int
    now: Callable[[], datetime]
    started: datetime
    scanned: int = 0
    changed: int = 0
    failed: int = 0
    filled: int = 0  # Pokémon that had a new column filled for the first time
    complete: bool = True  # false once the removals had to be left alone (too many)
    wrote_pokemon: bool = False  # a Pokémon row was inserted, updated or flagged
    missing: list[int] = field(default_factory=list)  # candidates for removal
    overrides: Overrides = field(default_factory=Overrides)  # the demo's patches, if any


class ChangeRow(NamedTuple):
    """One row for the changes table: a Pokémon field, or a chart cell."""

    field: str
    old: Any
    new: Any
    pokemon_id: int | None = None
    attacker: str | None = None
    defender: str | None = None
    is_demo: bool = False  # the field was set by a demo patch


def save_chart(conn: Conn, run: Run, chart: Chart) -> None:
    """Store a checked chart. A cell that moved gets a change row; an empty table is filled."""
    with conn.transaction():
        cursor = conn.execute("SELECT attacker, defender, multiplier FROM type_effectiveness")
        stored = {(attacker, defender): value for attacker, defender, value in cursor}
        cells = diff_chart(stored, chart)
        demo_cells = _demo_cells(conn, run) if cells else set()
        rows = [
            ChangeRow(
                "multiplier",
                c.old,
                c.new,
                attacker=c.attacker,
                defender=c.defender,
                is_demo=(c.attacker, c.defender) in demo_cells,
            )
            for c in cells
        ]
        insert_changes(conn, run, rows)
        conn.cursor().executemany(
            "INSERT INTO type_effectiveness (attacker, defender, multiplier) VALUES (%s, %s, %s)"
            " ON CONFLICT (attacker, defender) DO UPDATE SET multiplier = EXCLUDED.multiplier",
            [(a, d, value) for (a, d), value in chart.items() if stored.get((a, d)) != value],
        )


def save_pokemon(conn: Conn, run: Run, record: PokemonRecord) -> None:
    """Insert a first sight, or diff against the stored row and write what moved.

    A field not read in this run keeps its stored value (the diff's `record`).
    """
    with conn.transaction():
        stored = conn.cursor(row_factory=dict_row).execute(SELECT_ROW, (record.id,)).fetchone()
        if stored is None:
            conn.execute(INSERT_ROW, [getattr(record, name) for name in RECORD_FIELDS])
            run.wrote_pokemon = True
        else:
            _update_if_changed(conn, run, stored, record)
    run.scanned += 1


def _update_if_changed(conn: Conn, run: Run, stored: dict[str, Any], record: PokemonRecord) -> None:
    diff = diff_pokemon(stored, record)
    values = [getattr(diff.record, name) for name in RECORD_FIELDS]
    restored = stored["removed_at"] is not None
    demo = _demo_fields(conn, run, record.id) if diff.changes or restored else set()
    rows = [
        ChangeRow(c.field, c.old, c.new, record.id, is_demo=c.field in demo) for c in diff.changes
    ]
    if restored:
        rows.append(
            ChangeRow("status", "removed", "available", record.id, is_demo="status" in demo)
        )
        log_event(logger, logging.INFO, "pokemon_restored", run_id=run.run_id, pokemon_id=record.id)
    if rows or diff.filled:
        conn.execute(UPDATE_ROW, [*values, run.now(), record.id])
        run.wrote_pokemon = True
    insert_changes(conn, run, rows)
    run.filled += bool(diff.filled)


def _demo_fields(conn: Conn, run: Run, pokemon_id: int) -> set[str]:
    """Fields whose change is demo: those the patch names, and those whose stored value
    a demo change put there and reset has not yet undone (so undoing it is demo too)."""
    rows = conn.execute(
        "SELECT DISTINCT field FROM changes WHERE is_demo AND pokemon_id = %s", (pokemon_id,)
    )
    return run.overrides.patched_fields(pokemon_id) | {field for (field,) in rows}


def _demo_cells(conn: Conn, run: Run) -> set[tuple[str, str]]:
    """The same for chart cells: patched now, or holding a value a demo change put there."""
    rows = conn.execute(
        "SELECT DISTINCT attacker, defender FROM changes WHERE is_demo AND attacker IS NOT NULL"
    )
    return set(run.overrides.chart) | {(attacker, defender) for attacker, defender in rows}


def save_moves(conn: Conn, moves: list[Move]) -> None:
    """Store each move as read, in one transaction: new ones added, stored ones replaced."""
    with conn.transaction():
        conn.cursor().executemany(
            "INSERT INTO moves (id, name, type, damage_class, power, accuracy, priority,"
            " short_effect) VALUES (%s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (id) DO UPDATE"
            " SET name = EXCLUDED.name, type = EXCLUDED.type,"
            " damage_class = EXCLUDED.damage_class, power = EXCLUDED.power,"
            " accuracy = EXCLUDED.accuracy, priority = EXCLUDED.priority,"
            " short_effect = EXCLUDED.short_effect",
            [astuple(move) for move in moves],
        )


def save_move_list(conn: Conn, pokemon_id: int, move_ids: list[int]) -> None:
    """Store the IDs of the moves a Pokémon's answer lists, replacing the stored ones."""
    conn.execute(
        "INSERT INTO pokemon_moves (pokemon_id, move_ids) VALUES (%s, %s)"
        " ON CONFLICT (pokemon_id) DO UPDATE SET move_ids = EXCLUDED.move_ids",
        (pokemon_id, move_ids),
    )


def stored_not_listed(conn: Conn, listed: dict[int, str]) -> list[int]:
    """Stored Pokémon not marked removed that the list no longer names."""
    rows = conn.execute("SELECT id FROM pokemon WHERE removed_at IS NULL ORDER BY id")
    return [pokemon_id for (pokemon_id,) in rows if pokemon_id not in listed]


def apply_removals(conn: Conn, run: Run) -> None:
    """Flag each candidate removed, keeping its data, unless there are too many."""
    if len(run.missing) > MAX_REMOVALS:
        count = len(run.missing)
        log_event(
            logger,
            logging.WARNING,
            "removals_refused",
            run_id=run.run_id,
            count=count,
            limit=MAX_REMOVALS,
        )
        run.complete = False
        return
    for pokemon_id in run.missing:
        with conn.transaction():
            flagged = conn.execute(
                "UPDATE pokemon SET removed_at = %s, updated_at = %s"
                " WHERE id = %s AND removed_at IS NULL RETURNING id",
                (run.now(), run.now(), pokemon_id),
            ).fetchone()
            if flagged:
                run.wrote_pokemon = True
                demo = "status" in _demo_fields(conn, run, pokemon_id)
                row = ChangeRow("status", "available", "removed", pokemon_id, is_demo=demo)
                insert_changes(conn, run, [row])
                log_event(
                    logger,
                    logging.INFO,
                    "pokemon_removed",
                    run_id=run.run_id,
                    pokemon_id=pokemon_id,
                )


def insert_changes(conn: Conn, run: Run, rows: list[ChangeRow]) -> None:
    """The one place change rows are written. Jsonb, so None is JSON null, not SQL NULL."""
    detected = run.now()
    conn.cursor().executemany(
        "INSERT INTO changes (pokemon_id, attacker, defender, field, old_value, new_value,"
        " detected_at, scan_run_id, is_demo) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
        [
            (r.pokemon_id, r.attacker, r.defender, r.field, Jsonb(r.old), Jsonb(r.new))
            + (detected, run.run_id, r.is_demo)
            for r in rows
        ],
    )
    run.changed += len(rows)
