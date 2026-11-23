"""The score of a counter in one slot, as one whole number.

Three levels, compared in order:

1. The duel margin against its own opponent, using only moves that hit it for 2× or
   more (-19 to 19).
2. Its advantage against this team: N × (its margins against every opponent) - n ×
   (its baseline), where n is the team size, N the field size and the baseline its
   margins against every Pokémon of the field, added up. Both sums let it use its best
   move of any multiplier. A positive advantage means it does better against this team
   than against Pokémon in general.
3. Its base-stat total.

The levels are packed into one number by weights, each larger than six counters'
worth of everything below it, so a team's total compares the summed margins first,
then the summed advantages, then the summed base stats. Pure: no web or database code.
"""

from collections.abc import Sequence

from app.domain.duel import duel
from app.domain.pokemon import Pokemon
from app.domain.types import Chart

LARGEST_MARGIN = 19  # 2 × (10 - 1) + 1
LARGEST_TEAM = 6
LARGEST_STAT_TOTAL = 6 * 255  # the parser refuses a stat over 255
STAT_WEIGHT = 1
ADVANTAGE_WEIGHT = 10_000  # more than six base-stat totals, 9,180


def margin_sum(candidate: Pokemon, opponents: Sequence[Pokemon], chart: Chart) -> int:
    """The candidate's margins against each opponent, any move allowed, added up.

    Against the visitor's team it is part of level 2; against every Pokémon of the
    field it is the candidate's baseline, worked out once per scan.
    """
    return sum(
        duel(candidate, opponent, chart, counter_hits_hard=False).margin for opponent in opponents
    )


def largest_advantage(field_size: int) -> int:
    """The bound on level 2 for one counter: each of its two terms is at most 19 × 6 × N."""
    return 2 * LARGEST_MARGIN * LARGEST_TEAM * field_size


def margin_weight(field_size: int) -> int:
    """Larger than six counters' worth of the two levels below, from lowest to highest."""
    span_below = (
        2 * largest_advantage(field_size) * ADVANTAGE_WEIGHT + LARGEST_STAT_TOTAL * STAT_WEIGHT
    )
    return LARGEST_TEAM * span_below + 1


def advantage(
    candidate: Pokemon, opponents: Sequence[Pokemon], chart: Chart, field_size: int
) -> int:
    """Level 2: how much better the candidate does against this team than against the field."""
    return (
        field_size * margin_sum(candidate, opponents, chart) - len(opponents) * candidate.baseline
    )


def packed_score(margin: int, candidate_advantage: int, stat_total: int, field_size: int) -> int:
    """The three levels as one number, highest level weighing most."""
    return (
        margin * margin_weight(field_size)
        + candidate_advantage * ADVANTAGE_WEIGHT
        + stat_total * STAT_WEIGHT
    )
