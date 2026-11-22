"""The type chart: how much an attack of one type multiplies damage against another type.

Every Pokémon has one or two of 18 elemental types. Each attacking type does double,
half, no, or normal damage to each defending type. The chart is built from PokéAPI's
/type responses and used only if it passes a consistency check, because a half-loaded
chart would silently give wrong counter teams. Pure: no web or database code.
"""

import math
from collections.abc import Iterable, Iterator, Mapping, Sequence
from typing import Any

# The 18 standard types, in PokéAPI's id order 1 to 18 (samples/type_list.json).
# /type also lists stellar, unknown and shadow, which have no damage data and no
# Pokémon (samples/type_19_stellar.json and the two other captures); they are ignored.
STANDARD_TYPES = (
    "normal", "fighting", "flying", "poison", "ground", "rock", "bug", "ghost", "steel",
    "fire", "water", "grass", "electric", "psychic", "ice", "dragon", "dark", "fairy",
)  # fmt: skip

# (attacker, defender) -> multiplier, one of 0, 0.5, 1 and 2. Always all 324 cells.
Chart = dict[tuple[str, str], float]

# The three lists in a type's damage_relations naming what it does to others, and the
# three naming what others do to it. A type not listed is hit for normal damage (1).
DAMAGE_TO = {"double_damage_to": 2.0, "half_damage_to": 0.5, "no_damage_to": 0.0}
DAMAGE_FROM = {"double_damage_from": 2.0, "half_damage_from": 0.5, "no_damage_from": 0.0}


class ChartError(ValueError):
    """The type data failed a check. `rule` names the check, `detail` the type or cell."""

    def __init__(self, rule: str, detail: str) -> None:
        super().__init__(f"{rule}: {detail}")
        self.rule = rule
        self.detail = detail


def build_chart(payloads: Iterable[Mapping[str, Any]]) -> Chart:
    """Build the chart from /type/{id} responses, raising ChartError if it is inconsistent.

    Checks: all 18 types are present; their lists name only standard types; no type
    appears in two of one type's lists; and the chart read from the "damage to" lists
    equals the one read from the "damage from" lists, cell for cell.
    """
    relations = {p["name"]: p["damage_relations"] for p in payloads if p["name"] in STANDARD_TYPES}
    missing = [name for name in STANDARD_TYPES if name not in relations]
    if missing:
        raise ChartError("missing_type", missing[0])
    chart = _read_lists(relations, DAMAGE_TO, own_type_attacks=True)
    from_chart = _read_lists(relations, DAMAGE_FROM, own_type_attacks=False)
    for cell, multiplier in chart.items():
        if from_chart[cell] != multiplier:
            raise ChartError("from_disagrees", f"{cell[0]}>{cell[1]}")
    return chart


def effectiveness(chart: Chart, attack_type: str, defender_types: Sequence[str]) -> float:
    """The damage multiplier of one attack type against a defender with these types.

    It is the product over the defender's types, so it is one of 0, ¼, ½, 1, 2 or 4:
    rock against a fire and flying defender is 2 × 2 = 4.
    """
    return math.prod(chart[attack_type, defender] for defender in defender_types)


def _read_lists(
    relations: Mapping[str, Mapping[str, Any]], lists: Mapping[str, float], own_type_attacks: bool
) -> Chart:
    """The full 18 × 18 chart as one set of three lists describes it."""
    chart = {(a, d): 1.0 for a in STANDARD_TYPES for d in STANDARD_TYPES}
    listed: set[tuple[str, str]] = set()
    for own, other, multiplier in _entries(relations, lists):
        if other not in STANDARD_TYPES:
            raise ChartError("non_standard_type", other)
        cell = (own, other) if own_type_attacks else (other, own)
        if cell in listed:
            raise ChartError("listed_twice", f"{cell[0]}>{cell[1]}")
        listed.add(cell)
        chart[cell] = multiplier
    return chart


def _entries(
    relations: Mapping[str, Mapping[str, Any]], lists: Mapping[str, float]
) -> Iterator[tuple[str, str, float]]:
    """Every (type, type it names, multiplier) found in the given lists."""
    for own, relation in relations.items():
        for list_name, multiplier in lists.items():
            for entry in relation[list_name]:
                yield own, entry["name"], multiplier
