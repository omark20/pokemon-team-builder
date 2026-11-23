"""Counter team: for each Pokémon of the visitor's team, one counter that beats it in a duel.

Counter i answers opponent i. Each counter must hit its own opponent for 2× or more
with one of its four moves; no Pokémon is used twice; and no opposing type may hit
more than half the counters for 2× or more. Within those rules the team is the one
with the highest total score (counter_score.py), found exactly (counter_search.py).
This module decides who may be picked and scores every candidate in every slot;
counter_result.py describes the chosen team. Nothing here touches the database or
the web.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from app.domain.counter_result import CounterResult, describe_team
from app.domain.counter_score import advantage, packed_score
from app.domain.counter_search import Candidate, choose_team
from app.domain.duel import duel
from app.domain.move_rules import HITS_HARD, quarters
from app.domain.pokemon import Pokemon
from app.domain.types import Chart

Opponents = Sequence[Pokemon]


def candidate_pool(pokemon: Iterable[Pokemon], leave_out_legendary: bool = False) -> list[Pokemon]:
    """Who may be picked as a counter: default forms that PokéAPI still lists.

    Special versions (Mega and the like) are left out because many exist only in
    the middle of a battle. With `leave_out_legendary`, a Pokémon is allowed only if
    both flags are known to be false: an unread flag is left out, so the filter never
    lets a legendary through.
    """
    return [
        entry
        for entry in pokemon
        if entry.is_default
        and not entry.removed
        and not (leave_out_legendary and (entry.is_legendary, entry.is_mythical) != (False, False))
    ]


def weak_to(candidate: Pokemon, opponents: Opponents, chart: Chart) -> frozenset[str]:
    """The candidate's weakness pattern: the opposing types that hit it for 2× or more."""
    opposing = {own for opponent in opponents for own in opponent.types}
    return frozenset(t for t in opposing if quarters(chart, t, candidate.types) >= HITS_HARD)


@dataclass(frozen=True)
class Slot:
    """One opponent's scored candidates, and whether the 2× rule had to be waived."""

    candidates: list[Candidate]
    hits_hard_waived: bool


@dataclass(frozen=True)
class Standing:
    """What a candidate brings to every slot alike: levels 2 and 3, and its weaknesses."""

    advantage: int
    stat_total: int
    weak_to: frozenset[str]


def score_slot(
    opponent: Pokemon,
    pool: list[Pokemon],
    standings: dict[int, Standing],
    chart: Chart,
    field_size: int,
) -> Slot:
    """Every candidate that hits this opponent for 2×, scored; the whole pool if none can."""
    duels = {c.id: duel(c, opponent, chart, counter_hits_hard=True) for c in pool}
    able = [c for c in pool if duels[c.id].counter_hit is not None]
    if not able:
        duels = {c.id: duel(c, opponent, chart, counter_hits_hard=False) for c in pool}
    scored = []
    for candidate in able or pool:
        standing = standings[candidate.id]
        score = packed_score(
            duels[candidate.id].margin, standing.advantage, standing.stat_total, field_size
        )
        scored.append(Candidate(candidate.id, score, duels[candidate.id].margin, standing.weak_to))
    return Slot(scored, hits_hard_waived=not able)


def build_counter_team(
    opponents: Opponents, pool: Iterable[Pokemon], chart: Chart, field_size: int
) -> CounterResult:
    """The best counter team from the pool. `field_size` is the N the baselines were taken over."""
    candidates = sorted(pool, key=lambda entry: entry.id)
    standings = {
        c.id: Standing(
            advantage(c, opponents, chart, field_size), sum(c.stats), weak_to(c, opponents, chart)
        )
        for c in candidates
    }
    slots = [score_slot(o, candidates, standings, chart, field_size) for o in opponents]
    choice = choose_team([slot.candidates for slot in slots], [o.id for o in opponents])
    by_id = {entry.id: entry for entry in candidates}
    team = [by_id[candidate.id] for candidate in choice.team]
    waived = [slot.hits_hard_waived for slot in slots]
    return describe_team(team, opponents, waived, choice.weakness_rule, chart, len(candidates))
