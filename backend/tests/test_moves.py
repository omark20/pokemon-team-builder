"""The move parsers against the captured answers in samples/.

Expected values come from census_all_moves.tsv, one row per move extracted separately
from the same sweep, and from the moves' own `learned_by_pokemon` lists; neither is
read through the code under test.
"""

import copy
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from fake_pokeapi import SAMPLES, census_moves

from app.domain.diff import ParseError
from app.domain.moves import parse_move, parse_move_ids, parse_move_list

MOVE_FILES = sorted(SAMPLES.glob("move_[0-9]*_*.json"))
POKEMON_FILES = sorted(SAMPLES.glob("pokemon_[0-9]*_*.json"))


def load(path: Path) -> Any:
    return json.loads(path.read_text())


CENSUS = census_moves()
FLAMETHROWER = load(SAMPLES / "move_53_flamethrower.json")


@pytest.mark.parametrize("path", MOVE_FILES, ids=[path.stem for path in MOVE_FILES])
def test_each_captured_move_reads_as_the_census_records_it(path: Path) -> None:
    body = load(path)
    assert replace(parse_move(body), short_effect=None) == CENSUS[body["id"]]


@pytest.mark.parametrize(
    ("name", "text"),
    [
        ("move_129_swift_null_accuracy", "Never misses."),
        ("move_153_explosion_user_faints", "User faints."),
        ("move_827_dire_claw_null_meta", None),
    ],
)
def test_the_english_short_effect_is_kept_and_may_be_missing(name: str, text: str | None) -> None:
    assert parse_move(load(SAMPLES / f"{name}.json")).short_effect == text


def test_an_english_entry_listed_twice_is_one_text() -> None:
    body = copy.deepcopy(FLAMETHROWER)
    body["effect_entries"].append(copy.deepcopy(body["effect_entries"][1]))  # as scale-shot
    assert parse_move(body).short_effect == "Has a chance to burn the target."


def test_the_captured_list_reads_as_every_move_in_the_census() -> None:
    listed = parse_move_list(load(SAMPLES / "move_list_full.json"))
    assert sorted(listed) == sorted(CENSUS)
    assert listed[444] == "https://pokeapi.co/api/v2/move/444/"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("power", 0),
        ("power", 255),
        ("power", None),
        ("accuracy", 0),
        ("accuracy", None),
        ("priority", -7),
        ("priority", 5),
    ],
)
def test_the_edges_the_census_shows_are_accepted(field: str, value: object) -> None:
    body = copy.deepcopy(FLAMETHROWER) | {field: value}
    assert getattr(parse_move(body), field) == value


def _set(path: tuple[str | int, ...], value: object) -> dict[str, Any]:
    body = copy.deepcopy(FLAMETHROWER)
    target = body
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    return body


@pytest.mark.parametrize(
    ("body", "rule"),
    [
        (_set(("power",), -1), "power"),
        (_set(("power",), 256), "power"),
        (_set(("power",), "90"), "power"),
        (_set(("power",), True), "power"),
        (_set(("accuracy",), 101), "accuracy"),
        (_set(("accuracy",), 99.5), "accuracy"),
        (_set(("type", "name"), "stellar"), "move_type"),
        (_set(("damage_class", "name"), "other"), "damage_class"),
        (_set(("id",), 0), "id"),
        (_set(("name",), ""), "name"),
        (_set(("priority",), 6), "priority"),
        (_set(("priority",), -8), "priority"),
        (_set(("priority",), None), "priority"),
        (_set(("effect_entries", 1, "short_effect"), ""), "short_effect"),
        (_set(("effect_entries", 0, "language", "name"), "en"), "effect_conflict"),
        (_set(("effect_entries",), None), "malformed"),
        (_set(("type",), None), "malformed"),
        ({k: v for k, v in FLAMETHROWER.items() if k != "accuracy"}, "malformed"),
    ],
)
def test_a_move_answer_that_breaks_a_rule_is_refused_by_name(body: Any, rule: str) -> None:
    with pytest.raises(ParseError) as refused:
        parse_move(body)
    assert refused.value.rule == rule


@pytest.mark.parametrize("path", POKEMON_FILES, ids=[path.stem for path in POKEMON_FILES])
def test_a_pokemon_lists_exactly_the_captured_moves_that_name_it(path: Path) -> None:
    pokemon = load(path)
    ids = parse_move_ids(pokemon)
    assert ids == sorted(ids)
    for move_path in MOVE_FILES:
        move = load(move_path)
        named = any(entry["name"] == pokemon["name"] for entry in move["learned_by_pokemon"])
        assert (move["id"] in ids) == named, move["name"]


def test_a_pokemon_with_no_moves_listed_has_an_empty_list() -> None:
    assert parse_move_ids({"moves": []}) == []


def _entry(url: object) -> dict[str, Any]:
    return {"move": {"name": "x", "url": url}, "version_group_details": []}


LISTED = "https://pokeapi.co/api/v2/move/5/"


@pytest.mark.parametrize(
    ("body", "rule"),
    [
        ({}, "moves_malformed"),
        ({"moves": None}, "moves_malformed"),
        ({"moves": [{"version_group_details": []}]}, "moves_malformed"),
        ({"moves": [_entry("https://pokeapi.co/api/v2/pokemon/5/")]}, "move_url"),
        ({"moves": [_entry("https://pokeapi.co/api/v2/move/0/")]}, "move_url"),
        ({"moves": [_entry(5)]}, "move_url"),
        ({"moves": [_entry(LISTED), _entry(LISTED)]}, "move_repeated"),
    ],
)
def test_a_move_list_in_a_pokemon_answer_that_breaks_a_rule_is_refused(
    body: Any, rule: str
) -> None:
    with pytest.raises(ParseError) as refused:
        parse_move_ids(body)
    assert refused.value.rule == rule


@pytest.mark.parametrize(
    ("body", "rule"),
    [
        ({"count": 2, "results": [{"name": "x", "url": LISTED}]}, "count_mismatch"),
        ({"count": 2, "results": [{"name": "x", "url": LISTED}] * 2}, "move_repeated"),
        ({"count": 1, "results": [{"name": "x", "url": "/move/5/"}]}, "move_url"),
        ({"count": 1}, "malformed"),
    ],
)
def test_a_move_list_that_is_not_whole_is_refused(body: Any, rule: str) -> None:
    with pytest.raises(ParseError) as refused:
        parse_move_list(body)
    assert refused.value.rule == rule
