"""The four moves a Pokémon is assumed to carry when nobody has chosen them.

One rule for every Pokémon, worked out from stored data after each full scan:

1. For each type, keep the Pokémon's strongest counted move of that type, where
   strength = power × accuracy × (3 if the move shares its type, else 2) × the
   attacking stat at level 50; equal strengths go to the lower move ID.
2. Choose four of those one at a time, each time the one that adds most to the
   field total: over every Pokémon of the field, the highest strength × type
   multiplier among the moves chosen so far. Equal gains go to the lower move ID;
   the choice stops early when no move adds anything.

So the four together hit the most Pokémon the hardest. Choosing one at a time is not
guaranteed to find the best set of four; it is an assumption about a Pokémon, not the
thing the counter team maximises. Pokémon with the same types count together. Pure:
no web or database code.
"""

from collections import Counter
from collections.abc import Iterable

from app.domain.move_rules import accuracy, counts, quarters
from app.domain.moves import Move
from app.domain.pokemon import Pokemon, attacking_stat
from app.domain.types import Chart

MOVES_CARRIED = 4

# How many Pokémon of the field have each combination of types.
Field = Counter[tuple[str, ...]]


def field_types(pokemon: Iterable[Pokemon]) -> Field:
    """The field: the type combinations of every default Pokémon PokéAPI still lists."""
    return Counter(entry.types for entry in pokemon if entry.is_default and not entry.removed)


def strength(pokemon: Pokemon, move: Move) -> int:
    """How hard a move hits for this Pokémon, before the defender is known."""
    same_type = 3 if move.type in pokemon.types else 2
    return (move.power or 0) * accuracy(move) * same_type * attacking_stat(pokemon, move)


def strongest_per_type(pokemon: Pokemon, learnable: Iterable[Move]) -> list[Move]:
    """Step 1: the strongest counted move of each type, at most 18."""
    best: dict[str, Move] = {}
    for move in sorted(filter(counts, learnable), key=lambda move: move.id):
        held = best.get(move.type)
        if held is None or strength(pokemon, move) > strength(pokemon, held):
            best[move.type] = move
    return sorted(best.values(), key=lambda move: move.id)


def gain(
    reach: dict[tuple[str, ...], int], reached: dict[tuple[str, ...], int], field: Field
) -> int:
    """How much one move would add to the field total, given the best values reached so far."""
    return sum(count * max(0, reach[types] - reached[types]) for types, count in field.items())


def default_four(
    pokemon: Pokemon, learnable: Iterable[Move], field: Field, chart: Chart
) -> tuple[int, ...]:
    """Step 2: the IDs of the moves chosen, in the order chosen; fewer than four if
    fewer add anything, none if the Pokémon has no counted move."""
    reach = {  # per move, per type combination of the field: strength × type multiplier
        move.id: {
            types: strength(pokemon, move) * quarters(chart, move.type, types) for types in field
        }
        for move in strongest_per_type(pokemon, learnable)
    }
    reached = dict.fromkeys(field, 0)  # per type combination: the best value chosen so far
    chosen: list[int] = []
    while len(chosen) < MOVES_CARRIED:
        gains = {
            move_id: gain(values, reached, field)
            for move_id, values in reach.items()
            if move_id not in chosen
        }
        best = min(gains, key=lambda move_id: (-gains[move_id], move_id), default=None)
        if best is None or gains[best] == 0:
            break
        chosen.append(best)
        reached = {types: max(reached[types], reach[best][types]) for types in field}
    return tuple(chosen)
