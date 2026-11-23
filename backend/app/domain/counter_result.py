"""The counter team as the page shows it: each pick's duel, the grid, the moves assumed.

Built from the same duels the score was worked out from. Pure: no web or database code.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from app.domain.counter_text import outcome, pick_line, pokemon_name, reason
from app.domain.duel import Duel, Hit, duel
from app.domain.move_rules import HITS_HARD, quarters
from app.domain.pokemon import Pokemon
from app.domain.types import Chart


@dataclass(frozen=True)
class Side:
    """One side of a duel: the Pokémon, the move it uses on the other, and the turns it needs.

    The damage, accuracy and HP behind the turns are stated in the pick's `reason`.
    """

    id: int
    name: str
    move: str | None  # None if none of its four damages the other side
    turns: int  # 1 to 10; 10 is shown as "10 or more"


@dataclass(frozen=True)
class Pick:
    """One counter, the opponent it answers, and how their duel ends."""

    counter: Side
    opponent: Side
    outcome: str  # "wins", "draws with" or "loses to"
    line: str
    reason: str


@dataclass(frozen=True)
class Cell:
    """How one counter's duel with one opponent ends, as the details table shows it.

    Against the opponent it was picked for, a counter's cell is its pick's duel (moves of
    2× or more only), so the cell agrees with the pick's line. Every other cell lets it use
    any move. The cells are for reading, not the terms of the score's sum.
    """

    outcome: str  # "wins", "draws with" or "loses to", for the counter
    counter_turns: int
    opponent_turns: int


@dataclass(frozen=True)
class OpponentMoves:
    """The moves one of the visitor's Pokémon is assumed to carry, in the order chosen."""

    name: str
    moves: list[str]
    moves_listed: bool  # False when PokéAPI lists no moves for it at all


@dataclass(frozen=True)
class CounterResult:
    """The counter team in the opposing team's order; no picks means no team exists."""

    picks: list[Pick]
    grid: list[list[Cell]]  # grid[i][j]: counter i against opponent j
    opponent_moves: list[OpponentMoves]
    weakness_counts: dict[str, int]  # opposing type: counters it hits for 2× or more
    weakness_rule: str  # "kept", "limit_raised" or "guard_reached" (counter_search.py)
    pool_size: int
    # The first opponent, in team order, that no candidate left can hit for 2× or
    # more; when set, nothing else is filled in.
    no_candidate_for: str | None = None


def no_team_for(opponent: Pokemon, pool_size: int) -> CounterResult:
    """The answer when nothing left in the pool can counter this opponent."""
    return CounterResult([], [], [], {}, "kept", pool_size, no_candidate_for=opponent.name)


def side(attacker: Pokemon, hit: Hit | None, turns: int) -> Side:
    return Side(attacker.id, attacker.name, hit.move.name if hit else None, turns)


def describe_pick(counter: Pokemon, opponent: Pokemon, fight: Duel) -> Pick:
    """A pick from the duel its score used."""
    return Pick(
        side(counter, fight.counter_hit, fight.counter_turns),
        side(opponent, fight.opponent_hit, fight.opponent_turns),
        outcome(fight),
        pick_line(fight, counter, opponent),
        reason(fight, counter, opponent),
    )


def cell(fight: Duel) -> Cell:
    return Cell(outcome(fight), fight.counter_turns, fight.opponent_turns)


def grid_row(
    counter: Pokemon, own: int, own_fight: Duel, opponents: Sequence[Pokemon], chart: Chart
) -> list[Cell]:
    """One counter against every opponent; at position `own`, its pick's duel."""
    return [
        cell(own_fight if j == own else duel(counter, opponent, chart, counter_hits_hard=False))
        for j, opponent in enumerate(opponents)
    ]


def weakness_counts(
    team: Sequence[Pokemon], opponents: Sequence[Pokemon], chart: Chart
) -> dict[str, int]:
    """For each opposing type, in name order: how many counters it hits for 2× or more."""
    opposing = sorted({own for opponent in opponents for own in opponent.types})
    return {t: sum(quarters(chart, t, c.types) >= HITS_HARD for c in team) for t in opposing}


def describe_team(
    team: Sequence[Pokemon],
    opponents: Sequence[Pokemon],
    waived: Sequence[bool],
    weakness_rule: str,
    chart: Chart,
    pool_size: int,
) -> CounterResult:
    """The result for a chosen team, or for no team (an empty `team`).

    Each pick's duel is the one its score used: 2× moves only, unless that rule was
    waived for its slot because no candidate could keep it.
    """
    pairs = list(zip(team, opponents, waived, strict=False))
    fights = [duel(c, o, chart, counter_hits_hard=not w) for c, o, w in pairs]
    return CounterResult(
        picks=[describe_pick(c, o, f) for (c, o, _), f in zip(pairs, fights, strict=True)],
        grid=[grid_row(c, i, fights[i], opponents, chart) for i, c in enumerate(team)],
        opponent_moves=[
            OpponentMoves(pokemon_name(o), [m.name for m in o.moves], o.moves_listed)
            for o in opponents
        ],
        weakness_counts=weakness_counts(team, opponents, chart),
        weakness_rule=weakness_rule,
        pool_size=pool_size,
    )
