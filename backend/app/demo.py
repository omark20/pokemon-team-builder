"""The Task 2 demo: make the scan believe PokéAPI said something else, then undo it.

The demo never writes a change or an alert itself. A stored document of patches is read
at the start of a scan; each patch replaces fields of a record after it is fetched and
parsed, before the ordinary diff, so the change goes through exactly the scheduled job's
path. Change rows for patched fields are tagged `is_demo`, and reset writes their old
values back, newest first, then deletes them, so the next real scan finds nothing to do.
"""

from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any

from psycopg import sql
from psycopg.types.json import Jsonb

from app.db import Conn
from app.domain.diff import RECORD_FIELDS, PokemonRecord
from app.domain.types import Chart


@dataclass(frozen=True)
class Overrides:
    """The stored document, ready for the scan: patches by Pokémon ID, and chart cells."""

    pokemon: dict[int, dict[str, Any]] = field(default_factory=dict)
    chart: dict[tuple[str, str], float] = field(default_factory=dict)

    def patched_fields(self, pokemon_id: int) -> set[str]:
        """The fields a patch names; a removal is recorded on the `status` field."""
        names = set(self.pokemon.get(pokemon_id, {}))
        return names - {"removed"} | ({"status"} if "removed" in names else set())

    def removes(self, pokemon_id: int) -> bool:
        return bool(self.pokemon.get(pokemon_id, {}).get("removed"))

    def apply(self, record: PokemonRecord) -> PokemonRecord:
        """The record with its patch's fields replaced."""
        patch = {k: v for k, v in self.pokemon.get(record.id, {}).items() if k != "removed"}
        return replace(record, **patch)

    def apply_to_chart(self, chart: Chart) -> Chart:
        return chart | self.chart


def load(conn: Conn) -> Overrides:
    """The stored document, or no overrides."""
    row = conn.execute("SELECT doc FROM demo_overrides").fetchone()
    if row is None:
        return Overrides()
    doc = row[0]
    return Overrides(
        pokemon={int(pokemon_id): patch for pokemon_id, patch in doc["pokemon"].items()},
        chart={(c["attacker"], c["defender"]): float(c["multiplier"]) for c in doc["type_chart"]},
    )


def store(conn: Conn, doc: dict[str, Any]) -> None:
    """Replace the document. Nothing else changes until a scan runs."""
    conn.execute(
        "INSERT INTO demo_overrides (doc) VALUES (%s)"
        " ON CONFLICT (only_row) DO UPDATE SET doc = EXCLUDED.doc",
        (Jsonb(doc),),
    )


def is_active(conn: Conn) -> bool:
    """True while a document exists or any demo change is still recorded."""
    row = conn.execute(
        "SELECT EXISTS (SELECT 1 FROM demo_overrides)"
        " OR EXISTS (SELECT 1 FROM changes WHERE is_demo)"
    ).fetchone()
    return bool(row and row[0])


def scan_in_progress(conn: Conn, started_after: datetime) -> bool:
    """Whether a scan started after this time is running; no new one starts until commit.

    The lock conflicts with the INSERT that starts a scan (PostgreSQL 18 docs, "Explicit
    Locking": INSERT takes ROW EXCLUSIVE, which SHARE ROW EXCLUSIVE blocks), so a trigger
    arriving meanwhile waits for this transaction instead of racing it.
    """
    conn.execute("LOCK TABLE scan_runs IN SHARE ROW EXCLUSIVE MODE")
    row = conn.execute(
        "SELECT EXISTS (SELECT 1 FROM scan_runs WHERE status = 'running' AND started_at > %s)",
        (started_after,),
    ).fetchone()
    return bool(row and row[0])


def reset(conn: Conn) -> dict[str, int]:
    """Delete the document, write back every demo change's old value, delete those changes.

    Only the rows read and restored here are deleted, never a row committed meanwhile.
    """
    conn.execute("DELETE FROM demo_overrides")
    changes = conn.execute(
        "SELECT id, pokemon_id, attacker, defender, field, old_value FROM changes"
        " WHERE is_demo ORDER BY id DESC"
    ).fetchall()
    for _, pokemon_id, attacker, defender, name, old in changes:
        _restore(conn, pokemon_id, attacker, defender, name, old)
    restored = [change_id for change_id, *_ in changes]
    deleted = conn.execute("DELETE FROM changes WHERE id = ANY(%s)", (restored,)).rowcount
    return {"restored": len(changes), "deleted": deleted}


def _restore(
    conn: Conn,
    pokemon_id: int | None,
    attacker: str | None,
    defender: str | None,
    name: str,
    old: Any,
) -> None:
    if pokemon_id is None:
        conn.execute(
            "UPDATE type_effectiveness SET multiplier = %s WHERE attacker = %s AND defender = %s",
            (old, attacker, defender),
        )
    elif name == "status":
        # "removed" comes back when a demo removal was undone before reset: unwinding
        # newest first passes through it on the way to the older "available".
        removed_at = sql.SQL("NULL" if old == "available" else "now()")
        conn.execute(
            sql.SQL("UPDATE pokemon SET removed_at = {} WHERE id = %s").format(removed_at),
            (pokemon_id,),
        )
    else:
        # The one dynamic column name: allowed only if it is one of the record's fields.
        if name not in RECORD_FIELDS:
            raise ValueError("demo change names an unknown field")
        column = sql.Identifier(name)
        conn.execute(
            sql.SQL("UPDATE pokemon SET {} = %s WHERE id = %s").format(column), (old, pokemon_id)
        )
