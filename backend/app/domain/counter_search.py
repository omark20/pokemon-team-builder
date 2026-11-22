"""The two exact searches behind the counter team, and nothing else.

`counter.py` prepares, for every slot of the opposing team, the candidates worth
considering, grouped by weakness pattern: the set of opposing types that hit a
candidate for 2x or more. This module then finds the best team in two stages.

1. `search_patterns` gives each slot a pattern, depth first, never letting one
   opposing type appear in more chosen patterns than the weakness limit allows.
2. `hand_out` turns a complete choice of patterns into actual Pokémon, making sure
   no Pokémon is used twice. Two slots can only want the same Pokémon if they
   chose the same pattern, so only those slots need a search (`hand_out_shared`).

Both searches count their steps and stop at the limit, so the work per request is
bounded. Candidates are known here by ID and score only.
"""

import math
from collections import Counter
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Scored:
    """One candidate for one slot: its ID and its score in that slot."""

    score: int
    id: int


@dataclass(frozen=True)
class PatternGroup:
    """A slot's kept candidates that share one weakness pattern, best first."""

    pattern: frozenset[str]
    kept: tuple[Scored, ...]


@dataclass
class SearchState:
    """Everything one strictness level of the search reads and updates."""

    slots: list[list[PatternGroup]]  # per slot, its groups ordered by their best candidate
    repeats_previous: list[bool]  # per slot: same opponent as the slot before it
    weak_limit: int  # most chosen patterns that may contain one opposing type
    step_limit: int
    counts: Counter[str] = field(default_factory=Counter)  # chosen patterns per opposing type
    chosen: list[int] = field(default_factory=list)  # group index chosen for each slot so far
    chosen_score: int = 0  # best scores of the chosen groups, added up
    steps: int = 0
    stopped: bool = False  # the step limit was reached
    best_score: float = -math.inf
    best_team: list[int] | None = None  # candidate ID per slot


@dataclass
class Deal:
    """One hand-out among the slots that chose the same pattern."""

    kept: list[tuple[Scored, ...]]  # per sharing slot, in slot order
    reachable: list[int]  # per sharing slot: top kept score of it and every later one, added
    picks: list[Scored] = field(default_factory=list)
    best_total: float = -math.inf
    best_picks: list[Scored] | None = None


def take_step(state: SearchState) -> bool:
    """Count one step; at the limit, mark the level stopped and count nothing."""
    if state.steps >= state.step_limit:
        state.stopped = True
        return False
    state.steps += 1
    return True


def fits(state: SearchState, group: PatternGroup) -> bool:
    """Whether choosing this pattern keeps every opposing type within the limit."""
    return all(state.counts[weak_to] < state.weak_limit for weak_to in group.pattern)


def allowed_patterns(state: SearchState, slot: int) -> list[int]:
    """The slot's groups that may be chosen now, in order.

    A slot facing the same opponent as the slot before it starts at that slot's
    choice: the two are interchangeable, so earlier groups would repeat teams.
    """
    groups = state.slots[slot]
    first = state.chosen[slot - 1] if state.repeats_previous[slot] else 0
    return [index for index in range(first, len(groups)) if fits(state, groups[index])]


def later_slots_figure(state: SearchState, slot: int) -> int | None:
    """The most the slots after `slot` could add, or None if one of them is stuck.

    It must be taken before a pattern is chosen for `slot`, so that it is the same
    for every pattern tried there; `search_patterns` relies on that to stop early.
    """
    figure = 0
    for groups in state.slots[slot + 1 :]:
        best = next((group.kept[0].score for group in groups if fits(state, group)), None)
        if best is None:
            return None
        figure += best
    return figure


def search_patterns(state: SearchState, slot: int) -> None:
    """One arrival at a slot: try its allowed patterns, best first.

    The groups are ordered by best score and the later-slot figure is fixed, so
    once one pattern cannot beat the best team found, none after it can.
    """
    if not take_step(state):
        return
    if slot == len(state.slots):
        hand_out(state)
        return
    figure = later_slots_figure(state, slot)
    if figure is None:
        return
    for index in allowed_patterns(state, slot):
        group = state.slots[slot][index]
        best = group.kept[0].score
        if state.chosen_score + best + figure <= state.best_score:
            return
        state.chosen.append(index)
        state.chosen_score += best
        state.counts.update(group.pattern)
        search_patterns(state, slot + 1)
        state.counts.subtract(group.pattern)
        state.chosen_score -= best
        state.chosen.pop()
        if state.stopped:
            return


def hand_out(state: SearchState) -> None:
    """Every slot has a pattern: choose the Pokémon and keep the team if it is the best.

    Patterns are handled in the order of the first slot that chose each. A pattern
    with fewer different candidates than slots wanting it gives no team.
    """
    sharing: dict[frozenset[str], list[int]] = {}
    for slot, index in enumerate(state.chosen):
        sharing.setdefault(state.slots[slot][index].pattern, []).append(slot)
    team = [0] * len(state.chosen)
    total = 0
    for slots in sharing.values():
        kept = [state.slots[slot][state.chosen[slot]].kept for slot in slots]
        picks = [kept[0][0]] if len(slots) == 1 else deal_shared(state, kept)
        if picks is None:
            return
        for slot, pick in zip(slots, picks, strict=True):
            team[slot] = pick.id
            total += pick.score
    if total > state.best_score:
        state.best_score = total
        state.best_team = team


def deal_shared(state: SearchState, kept: list[tuple[Scored, ...]]) -> list[Scored] | None:
    """The best different candidates for slots sharing a pattern, or None.

    None means there are too few different candidates, or the step limit cut the
    search off, in which case a partial answer is not trusted.
    """
    tops = [candidates[0].score for candidates in kept]
    reachable = [sum(tops[position:]) for position in range(len(tops))]
    deal = Deal(kept, reachable)
    hand_out_shared(state, deal, 0, 0)
    return None if state.stopped else deal.best_picks


def hand_out_shared(state: SearchState, deal: Deal, position: int, total: int) -> None:
    """One arrival at a sharing slot: try its kept candidates not already taken."""
    if not take_step(state):
        return
    if position == len(deal.kept):
        if total > deal.best_total:
            deal.best_total = total
            deal.best_picks = list(deal.picks)
        return
    if total + deal.reachable[position] <= deal.best_total:
        return
    for candidate in deal.kept[position]:
        if any(candidate.id == pick.id for pick in deal.picks):
            continue
        deal.picks.append(candidate)
        hand_out_shared(state, deal, position + 1, total + candidate.score)
        deal.picks.pop()
        if state.stopped:
            return
