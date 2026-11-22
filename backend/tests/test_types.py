"""The type chart built from the captured /type responses, and its consistency checks.

Expected values are written out by hand from the type chart (https://pokemondb.net/type)
and from the counts in samples/README.md, fact 13; none is copied from the code.
"""

import copy
import json
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from app.domain.types import STANDARD_TYPES, ChartError, build_chart, effectiveness

SAMPLES = Path(__file__).resolve().parents[2] / "samples"

# Every captured /type/{id} response: the 18 standard types and stellar, unknown, shadow.
TYPE_PAYLOADS = [json.loads(path.read_text()) for path in sorted(SAMPLES.glob("type_*_*.json"))]


@pytest.fixture(scope="module")
def chart() -> dict[tuple[str, str], float]:
    return build_chart(TYPE_PAYLOADS)


def test_all_21_captures_give_the_18_by_18_chart(chart: dict[tuple[str, str], float]) -> None:
    assert len(TYPE_PAYLOADS) == 21
    assert {attacker for attacker, _ in chart} == set(STANDARD_TYPES)
    assert {defender for _, defender in chart} == set(STANDARD_TYPES)
    assert Counter(chart.values()) == {2.0: 51, 0.5: 61, 0.0: 8, 1.0: 204}


def test_the_eight_immunities(chart: dict[tuple[str, str], float]) -> None:
    immune = {cell for cell, multiplier in chart.items() if multiplier == 0}
    assert immune == {
        ("normal", "ghost"),
        ("fighting", "ghost"),
        ("poison", "steel"),
        ("ground", "flying"),
        ("ghost", "normal"),
        ("electric", "ground"),
        ("psychic", "dark"),
        ("dragon", "fairy"),
    }


@pytest.mark.parametrize(
    ("attack_type", "defender_types", "expected"),
    [
        ("rock", ["fire", "flying"], 4),
        ("grass", ["fire", "flying"], 0.25),
        ("ground", ["fire", "flying"], 0),
        ("electric", ["water", "flying"], 4),
        ("fire", ["water"], 0.5),
        ("ice", ["dragon", "flying"], 4),
        ("fighting", ["normal"], 2),
        ("steel", ["fairy"], 2),
        ("water", ["water", "grass"], 0.25),
        ("normal", ["rock"], 0.5),
    ],
)
def test_effectiveness_multiplies_over_the_defenders_types(
    chart: dict[tuple[str, str], float],
    attack_type: str,
    defender_types: list[str],
    expected: float,
) -> None:
    assert effectiveness(chart, attack_type, defender_types) == expected


def _payload(payloads: list[dict[str, Any]], name: str) -> dict[str, Any]:
    return next(p for p in payloads if p["name"] == name)


def _drop_fairy(payloads: list[dict[str, Any]]) -> None:
    payloads.remove(_payload(payloads, "fairy"))


def _fire_loses_water_from_its_from_list(payloads: list[dict[str, Any]]) -> None:
    relations = _payload(payloads, "fire")["damage_relations"]
    relations["double_damage_from"] = [
        e for e in relations["double_damage_from"] if e["name"] != "water"
    ]


def _fire_names_stellar(payloads: list[dict[str, Any]]) -> None:
    _payload(payloads, "fire")["damage_relations"]["double_damage_to"].append({"name": "stellar"})


def _fire_lists_grass_twice(payloads: list[dict[str, Any]]) -> None:
    # Fire already does double damage to grass.
    _payload(payloads, "fire")["damage_relations"]["half_damage_to"].append({"name": "grass"})


@pytest.mark.parametrize(
    ("break_data", "rule", "detail"),
    [
        (_drop_fairy, "missing_type", "fairy"),
        (_fire_loses_water_from_its_from_list, "from_disagrees", "water>fire"),
        (_fire_names_stellar, "non_standard_type", "stellar"),
        (_fire_lists_grass_twice, "listed_twice", "fire>grass"),
    ],
)
def test_inconsistent_type_data_is_refused(
    break_data: Callable[[list[dict[str, Any]]], None], rule: str, detail: str
) -> None:
    payloads = copy.deepcopy(TYPE_PAYLOADS)
    break_data(payloads)
    with pytest.raises(ChartError) as refused:
        build_chart(payloads)
    assert (refused.value.rule, refused.value.detail) == (rule, detail)
