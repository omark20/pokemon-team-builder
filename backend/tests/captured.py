"""The captured PokéAPI data in samples/, read into the counter team's records for tests.

Every Pokémon comes from samples/census_all_pokemon.tsv with its species' flags from
samples/census_all_species.tsv; every move from samples/census_all_moves.tsv; the
moves a Pokémon can learn only from the 14 captured /pokemon answers that list them.
"""

import csv
import dataclasses
import json
from pathlib import Path

from app.domain.default_moves import default_four, field_types
from app.domain.moves import Move, parse_move_ids
from app.domain.pokemon import Pokemon
from app.domain.types import build_chart

SAMPLES = Path(__file__).resolve().parents[2] / "samples"
STAT_COLUMNS = ("hp", "attack", "defense", "special-attack", "special-defense", "speed")


def _rows(name: str) -> list[dict[str, str]]:
    with (SAMPLES / name).open() as file:
        return list(csv.DictReader(file, delimiter="\t"))


def _number(text: str) -> int | None:
    return int(text) if text else None


def load_moves() -> dict[int, Move]:
    """Every move PokéAPI lists, by ID."""
    return {
        int(row["id"]): Move(
            int(row["id"]),
            row["name"],
            row["type"],
            row["damage_class"],
            _number(row["power"]),
            _number(row["accuracy"]),
            int(row["priority"]),
            row["short_effect_en"] or None,
        )
        for row in _rows("census_all_moves.tsv")
    }


def load_species_flags() -> dict[int, tuple[bool, bool]]:
    """(is_legendary, is_mythical) by Pokémon ID; every variety takes its species' flags."""
    flags = {}
    for row in _rows("census_all_species.tsv"):
        for variety in row["varieties"].split(","):
            flags[int(variety.split(":")[0])] = (
                row["is_legendary"] == "true",
                row["is_mythical"] == "true",
            )
    return flags


def load_census() -> dict[str, Pokemon]:
    """Every Pokémon, by name, without moves."""
    flags = load_species_flags()
    census = {}
    for row in _rows("census_all_pokemon.tsv"):
        legendary, mythical = flags[int(row["id"])]
        census[row["name"]] = Pokemon(
            id=int(row["id"]),
            name=row["name"],
            types=tuple(row["types"].split("/")),
            stats=tuple(int(row[column]) for column in STAT_COLUMNS),
            is_default=row["is_default"] == "true",
            is_legendary=legendary,
            is_mythical=mythical,
        )
    return census


MOVES = load_moves()
CENSUS = load_census()
CHART = build_chart(json.loads(path.read_text()) for path in SAMPLES.glob("type_*_*.json"))
FIELD = field_types(CENSUS.values())


def learnable(capture: str) -> list[Move]:
    """The moves listed in one captured /pokemon answer, e.g. "pokemon_248_tyranitar"."""
    payload = json.loads((SAMPLES / f"{capture}.json").read_text())
    return [MOVES[move_id] for move_id in parse_move_ids(payload)]


def armed(name: str, capture: str) -> Pokemon:
    """A census Pokémon carrying its four, worked out from its captured move list."""
    moves = learnable(capture)
    four = default_four(CENSUS[name], moves, FIELD, CHART)
    return dataclasses.replace(
        CENSUS[name], moves=tuple(MOVES[move_id] for move_id in four), moves_listed=bool(moves)
    )
