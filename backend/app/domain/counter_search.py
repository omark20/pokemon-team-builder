"""Choosing the counter team exactly, given every slot's scored candidates.

The only rule tying slots together is that no Pokémon is used twice, so the best
team is an assignment. Each slot keeps its n best candidates, n being the team size:
if a best team used a candidate that was not kept, that slot's n kept candidates
cannot all be on the other n - 1 slots, so a kept one is free and scores at least as
much. A depth-first search then tries every hand-out of kept candidates, abandoning a
branch that cannot beat the best team found.

The shared-weakness rule says no opposing type may hit more than half the counters
for 2× or more. If the best team keeps it, that team is the answer. Otherwise a
second search runs in which each slot keeps its n best candidates of every weakness
pattern (the set of opposing types that hit a candidate for 2×): swapping a candidate
for a kept one of the same pattern changes no type's count, so again nothing is lost.
It decides the narrowest slots first, which changes no possible team but reaches the
slots that decide the rule early. If no team keeps the rule, the limit is raised by
one until a team does. The second search has a step guard; if it is reached, the
first team is the answer. Pure.
"""

from collections import Counter
from dataclasses import dataclass, field

# Steps the second search may take, over every limit tried: about nine times the most
# any of 40,000 random teams took (10,624), and under a second of search on the
# deployed server at about 8 millionths of a second a step.
STEP_GUARD = 100_000

# How the answer stands with the shared-weakness rule.
RULE_KEPT = "kept"
LIMIT_RAISED = "limit_raised"  # no team keeps the rule, so the best at a higher limit
GUARD_REACHED = "guard_reached"  # the second search was cut short: the first team stands


@dataclass(frozen=True)
class Candidate:
    """One candidate for one slot."""

    id: int
    score: int
    margin: int  # its duel margin against this slot's opponent, the score's first level
    weak_to: frozenset[str]  # the opposing types that hit it for 2× or more


def best_first(candidate: Candidate) -> tuple[int, int]:
    """Sort key: higher score first, then lower ID."""
    return -candidate.score, candidate.id


@dataclass
class Search:
    """One depth-first search: what it reads, and the team it is building."""

    slots: list[list[Candidate]]  # per slot, its kept candidates, best first
    repeats_previous: list[bool]  # per slot: same opponent as the slot before it
    weak_limit: int  # most counters one opposing type may hit for 2× or more
    step_limit: int | None
    reachable: list[int]  # per slot: the top score of it and every later slot, added up
    steps: int = 0
    stopped: bool = False
    chosen: list[int] = field(default_factory=list)  # index chosen in each slot so far
    team: list[Candidate] = field(default_factory=list)
    counts: Counter[str] = field(default_factory=Counter)  # counters hit hard, per type
    best_total: int | None = None
    best_team: list[Candidate] | None = None


def reachable(slots: list[list[Candidate]]) -> list[int]:
    """The bound: per slot, the best kept score of it and of every later slot, added up.

    A branch whose total plus this figure for the next slot cannot beat the best team
    found is abandoned.
    """
    tops = [kept[0].score if kept else 0 for kept in slots]
    return [sum(tops[slot:]) for slot in range(len(slots) + 1)]


def repeats_previous(opponents: list[int]) -> list[bool]:
    """Per slot: whether it faces the same opponent as the slot searched before it."""
    return [i > 0 and opponent == opponents[i - 1] for i, opponent in enumerate(opponents)]


def new_search(
    slots: list[list[Candidate]], opponents: list[int], weak_limit: int, step_limit: int | None
) -> Search:
    return Search(slots, repeats_previous(opponents), weak_limit, step_limit, reachable(slots))


def take_step(search: Search) -> bool:
    """Count one step; at the limit, mark the search stopped instead."""
    if search.step_limit is not None and search.steps >= search.step_limit:
        search.stopped = True
        return False
    search.steps += 1
    return True


def cannot_beat_best(search: Search, total: int) -> bool:
    return search.best_total is not None and total <= search.best_total


def may_take(search: Search, candidate: Candidate) -> bool:
    """Not on the team yet, and no type would then hit more counters than the limit."""
    return all(c.id != candidate.id for c in search.team) and all(
        search.counts[weak_to] < search.weak_limit for weak_to in candidate.weak_to
    )


def visit(search: Search, slot: int, total: int) -> None:
    """Try the slot's kept candidates in order, then the later slots under each.

    Where the slot faces the same opponent as the slot before, it only takes
    candidates after that slot's choice, so the same team is not tried twice.
    """
    if not take_step(search):
        return
    if slot == len(search.slots):
        search.best_total, search.best_team = total, list(search.team)
        return
    first = search.chosen[-1] + 1 if search.repeats_previous[slot] else 0
    for index in range(first, len(search.slots[slot])):
        candidate = search.slots[slot][index]
        if cannot_beat_best(search, total + candidate.score + search.reachable[slot + 1]):
            return  # candidates are best first, so no later one can do better
        if may_take(search, candidate):
            take(search, slot, index, total)
        if search.stopped:
            return


def take(search: Search, slot: int, index: int, total: int) -> None:
    """Put one candidate on the team, search the later slots, and take it off again."""
    candidate = search.slots[slot][index]
    search.chosen.append(index)
    search.team.append(candidate)
    search.counts.update(candidate.weak_to)
    visit(search, slot + 1, total + candidate.score)
    search.counts.subtract(candidate.weak_to)
    search.team.pop()
    search.chosen.pop()


def keep_best(candidates: list[Candidate], size: int) -> list[Candidate]:
    return sorted(candidates, key=best_first)[:size]


def keep_best_per_pattern(candidates: list[Candidate], size: int) -> list[Candidate]:
    by_pattern: dict[frozenset[str], list[Candidate]] = {}
    for candidate in candidates:
        by_pattern.setdefault(candidate.weak_to, []).append(candidate)
    kept = [c for group in by_pattern.values() for c in keep_best(group, size)]
    return sorted(kept, key=best_first)


def keeps_rule(team: list[Candidate], limit: int) -> bool:
    counts = Counter(weak_to for candidate in team for weak_to in candidate.weak_to)
    return all(count <= limit for count in counts.values())


def narrowest_first(slots: list[list[Candidate]]) -> list[int]:
    """Slot positions, fewest kept candidates sharing the slot's best margin first.

    Ties keep team order, so neighbouring slots facing the same opponent, which tie,
    stay neighbours.
    """

    def width(slot: int) -> int:
        kept = slots[slot]
        return sum(c.margin == kept[0].margin for c in kept) if kept else 0

    return sorted(range(len(slots)), key=lambda slot: (width(slot), slot))


@dataclass(frozen=True)
class TeamChoice:
    """One candidate per slot in team order, empty if no team exists, and the rule's state."""

    team: list[Candidate]
    weakness_rule: str  # RULE_KEPT, LIMIT_RAISED or GUARD_REACHED


def second_search(
    kept: list[list[Candidate]], opponents: list[int], first_team: list[Candidate], step_guard: int
) -> TeamChoice:
    """The best team that keeps the rule, raising the limit while no team can.

    At a limit of the whole team nothing is ruled out, so the answer there is the first
    team; it is also the answer if the guard is reached.
    """
    order = narrowest_first(kept)
    ordered, faced = [kept[i] for i in order], [opponents[i] for i in order]
    size, steps = len(kept), 0
    for weak_limit in range(size // 2, size):
        search = new_search(ordered, faced, weak_limit, step_guard - steps)
        visit(search, 0, 0)
        steps += search.steps
        if search.stopped:
            return TeamChoice(first_team, GUARD_REACHED)
        if search.best_team is not None:
            team = [search.best_team[order.index(slot)] for slot in range(size)]
            return TeamChoice(team, RULE_KEPT if weak_limit == size // 2 else LIMIT_RAISED)
    return TeamChoice(first_team, LIMIT_RAISED)


def choose_team(
    slots: list[list[Candidate]], opponents: list[int], step_guard: int = STEP_GUARD
) -> TeamChoice:
    """The best team that keeps the shared-weakness rule, or the closest to it that exists.

    `opponents` names each slot's opponent, so slots facing the same one are searched
    without repeating teams. Only tests change `step_guard`.
    """
    size = len(slots)
    first = new_search([keep_best(s, size) for s in slots], opponents, size, None)
    visit(first, 0, 0)
    if first.best_team is None or keeps_rule(first.best_team, size // 2):
        return TeamChoice(first.best_team or [], RULE_KEPT)
    kept = [keep_best_per_pattern(s, size) for s in slots]
    return second_search(kept, opponents, first.best_team, step_guard)
