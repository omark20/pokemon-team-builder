"""Which stored moves count in a duel, and the whole-number facts every duel reads from a move.

A move counts if it deals ordinary damage on the turn it is used: it is physical or
special, has a power above 0, has one of the 18 standard types, and its English short
effect contains none of `LEFT_OUT_PHRASES`. Against samples/census_all_moves.tsv the
phrases remove exactly 39 moves and leave 533 that count. A move with no effect text
counts as ordinary, which lets through recent moves whose drawback PokéAPI does not
describe; that is a stated limit, not corrected by hand. Pure: no web or database code.
"""

from collections.abc import Sequence

from app.domain.moves import Move
from app.domain.types import STANDARD_TYPES, Chart, effectiveness

HITS_HARD = 8  # a type multiplier of 2× or more, in quarters (see `quarters`)

# Each phrase marks a move that does not simply hit on the turn it is chosen.
LEFT_OUT_PHRASES = (
    "charge",  # charges first, or must recharge after ("recharge" contains it)
    "next turn",  # hits on the next turn: fly, dig and the like
    "User faints",  # self-destruct, explosion
    "Only works",  # needs a condition: dream-eater, snore, sucker-punch
    "an only be used",  # "Can only be used" on the first turn or under a condition
    "two turns later",  # future-sight, doom-desire
    "canceled",  # focus-punch
    "Only inflicts",  # shell-trap
    "shares a type",  # synchronoise
)


def counts(move: Move) -> bool:
    """Whether a move is one a Pokémon may use in a duel."""
    effect = move.short_effect or ""
    return (
        move.damage_class in ("physical", "special")
        and (move.power or 0) > 0
        and move.type in STANDARD_TYPES
        and not any(phrase in effect for phrase in LEFT_OUT_PHRASES)
    )


def accuracy(move: Move) -> int:
    """A move's chance to hit, in percent.

    PokéAPI gives no accuracy (swift) or 0 (tachyon-cutter) for moves that cannot
    miss, so both count as 100.
    """
    return move.accuracy or 100


def quarters(chart: Chart, move_type: str, defender_types: Sequence[str]) -> int:
    """The type multiplier on a defender, times four, so it is a whole number.

    One of 0, 1, 2, 4, 8 or 16: ¼× is 1, 1× is 4, 2× is 8 and 4× is 16. The chart's
    cells are 0, ½, 1 and 2, so the product times four is exact.
    """
    return round(4 * effectiveness(chart, move_type, defender_types))
