"""The stored Pokémon record: reading it from PokéAPI, and finding what changed.

`parse_pokemon` keeps the values the app shows or computes with and refuses any
response that breaks a rule, so a half-read record is never stored or reported as a
change; `parse_species` reads the two flags that come from the Pokémon's species.
`diff_pokemon` compares a stored row with a fresh record over the record's own fields,
so a field added to `PokemonRecord` is diffed without more code. `diff_chart` does the
same for the type chart, cell by cell. Pure: no web or database code.
"""

from collections.abc import Mapping
from dataclasses import dataclass, fields, replace
from typing import Any

from app.domain.types import STANDARD_TYPES, Chart

# Every response lists these six stats, in this order (samples/README.md, fact 5).
STAT_NAMES = ("hp", "attack", "defense", "special-attack", "special-defense", "speed")
SPRITE_PREFIX = "https://raw.githubusercontent.com/PokeAPI/sprites/"
MAX_BASE_STAT = 255  # the largest in the data (fact 10); the counter score's weights rely on it

# Fields PokéAPI itself may send as null. A stored null in any other field means the
# column is new and not yet filled (see diff_pokemon). Nine entries have no sprite (fact 11).
OPTIONAL_UPSTREAM = frozenset({"sprite_url"})


@dataclass(frozen=True)
class PokemonRecord:
    """One Pokémon as stored. Each field is a column of the `pokemon` table, same name."""

    id: int
    name: str
    is_default: bool  # false for alternate forms such as Mega Charizard X
    types: list[str]  # one or two, in PokéAPI's slot order
    hp: int
    attack: int
    defense: int
    special_attack: int
    special_defense: int
    speed: int
    sprite_url: str | None
    # From the species response, a second request; None until it has been read.
    is_legendary: bool | None = None
    is_mythical: bool | None = None


@dataclass(frozen=True)
class FieldChange:
    """A stored field whose value moved upstream."""

    field: str
    old: Any
    new: Any


@dataclass(frozen=True)
class PokemonDiff:
    """What a fresh record changes: recorded changes, and new columns to fill silently."""

    changes: tuple[FieldChange, ...]
    filled: tuple[str, ...]
    record: PokemonRecord  # what to store: the fetched record, unread fields as stored


@dataclass(frozen=True)
class CellChange:
    """A type-chart cell whose multiplier moved upstream."""

    attacker: str
    defender: str
    old: float
    new: float


class ParseError(ValueError):
    """A detail response broke a rule. `rule` names it, for the scan's skip log line."""

    def __init__(self, rule: str) -> None:
        super().__init__(rule)
        self.rule = rule


RECORD_FIELDS = tuple(field.name for field in fields(PokemonRecord))


def parse_pokemon(payload: Mapping[str, Any]) -> PokemonRecord:
    """Read a /pokemon/{id} response into a record, or raise ParseError naming the rule."""
    try:
        return _read_record(payload)
    except (KeyError, TypeError, AttributeError) as exc:
        raise ParseError("malformed") from exc


def parse_species(payload: Mapping[str, Any]) -> tuple[bool, bool]:
    """Read a /pokemon-species/{id} response's (is_legendary, is_mythical), or raise ParseError."""
    try:
        flags = payload["is_legendary"], payload["is_mythical"]
    except (KeyError, TypeError) as exc:
        raise ParseError("malformed") from exc
    check(all(isinstance(flag, bool) for flag in flags), "species_flags")
    return flags


def species_url(payload: Mapping[str, Any]) -> str:
    """The species URL a /pokemon/{id} response names (samples/README.md, fact 17)."""
    species = payload.get("species")
    url = species.get("url") if isinstance(species, Mapping) else None
    if not isinstance(url, str):
        raise ParseError("species_url")
    return url


def _keep_unread(stored: Mapping[str, Any], fetched: PokemonRecord) -> PokemonRecord:
    """The fetched record, with every field not read in this run taken from the stored row.

    A None in a field PokéAPI never sends as null (one not in OPTIONAL_UPSTREAM) means
    its request failed this run, so the stored value stands: no change, no fill.
    """
    unread = [
        n for n in RECORD_FIELDS if getattr(fetched, n) is None and n not in OPTIONAL_UPSTREAM
    ]
    return replace(fetched, **{name: stored[name] for name in unread})


def diff_pokemon(stored: Mapping[str, Any], fetched: PokemonRecord) -> PokemonDiff:
    """Compare a stored row with a fresh record, over every field of the record.

    A stored SQL NULL in a field not in OPTIONAL_UPSTREAM is a column added since the
    last scan: it is filled with no change recorded, or every user would be alerted
    about a change that never happened upstream. A field not read in this run is left
    as stored (`_keep_unread`), and the record to store is returned with the diff.
    """
    fetched = _keep_unread(stored, fetched)
    changes: list[FieldChange] = []
    filled: list[str] = []
    for name in RECORD_FIELDS:
        old, new = stored[name], getattr(fetched, name)
        if old == new:
            continue
        if old is None and name not in OPTIONAL_UPSTREAM:
            filled.append(name)
        else:
            changes.append(FieldChange(name, old, new))
    return PokemonDiff(tuple(changes), tuple(filled), fetched)


def diff_chart(stored: Chart, fetched: Chart) -> list[CellChange]:
    """The cells whose multiplier differs. A cell not stored yet is a fill, not a change."""
    return [
        CellChange(attacker, defender, stored[attacker, defender], new)
        for (attacker, defender), new in fetched.items()
        if (attacker, defender) in stored and stored[attacker, defender] != new
    ]


def _read_record(payload: Mapping[str, Any]) -> PokemonRecord:
    pokemon_id, name, is_default = payload["id"], payload["name"], payload["is_default"]
    check(is_int(pokemon_id) and pokemon_id > 0, "id")
    check(isinstance(name, str) and name != "", "name")
    check(isinstance(is_default, bool), "is_default")
    stats = _parse_stats(payload["stats"])
    return PokemonRecord(
        id=pokemon_id,
        name=name,
        is_default=is_default,
        types=_parse_types(payload["types"]),
        hp=stats["hp"],
        attack=stats["attack"],
        defense=stats["defense"],
        special_attack=stats["special-attack"],
        special_defense=stats["special-defense"],
        speed=stats["speed"],
        sprite_url=_parse_sprite(payload["sprites"]["front_default"]),
    )


def check(holds: bool, rule: str) -> None:
    if not holds:
        raise ParseError(rule)


def is_int(value: Any) -> bool:
    # bool is a subclass of int in Python; true and false are not numbers here.
    return isinstance(value, int) and not isinstance(value, bool)


def _parse_types(entries: list[Mapping[str, Any]]) -> list[str]:
    """One or two standard types, slots numbered 1..n, no type twice."""
    ordered = sorted(entries, key=lambda entry: entry["slot"])
    names = [entry["type"]["name"] for entry in ordered]
    slots = [entry["slot"] for entry in ordered]
    check(len(names) in (1, 2), "type_count")
    check(slots == list(range(1, len(names) + 1)), "type_slots")
    check(len(set(names)) == len(names), "type_repeated")
    check(all(name in STANDARD_TYPES for name in names), "type_unknown")
    return names


def _parse_stats(entries: list[Mapping[str, Any]]) -> dict[str, int]:
    """The six base stats by name, each a whole number from 0 to 255."""
    stats = {entry["stat"]["name"]: entry["base_stat"] for entry in entries}
    check(len(entries) == len(STAT_NAMES) and set(stats) == set(STAT_NAMES), "stat_names")
    check(all(is_int(v) and 0 <= v <= MAX_BASE_STAT for v in stats.values()), "stat_value")
    return stats


def _parse_sprite(url: object) -> str | None:
    """No sprite, or an image on PokéAPI's sprite host (samples/README.md, fact 8)."""
    if url is None or (isinstance(url, str) and url.startswith(SPRITE_PREFIX)):
        return url
    raise ParseError("sprite_url")
