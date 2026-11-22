"""Finding what changed: per field for a Pokémon, per cell for the type chart."""

import ast
import sys
from dataclasses import asdict, replace
from pathlib import Path

import pytest

from app.domain.diff import (
    RECORD_FIELDS,
    CellChange,
    FieldChange,
    PokemonRecord,
    diff_chart,
    diff_pokemon,
)

SPRITE = "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/6.png"
CHARIZARD = PokemonRecord(
    6, "charizard", True, ["fire", "flying"], 78, 84, 78, 109, 85, 100, SPRITE
)

# A different value for every field. A field added to the record without a row here
# fails the parametrised test below, so no stored field can go undiffed.
ALTERED = {
    "id": 7,
    "name": "charizard-mega-x",
    "is_default": False,
    "types": ["fire", "dragon"],
    "hp": 79,
    "attack": 130,
    "defense": 111,
    "special_attack": 130,
    "special_defense": 86,
    "speed": 101,
    "sprite_url": "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/10034.png",
}

DOMAIN = Path(__file__).resolve().parents[1] / "app" / "domain"


def test_identical_records_give_nothing() -> None:
    diff = diff_pokemon(asdict(CHARIZARD), CHARIZARD)
    assert (diff.changes, diff.filled) == ((), ())


@pytest.mark.parametrize("field", RECORD_FIELDS)
def test_each_field_changed_alone_gives_one_change(field: str) -> None:
    diff = diff_pokemon(asdict(CHARIZARD), replace(CHARIZARD, **{field: ALTERED[field]}))
    assert diff.changes == (FieldChange(field, getattr(CHARIZARD, field), ALTERED[field]),)
    assert diff.filled == ()


def test_two_fields_changed_give_two_changes() -> None:
    diff = diff_pokemon(asdict(CHARIZARD), replace(CHARIZARD, attack=94, types=["fire"]))
    assert diff.changes == (
        FieldChange("types", ["fire", "flying"], ["fire"]),
        FieldChange("attack", 84, 94),
    )


def test_empty_new_column_is_filled_without_a_change() -> None:
    stored = asdict(CHARIZARD) | {"speed": None}
    diff = diff_pokemon(stored, CHARIZARD)
    assert (diff.changes, diff.filled) == ((), ("speed",))


@pytest.mark.parametrize(("old", "new"), [(None, SPRITE), (SPRITE, None)])
def test_sprite_appearing_or_disappearing_is_a_change(old: str | None, new: str | None) -> None:
    diff = diff_pokemon(asdict(CHARIZARD) | {"sprite_url": old}, replace(CHARIZARD, sprite_url=new))
    assert (diff.changes, diff.filled) == ((FieldChange("sprite_url", old, new),), ())


def test_chart_diff_reports_exactly_the_altered_cells() -> None:
    stored = {("fire", "grass"): 2.0, ("water", "fire"): 2.0, ("normal", "ghost"): 0.0}
    fetched = stored | {("fire", "grass"): 1.0, ("normal", "ghost"): 0.5}
    assert diff_chart(stored, fetched) == [
        CellChange("fire", "grass", 2.0, 1.0),
        CellChange("normal", "ghost", 0.0, 0.5),
    ]


def test_chart_into_an_empty_table_is_a_fill_not_a_change() -> None:
    assert diff_chart({}, {("fire", "grass"): 2.0}) == []


@pytest.mark.parametrize("module", sorted(DOMAIN.glob("*.py")), ids=lambda path: path.name)
def test_domain_modules_import_only_the_standard_library_and_each_other(module: Path) -> None:
    for node in ast.walk(ast.parse(module.read_text())):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
        else:
            continue
        for name in names:
            assert name.startswith("app.domain") or name.split(".")[0] in sys.stdlib_module_names
