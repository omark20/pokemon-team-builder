"""One Pokémon as the counter team sees it, and its stats at level 50.

Every duel is fought at level 50 with no individual values, no training and a
neutral nature. The stat formulas are the games' own, as written in the Smogon
damage calculator's public source (`calc/src/stats.ts`): at level 50 they come
down to HP = base + 60 and every other stat = base + 5. Pure: no web or database
code.
"""

from dataclasses import dataclass

from app.domain.moves import Move

# Positions in `Pokemon.stats`, the order of PokéAPI's stat list.
HP, ATTACK, DEFENSE, SPECIAL_ATTACK, SPECIAL_DEFENSE, SPEED = range(6)


@dataclass(frozen=True)
class Pokemon:
    """What the counter team needs to know about one Pokémon, opponent or candidate."""

    id: int
    name: str
    types: tuple[str, ...]
    stats: tuple[int, ...]  # the six base stats
    is_default: bool = True
    removed: bool = False
    is_legendary: bool | None = None  # PokéAPI's species flags; None until the scan reads them
    is_mythical: bool | None = None
    moves: tuple[Move, ...] = ()  # the four it carries (default_moves.py), possibly fewer
    moves_listed: bool = True  # False when PokéAPI lists no moves for it at all
    baseline: int = 0  # its duel margins against the whole field, added up (counter_score.py)


def hp_at_level_50(pokemon: Pokemon) -> int:
    return pokemon.stats[HP] + 60


def stat_at_level_50(pokemon: Pokemon, position: int) -> int:
    """Attack, Defense, Special Attack or Special Defense at level 50."""
    return pokemon.stats[position] + 5


def attacking_stat(pokemon: Pokemon, move: Move) -> int:
    """The stat a move hits with: Attack for a physical move, Special Attack for a special one."""
    return stat_at_level_50(pokemon, ATTACK if move.damage_class == "physical" else SPECIAL_ATTACK)


def defending_stat(pokemon: Pokemon, move: Move) -> int:
    """The stat a move is taken on: Defense against physical, Special Defense against special."""
    position = DEFENSE if move.damage_class == "physical" else SPECIAL_DEFENSE
    return stat_at_level_50(pokemon, position)
