"""The moves a visitor chooses for a team member: which ones a Pokémon may use.

A chosen move must be named in the Pokémon's stored move list and must count in a
duel (domain/move_rules.py). The rule is checked when a team is saved, so a visitor
cannot store a move it may not use, and again when a counter team is built, since a
later scan may have dropped a move from the list or changed it; a move that no longer
passes is then left out of the duel. The stored choice itself is never rewritten.
"""

from collections.abc import Sequence
from dataclasses import replace

from app.domain.move_rules import counts
from app.domain.moves import Move
from app.domain.pokemon import Pokemon


def counted(move_id: int, moves: dict[int, Move]) -> bool:
    """Whether the stored move counts in a duel; a move not stored does not."""
    move = moves.get(move_id)
    return move is not None and counts(move)


def with_choice(
    pokemon: Pokemon, chosen: Sequence[int], learnable_ids: set[int], moves: dict[int, Move]
) -> Pokemon:
    """The Pokémon carrying the chosen moves it may still use, in the order chosen.

    If none of them may be used, or none were chosen, it keeps the four it carries
    already: its usual four.
    """
    usable = [i for i in chosen if i in learnable_ids and counted(i, moves)]
    return replace(pokemon, moves=tuple(moves[i] for i in usable)) if usable else pokemon
