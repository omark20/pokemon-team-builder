"""A one-on-one fight between two Pokémon at level 50, in whole numbers.

Each side uses the best of the four moves it carries every turn. Damage follows the
games' formula as written in the Smogon damage calculator's public source
(`getBaseDamage` in `calc/src/mechanics/util.ts`), with the full damage roll and no
critical hits, abilities, items or weather. A move that sometimes misses counts for
its average damage. Every division rounds down. Pure: no web or database code.
"""

from dataclasses import dataclass

from app.domain.move_rules import HITS_HARD, accuracy, quarters
from app.domain.moves import Move
from app.domain.pokemon import SPEED, Pokemon, attacking_stat, defending_stat, hp_at_level_50
from app.domain.types import Chart

LEVEL_FACTOR = 22  # 2 × level ÷ 5 + 2 at level 50
MOST_TURNS = 10  # turns are counted up to 10, which a reader sees as "10 or more"


@dataclass(frozen=True)
class Hit:
    """One move used by one Pokémon on another, and what it does."""

    move: Move
    damage: int
    quarters: int  # the type multiplier times four: 16 is 4×, 4 is 1×


@dataclass(frozen=True)
class Duel:
    """Both sides of a fight. A side with no move that damages the other has no hit."""

    counter_hit: Hit | None
    opponent_hit: Hit | None
    counter_turns: int  # turns the counter needs to knock the opponent out
    opponent_turns: int  # turns the opponent needs to knock the counter out
    speed_edge: int  # +1 if the counter strikes first each turn, -1 if the opponent does, else 0

    @property
    def margin(self) -> int:
        """How decisively the counter wins, -19 to 19; above 0 it knocks the opponent out first.

        Each turn fewer counts 2 and striking first counts 1, so equal turns are
        settled by speed and one turn fewer still wins when slower.
        """
        return 2 * (self.opponent_turns - self.counter_turns) + self.speed_edge


def damage(attacker: Pokemon, move: Move, defender: Pokemon, chart: Chart) -> int:
    """The damage of one hit: the base formula, the same-type bonus, then the type multiplier.

    Tyranitar's Stone Edge on Charizard: 22 × 100 × 139 ÷ 83 ÷ 50 + 2 = 75, same type
    × 3 ÷ 2 = 112, rock on fire and flying × 16 ÷ 4 = 448.
    """
    power = move.power or 0
    base = LEVEL_FACTOR * power * attacking_stat(attacker, move)
    base = base // defending_stat(defender, move) // 50 + 2
    if move.type in attacker.types:
        base = base * 3 // 2
    return base * quarters(chart, move.type, defender.types) // 4


def best_hit(attacker: Pokemon, defender: Pokemon, chart: Chart, least: int = 0) -> Hit | None:
    """The attacker's best move on the defender, or None if none of its four does damage.

    Best means the most damage times accuracy; among equals, the lowest move ID. Only
    moves whose type multiplier is at least `least` quarters are considered.
    """
    hits = [
        Hit(move, damage(attacker, move, defender, chart), multiplier)
        for move in attacker.moves
        if (multiplier := quarters(chart, move.type, defender.types)) >= least
    ]
    damaging = [hit for hit in hits if hit.damage > 0]
    if not damaging:
        return None
    return min(damaging, key=lambda hit: (-hit.damage * accuracy(hit.move), hit.move.id))


def turns_to_knock_out(hit: Hit | None, defender: Pokemon) -> int:
    """Turns of average damage to empty the defender's HP, rounded up, at most 10."""
    if hit is None:
        return MOST_TURNS
    average = hit.damage * accuracy(hit.move)  # in hundredths of a hit point
    needed = -(-hp_at_level_50(defender) * 100 // average)  # rounds up
    return min(needed, MOST_TURNS)


def speed_edge(counter: Pokemon, opponent: Pokemon) -> int:
    """+1 if the counter's base Speed is higher, -1 if lower, 0 if equal."""
    ours, theirs = counter.stats[SPEED], opponent.stats[SPEED]
    return (ours > theirs) - (ours < theirs)


def duel(counter: Pokemon, opponent: Pokemon, chart: Chart, counter_hits_hard: bool) -> Duel:
    """The fight between a counter and an opponent.

    With `counter_hits_hard` the counter may only use a move that hits for 2× or more;
    the opponent always uses its best move, of any multiplier.
    """
    counter_hit = best_hit(counter, opponent, chart, HITS_HARD if counter_hits_hard else 0)
    opponent_hit = best_hit(opponent, counter, chart)
    return Duel(
        counter_hit,
        opponent_hit,
        turns_to_knock_out(counter_hit, opponent),
        turns_to_knock_out(opponent_hit, counter),
        speed_edge(counter, opponent),
    )
