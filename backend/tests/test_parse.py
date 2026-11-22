"""Reading a /pokemon/{id} response: what is kept, and which responses are refused.

Expected values are read off the captured responses in samples/ by hand.
"""

import copy
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from app.domain.diff import ParseError, PokemonRecord, parse_pokemon

SAMPLES = Path(__file__).resolve().parents[2] / "samples"


def load(name: str) -> dict[str, Any]:
    payload: dict[str, Any] = json.loads((SAMPLES / name).read_text())
    return payload


CHARIZARD = load("pokemon_6_charizard_dual_type.json")


def test_charizard_keeps_its_ten_values() -> None:
    assert parse_pokemon(CHARIZARD) == PokemonRecord(
        id=6,
        name="charizard",
        is_default=True,
        types=["fire", "flying"],
        hp=78,
        attack=84,
        defense=78,
        special_attack=109,
        special_defense=85,
        speed=100,
        sprite_url="https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/6.png",
    )


@pytest.mark.parametrize(
    ("sample", "field", "expected"),
    [
        ("pokemon_25_pikachu_single_type.json", "types", ["electric"]),
        ("pokemon_10034_nondefault_form.json", "is_default", False),
        ("pokemon_10034_nondefault_form.json", "types", ["fire", "dragon"]),
        ("pokemon_10264_null_sprite.json", "sprite_url", None),
    ],
)
def test_captured_responses_parse(sample: str, field: str, expected: object) -> None:
    assert getattr(parse_pokemon(load(sample)), field) == expected


def _three_types(payload: dict[str, Any]) -> None:
    payload["types"].append({"slot": 3, "type": {"name": "dragon"}})


def _no_speed(payload: dict[str, Any]) -> None:
    payload["stats"] = [s for s in payload["stats"] if s["stat"]["name"] != "speed"]


def _stellar_type(payload: dict[str, Any]) -> None:
    payload["types"][1]["type"]["name"] = "stellar"


def _foreign_sprite(payload: dict[str, Any]) -> None:
    payload["sprites"]["front_default"] = "https://example.com/6.png"


def _stat_256(payload: dict[str, Any]) -> None:
    payload["stats"][0]["base_stat"] = 256


def _no_types_key(payload: dict[str, Any]) -> None:
    del payload["types"]


@pytest.mark.parametrize(
    ("break_payload", "rule"),
    [
        (_three_types, "type_count"),
        (_no_speed, "stat_names"),
        (_stellar_type, "type_unknown"),
        (_foreign_sprite, "sprite_url"),
        (_stat_256, "stat_value"),
        (_no_types_key, "malformed"),
    ],
)
def test_responses_breaking_a_rule_are_refused(
    break_payload: Callable[[dict[str, Any]], None], rule: str
) -> None:
    payload = copy.deepcopy(CHARIZARD)
    break_payload(payload)
    with pytest.raises(ParseError) as refused:
        parse_pokemon(payload)
    assert refused.value.rule == rule
