"""Counter team: the best team of equal size against a given opposing team.

Only types and base stats are used. Each Pokémon is assumed to attack with moves
of its own types. Counter i is the designated answer to opponent i. A team is
judged on the rows of `SCORE_LEVELS`, most important first, under four rules:

R1  as many counters as opponents;
R2  each counter hits its own opponent for 2x or more (`can_face`);
R3  no Pokémon twice;
R4  no opposing type hits more than half the counters for 2x or more. If no team
    can keep R4, the limit is raised one at a time until one can.

This module decides who may be picked, scores candidates, cuts each slot down to
the candidates that can matter, and describes the result. The search, run level
by level under its step limit, is in `counter_search.py`. Nothing here touches
the database or the web.
"""

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, replace

from app.domain.counter_search import STEP_LIMIT, PatternGroup, Scored, best_first, search_levels
from app.domain.types import Chart, effectiveness

# A damage multiplier as points, one per doubling, and as it is written for a reader.
POINTS: dict[float, int] = {4: 2, 2: 1, 1: 0, 0.5: -1, 0.25: -2, 0: -3}
WRITTEN: dict[float, str] = {4: "4×", 2: "2×", 1: "1×", 0.5: "½×", 0.25: "¼×", 0: "0×"}


@dataclass(frozen=True)
class Pokemon:
    """What the counter team needs to know about one Pokémon, opponent or candidate."""

    id: int
    name: str
    types: tuple[str, ...]
    stats: tuple[int, ...]
    is_default: bool = True
    removed: bool = False
    is_legendary: bool | None = None  # PokéAPI's species flags; None until the scan reads them
    is_mythical: bool | None = None


def candidate_pool(pokemon: Iterable[Pokemon], leave_out_legendary: bool = False) -> list[Pokemon]:
    """Who may be picked as a counter: default forms that PokéAPI still lists.

    Special versions (Mega and the like) are left out because many exist only in
    the middle of a battle. With `leave_out_legendary`, a Pokémon is allowed only if
    both flags are known to be false: an unread flag is left out, so the filter never
    lets a legendary through. A new rule about who may be picked goes here.
    """
    return [
        entry
        for entry in pokemon
        if entry.is_default
        and not entry.removed
        and not (leave_out_legendary and (entry.is_legendary, entry.is_mythical) != (False, False))
    ]


def best_attack(attacker: Pokemon, defender: Pokemon, chart: Chart) -> tuple[float, str]:
    """The attacker's strongest multiplier on the defender, and the type that gives it."""
    hits = [(effectiveness(chart, own, defender.types), own) for own in attacker.types]
    return max(hits, key=lambda hit: hit[0])


def can_face(candidate: Pokemon, opponent: Pokemon, chart: Chart) -> bool:
    """R2: a counter must hit its own opponent for 2x or more."""
    return best_attack(candidate, opponent, chart)[0] >= 2


def matchup(counter: Pokemon, opponent: Pokemon, chart: Chart) -> int:
    """How hard the counter hits the opponent minus how hard it is hit back: -5 to 5."""
    hit, _ = best_attack(counter, opponent, chart)
    back, _ = best_attack(opponent, counter, chart)
    return POINTS[hit] - POINTS[back]


Opponents = Sequence[Pokemon]


def assigned_points(counter: Pokemon, opponent: Pokemon, _all: Opponents, chart: Chart) -> int:
    """The counter's matchup against the opponent it is assigned to."""
    return matchup(counter, opponent, chart)


def coverage(counter: Pokemon, _own: Pokemon, opponents: Opponents, chart: Chart) -> int:
    """The counter's matchups against every slot of the opposing team, added up."""
    return sum(matchup(counter, opponent, chart) for opponent in opponents)


def base_stat_total(counter: Pokemon, _own: Pokemon, _all: Opponents, _chart: Chart) -> int:
    """The six base stats added up."""
    return sum(counter.stats)


@dataclass(frozen=True)
class ScoreLevel:
    """One level of the score: its value for a counter in a slot, and its weight.

    `smallest` and `largest` bound the value for one counter. A weight must exceed
    everything the levels below it can add up to for six counters, so that a
    higher level always decides first; a test checks this from the rows alone.
    """

    name: str
    value: Callable[[Pokemon, Pokemon, Opponents, Chart], int]
    smallest: int
    largest: int
    weight: int


Levels = Sequence[ScoreLevel]

# Most important first. A new level is one function and one row.
SCORE_LEVELS: tuple[ScoreLevel, ...] = (
    ScoreLevel("assigned_points", assigned_points, smallest=-5, largest=5, weight=10_000_000),
    ScoreLevel("coverage", coverage, smallest=-30, largest=30, weight=10_000),
    ScoreLevel("base_stats", base_stat_total, smallest=0, largest=1530, weight=1),
)


def score(
    counter: Pokemon, opponent: Pokemon, opponents: Opponents, chart: Chart, levels: Levels
) -> int:
    """A counter's worth in one slot as a single number: the levels' weighted sum."""
    return sum(row.weight * row.value(counter, opponent, opponents, chart) for row in levels)


@dataclass(frozen=True)
class Pick:
    """One counter, the opponent it answers, and the numbers behind the choice."""

    opponent: Pokemon
    counter: Pokemon
    attack: float  # the counter's best multiplier on the opponent
    attack_type: str  # the counter's type that gives it
    attack_back: float  # the opponent's best multiplier on the counter
    matchup: int
    coverage: int
    base_stats: int
    reason: str


@dataclass(frozen=True)
class CounterResult:
    """The counter team in the opposing team's order; no picks means no team exists."""

    picks: list[Pick]
    totals: dict[str, int]  # one total per score level, by level name
    grid: list[list[int]]  # grid[i][j]: matchup of counter i against opponent j
    weakness_counts: dict[str, int]  # opposing type: counters it hits for 2x or more
    relaxed: bool  # the team breaks the strict R4 limit of half its size
    stopped_early: bool = False  # a step limit was reached, so a better team may exist
    steps: int = 0
    pool_size: int = 0


def score_slot(
    opponent: Pokemon, opponents: Opponents, pool: list[Pokemon], chart: Chart, levels: Levels
) -> list[Scored]:
    """Every candidate allowed to face this opponent, with its score in this slot.

    R2 is waived for a slot whose opponent nobody in the pool can hit for 2x.
    """
    able = [candidate for candidate in pool if can_face(candidate, opponent, chart)] or pool
    return [Scored(score(c, opponent, opponents, chart, levels), c.id) for c in able]


def reduce_slot(
    scored: list[Scored], patterns: dict[int, frozenset[str]], keep: int
) -> list[PatternGroup]:
    """Group a slot's candidates by weakness pattern and keep the best `keep` of each.

    Nothing is lost by keeping as many as the team has slots: if a best team used a
    candidate that was not kept, some kept candidate of the same pattern is not on
    the team, and swapping it in breaks no rule and does not lower the score.
    """
    by_pattern: dict[frozenset[str], list[Scored]] = {}
    for candidate in scored:
        by_pattern.setdefault(patterns[candidate.id], []).append(candidate)
    groups = [
        PatternGroup(pattern, tuple(sorted(members, key=best_first)[:keep]))
        for pattern, members in by_pattern.items()
    ]
    return sorted(groups, key=lambda group: best_first(group.kept[0]))


def describe_pick(counter: Pokemon, opponent: Pokemon, opponents: Opponents, chart: Chart) -> Pick:
    """A pick with a reason a reader can check against the type chart."""
    hit, hit_type = best_attack(counter, opponent, chart)
    back, _ = best_attack(opponent, counter, chart)
    across = coverage(counter, opponent, opponents, chart)
    written_across = f"{across:+d}" if across else "0"  # zero has no sign, as in the table
    theirs, ours = opponent.name.capitalize(), counter.name.capitalize()
    reason = (
        f"{ours} ({', '.join(counter.types)}) hits {theirs} for {WRITTEN[hit]} "
        f"with {hit_type} attacks; {theirs}'s best attack back does {WRITTEN[back]}. "
        f"Across the whole opposing team its matchups add up to {written_across}."
    )
    points = matchup(counter, opponent, chart)
    return Pick(opponent, counter, hit, hit_type, back, points, across, sum(counter.stats), reason)


def opposing_types(opponents: Opponents) -> list[str]:
    """Every type that appears on the opposing team, in a fixed order."""
    return sorted({own for opponent in opponents for own in opponent.types})


def weakness_patterns(
    candidates: list[Pokemon], opponents: Opponents, chart: Chart
) -> dict[int, frozenset[str]]:
    """For each candidate, by ID: the opposing types that hit it for 2x or more.

    R4 looks at nothing else about a candidate, which is what makes `reduce_slot` safe.
    """
    opposing = opposing_types(opponents)
    return {
        entry.id: frozenset(t for t in opposing if effectiveness(chart, t, entry.types) >= 2)
        for entry in candidates
    }


def describe_team(
    team: list[Pokemon], opponents: Opponents, chart: Chart, levels: Levels
) -> CounterResult:
    """The result for a found team, or for no team; the caller adds the search's own facts."""
    pairs = list(zip(team, opponents, strict=False))
    weak = {
        t: sum(effectiveness(chart, t, counter.types) >= 2 for counter in team)
        for t in opposing_types(opponents)
    }
    totals = {row.name: sum(row.value(c, o, opponents, chart) for c, o in pairs) for row in levels}
    return CounterResult(
        picks=[describe_pick(counter, opponent, opponents, chart) for counter, opponent in pairs],
        totals=totals,
        grid=[[matchup(counter, opponent, chart) for opponent in opponents] for counter in team],
        weakness_counts=weak,
        relaxed=any(count > len(opponents) // 2 for count in weak.values()),
    )


def build_counter_team(
    opponents: Opponents,
    pool: Iterable[Pokemon],
    chart: Chart,
    keep: int | None = None,
    step_limit: int = STEP_LIMIT,
    levels: Levels = SCORE_LEVELS,
) -> CounterResult:
    """The best counter team over the whole pool, unless marked `stopped_early`.

    `keep`, `step_limit` and `levels` have defaults that only tests change: how many
    candidates to keep per weakness pattern (the team size), the step limit per
    strictness level, and the table of score levels.
    """
    candidates = sorted(pool, key=lambda entry: entry.id)
    patterns = weakness_patterns(candidates, opponents, chart)
    kept_per_pattern = keep or len(opponents)
    slots = [
        reduce_slot(score_slot(o, opponents, candidates, chart, levels), patterns, kept_per_pattern)
        for o in opponents
    ]
    repeats = [i > 0 and o.id == opponents[i - 1].id for i, o in enumerate(opponents)]
    ids, steps, stopped = search_levels(slots, repeats, step_limit)
    by_id = {entry.id: entry for entry in candidates}
    team = [by_id[chosen] for chosen in ids or []]
    described = describe_team(team, opponents, chart, levels)
    return replace(described, stopped_early=stopped, steps=steps, pool_size=len(candidates))
