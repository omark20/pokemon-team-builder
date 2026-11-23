"""The counter team's reads from the database, and the one table the scan writes for it.

The loaders turn stored rows into the pure core's records (domain/pokemon.py): the
type chart, the moves, and every Pokémon, either with the whole list of moves it can
learn (for the scan, which works out its four) or with the four it carries and its
baseline (for a counter request). `replace_duel_data` stores what the scan worked out.
"""

from collections.abc import Iterable
from dataclasses import dataclass, replace
from typing import Any

from app.db import Conn
from app.domain.moves import Move
from app.domain.pokemon import Pokemon
from app.domain.types import Chart

CHART_CELLS = 18 * 18
POKEMON_COLUMNS = (
    "p.id, p.name, p.types,"
    " ARRAY[p.hp, p.attack, p.defense, p.special_attack, p.special_defense, p.speed],"
    " p.is_default, p.removed_at IS NOT NULL, p.is_legendary, p.is_mythical"
)
MOVE_COLUMNS = "id, name, type, damage_class, power, accuracy, priority, short_effect"
# Every Pokémon with the IDs of the moves it can learn; null where its answer is unread.
LEARNABLE_QUERY = (
    f"SELECT {POKEMON_COLUMNS}, m.move_ids FROM pokemon p"
    " LEFT JOIN pokemon_moves m ON m.pokemon_id = p.id ORDER BY p.id"
)
# Every Pokémon with its four and baseline, and whether PokéAPI lists no moves for it.
FIGHTERS_QUERY = (
    f"SELECT {POKEMON_COLUMNS}, d.move_ids, d.baseline, m.move_ids = '{{}}' FROM pokemon p"
    " LEFT JOIN duel_data d ON d.pokemon_id = p.id"
    " LEFT JOIN pokemon_moves m ON m.pokemon_id = p.id ORDER BY p.id"
)
CARRIED_MOVES_QUERY = (
    f"SELECT {MOVE_COLUMNS} FROM moves WHERE id IN (SELECT unnest(move_ids) FROM duel_data)"
)


@dataclass(frozen=True)
class Fighters:
    """Every stored Pokémon with the four moves it carries, and the field: those of them
    with a stored baseline, the only ones that may be counters."""

    by_id: dict[int, Pokemon]
    field: list[Pokemon]


def load_chart(conn: Conn) -> Chart | None:
    """The stored type chart, or None until a scan has stored all of it."""
    rows = conn.execute("SELECT attacker, defender, multiplier FROM type_effectiveness")
    chart = {(attacker, defender): value for attacker, defender, value in rows}
    return chart if len(chart) == CHART_CELLS else None


def load_moves(conn: Conn) -> dict[int, Move]:
    """Every stored move by ID."""
    return {row[0]: Move(*row) for row in conn.execute(f"SELECT {MOVE_COLUMNS} FROM moves")}


def load_learnable(conn: Conn) -> list[tuple[Pokemon, list[int]]]:
    """Every stored Pokémon, carrying no moves yet, with the IDs of every move it can learn."""
    return [(_pokemon(row), row[8] or []) for row in conn.execute(LEARNABLE_QUERY)]


def load_fighters(conn: Conn) -> Fighters | None:
    """Every stored Pokémon with its four and baseline, or None until a scan has stored them.

    A Pokémon stored after the last refresh has no row: it carries no moves and is not
    in the field.
    """
    carried = {row[0]: Move(*row) for row in conn.execute(CARRIED_MOVES_QUERY)}
    by_id: dict[int, Pokemon] = {}
    field: list[Pokemon] = []
    for row in conn.execute(FIGHTERS_QUERY):
        four, baseline, none_listed = row[8:]
        pokemon = replace(
            _pokemon(row),
            moves=tuple(carried[move_id] for move_id in four or ()),
            moves_listed=not none_listed,
            baseline=baseline or 0,
        )
        by_id[pokemon.id] = pokemon
        if baseline is not None:
            field.append(pokemon)
    return Fighters(by_id, field) if field else None


def replace_duel_data(conn: Conn, rows: Iterable[tuple[int, list[int], int | None]]) -> None:
    """Store every Pokémon's four and baseline in place of the last ones, in one
    transaction, so a request reads either the old rows or the new ones."""
    with conn.transaction():
        conn.execute("DELETE FROM duel_data")
        conn.cursor().executemany(
            "INSERT INTO duel_data (pokemon_id, move_ids, baseline) VALUES (%s, %s, %s)", rows
        )


def _pokemon(row: tuple[Any, ...]) -> Pokemon:
    pokemon_id, name, types, stats, is_default, removed, legendary, mythical = row[:8]
    return Pokemon(
        pokemon_id, name, tuple(types), tuple(stats), is_default, removed, legendary, mythical
    )
