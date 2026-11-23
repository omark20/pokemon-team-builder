"""Moves as PokéAPI gives them: the move list, one move's answer, and a Pokémon's moves.

All three are stored as fetched; which moves count in a duel is decided in
domain/move_rules.py. Each parser refuses any answer that breaks a rule, naming
the rule, so a half-read move or move list is never stored. Every rule rests on the
captures in samples/ (samples/README.md, facts 22 to 26, and census_all_moves.tsv, one
row per listed move). Pure: no web or database code.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from app.domain.diff import FieldChange, ParseError, check, is_int
from app.domain.types import STANDARD_TYPES

# Every move URL in the list and in the 14 captured Pokémon answers has this form.
MOVE_URL = re.compile(r"https://pokeapi\.co/api/v2/move/([1-9][0-9]*)/")
# The 18 standard types and `shadow`, the type of the 18 moves numbered from 10001 (fact 22).
MOVE_TYPES = frozenset((*STANDARD_TYPES, "shadow"))
DAMAGE_CLASSES = frozenset({"physical", "special", "status"})  # fact 23
# Power is null for 338 moves and 0 for 17 (16 status moves and hard-press); the largest
# is explosion's 250 (census_all_moves.tsv). Accuracy is null for 288 and runs 0 to 100.
MAX_POWER = 255  # a bound above every power seen, not a power seen
MAX_ACCURACY = 100
PRIORITIES = range(-7, 6)  # every move has one, from -7 to 5 (census_all_moves.tsv)
# The fields of a move a duel reads, so the ones whose change is recorded and alerted on.
DIFFED = ("power", "accuracy", "type", "damage_class")


@dataclass(frozen=True)
class Move:
    """One move as stored. Each field is a column of the `moves` table, same name."""

    id: int
    name: str
    type: str
    damage_class: str
    power: int | None  # null where PokéAPI gives none (fact 24)
    accuracy: int | None  # null for moves that do not check accuracy (fact 24)
    priority: int
    short_effect: str | None  # the English one; dire-claw, among the newest, has none


def parse_move_list(payload: Mapping[str, Any]) -> dict[int, str]:
    """The /move list as move ID to URL, or ParseError if it is not whole and well formed."""
    try:
        results, count = payload["results"], payload["count"]
        urls = [entry["url"] for entry in results]
    except (KeyError, TypeError) as exc:
        raise ParseError("malformed") from exc
    listed = dict(zip(_ids_from_urls(urls), urls, strict=True))
    check(len(listed) == len(urls), "move_repeated")
    check(len(listed) == count, "count_mismatch")
    return listed


def parse_move(payload: Mapping[str, Any]) -> Move:
    """Read a /move/{id} answer into a move, or raise ParseError naming the rule.

    Only the stored fields are read, so `meta`, null for 111 moves (fact 23), is never
    looked at.
    """
    try:
        return _read_move(payload)
    except (KeyError, TypeError) as exc:
        raise ParseError("malformed") from exc


def parse_move_ids(payload: Mapping[str, Any]) -> list[int]:
    """The IDs of the moves a /pokemon/{id} answer lists, smallest first; may be empty.

    The 34 Gigantamax forms list no moves at all (fact 26). In the 14 captured answers
    no move is listed twice.
    """
    try:
        urls = [entry["move"]["url"] for entry in payload["moves"]]
    except (KeyError, TypeError) as exc:
        raise ParseError("moves_malformed") from exc
    ids = _ids_from_urls(urls)
    check(len(set(ids)) == len(ids), "move_repeated")
    return sorted(ids)


def diff_move(stored: Move, fetched: Move) -> list[FieldChange]:
    """The duel's fields that differ between the stored move and the fetched one."""
    return [
        FieldChange(name, getattr(stored, name), getattr(fetched, name))
        for name in DIFFED
        if getattr(stored, name) != getattr(fetched, name)
    ]


def _read_move(payload: Mapping[str, Any]) -> Move:
    move_id, name = payload["id"], payload["name"]
    power, accuracy, priority = payload["power"], payload["accuracy"], payload["priority"]
    move_type, damage_class = payload["type"]["name"], payload["damage_class"]["name"]
    check(is_int(move_id) and move_id > 0, "id")
    check(isinstance(name, str) and name != "", "name")
    check(move_type in MOVE_TYPES, "move_type")
    check(damage_class in DAMAGE_CLASSES, "damage_class")
    check(power is None or (is_int(power) and 0 <= power <= MAX_POWER), "power")
    check(accuracy is None or (is_int(accuracy) and 0 <= accuracy <= MAX_ACCURACY), "accuracy")
    check(is_int(priority) and priority in PRIORITIES, "priority")
    short_effect = _english_short_effect(payload["effect_entries"])
    return Move(move_id, name, move_type, damage_class, power, accuracy, priority, short_effect)


def _english_short_effect(entries: list[Mapping[str, Any]]) -> str | None:
    """The English short effect text, or None if there is none.

    The captured answers have one entry in French and one in English, or none at all;
    scale-shot (799) lists the same English entry twice, so English entries that agree
    are one text, and English entries that disagree are refused.
    """
    english = [entry["short_effect"] for entry in entries if entry["language"]["name"] == "en"]
    check(all(isinstance(text, str) and text != "" for text in english), "short_effect")
    check(len(set(english)) <= 1, "effect_conflict")
    return english[0] if english else None


def _ids_from_urls(urls: list[Any]) -> list[int]:
    """The move ID in each URL, or ParseError if any is not a move URL."""
    matches = [MOVE_URL.fullmatch(url) if isinstance(url, str) else None for url in urls]
    check(all(matches), "move_url")
    return [int(match[1]) for match in matches if match]
