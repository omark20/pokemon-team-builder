"""Tests of choosing the counter team (app/domain/counter.py and counter_search.py).

The exactness tests compare the product with an enumerator in this file that tries
every possible team of the pool, with no kept lists and no pruning. It scores a counter
in a slot with the product's duel and score functions, which test_duel.py checks by
hand; what it checks independently is the choice of team. Pools are small, seeded and
built from the census, each Pokémon carrying four counted moves drawn at random.
"""

import dataclasses
import itertools
import random
from collections import Counter

import pytest

from app.domain.counter import build_counter_team, candidate_pool
from app.domain.counter_result import Cell, CounterResult, OpponentMoves, Side
from app.domain.counter_score import (
    ADVANTAGE_WEIGHT,
    LARGEST_STAT_TOTAL,
    advantage,
    largest_advantage,
    margin_sum,
    margin_weight,
    packed_score,
)
from app.domain.counter_search import (
    GUARD_REACHED,
    LIMIT_RAISED,
    RULE_KEPT,
    Candidate,
    TeamChoice,
    choose_team,
    narrowest_first,
)
from app.domain.duel import duel
from app.domain.move_rules import HITS_HARD, counts, quarters
from app.domain.pokemon import Pokemon
from tests.captured import CENSUS, CHART, MOVES, armed

COUNTED = sorted((m for m in MOVES.values() if counts(m)), key=lambda move: move.id)
DEFAULTS = sorted((p for p in CENSUS.values() if p.is_default), key=lambda pokemon: pokemon.id)
TYRANITAR = armed("tyranitar", "pokemon_248_tyranitar")
CHARIZARD = armed("charizard", "pokemon_6_charizard_dual_type")

# ---- Seeded small cases.


def with_random_moves(pokemon: Pokemon, rng: random.Random) -> Pokemon:
    return dataclasses.replace(pokemon, moves=tuple(rng.sample(COUNTED, 4)))


def small_case(size: int, seed: int) -> tuple[list[Pokemon], list[Pokemon], int]:
    """Opponents (one repeated when there are two or more), a pool of size + 3, and N.

    Each pool member's baseline is taken over a field of twelve, the pool among them.
    """
    rng = random.Random(seed)
    chosen = [with_random_moves(p, rng) for p in rng.sample(DEFAULTS, 2 * size + 12)]
    opponents = chosen[:size]
    if size >= 2:
        opponents[1] = opponents[0]
    pool = chosen[size : 2 * size + 3]
    field = chosen[size + 3 :]
    pool = [dataclasses.replace(p, baseline=margin_sum(p, field, CHART)) for p in pool]
    return opponents, pool, len(field)


# Seeds 0 to 7 at every size, plus, per size, the first seed found whose best team
# breaks the shared-weakness rule; at sizes 1, 3, 5 and 6 that seed's pool also has no
# team keeping it, so the limit must be raised.
EXTRA_SEEDS = {1: 14, 2: 8, 3: 36, 4: 37, 5: 20, 6: 20}
CASES = [(size, seed) for size in range(1, 7) for seed in [*range(8), EXTRA_SEEDS[size]]]


def slot_scores(
    opponents: list[Pokemon], pool: list[Pokemon], n_field: int
) -> list[dict[int, int]]:
    """Per slot, per allowed candidate ID: its score. Every candidate if none hits 2×."""
    slots = []
    for opponent in opponents:
        hard = {c.id: duel(c, opponent, CHART, counter_hits_hard=True) for c in pool}
        able = [c for c in pool if hard[c.id].counter_hit is not None]
        if able:
            fights = hard
        else:
            fights = {c.id: duel(c, opponent, CHART, counter_hits_hard=False) for c in pool}
        scores = {}
        for c in able or pool:
            lower = advantage(c, opponents, CHART, n_field)
            scores[c.id] = packed_score(fights[c.id].margin, lower, sum(c.stats), n_field)
        slots.append(scores)
    return slots


def most_weak(team: tuple[Pokemon, ...], opponents: list[Pokemon]) -> int:
    """The most counters any one opposing type hits for 2× or more."""
    opposing = {t for o in opponents for t in o.types}
    weak = Counter(t for c in team for t in opposing if quarters(CHART, t, c.types) >= HITS_HARD)
    return max(weak.values(), default=0)


def enumerate_teams(opponents, pool, n_field) -> dict[int, int]:
    """Over every possible team: for each value of `most_weak`, the best total score."""
    slots = slot_scores(opponents, pool, n_field)
    best: dict[int, int] = {}
    for team in itertools.permutations(pool, len(opponents)):
        if any(c.id not in slot for c, slot in zip(team, slots, strict=True)):
            continue
        total = sum(slot[c.id] for c, slot in zip(team, slots, strict=True))
        weak = most_weak(team, opponents)
        best[weak] = max(best.get(weak, total), total)
    return best


def expected(best: dict[int, int], size: int) -> tuple[int, int] | None:
    """The rule's limit the answer must keep, and its total; None if no team exists.

    The best team overall if it keeps the limit of half the team; otherwise the best team
    at the lowest limit any team keeps.
    """
    if not best:
        return None
    overall = max(best.values())
    if any(total == overall for weak, total in best.items() if weak <= size // 2):
        return size // 2, overall
    limit = max(size // 2, min(best))
    return limit, max(total for weak, total in best.items() if weak <= limit)


def found(result: CounterResult, opponents, pool, n_field) -> tuple[int, int] | None:
    if not result.picks:
        return None
    by_id = {p.id: p for p in pool}
    team = tuple(by_id[pick.counter.id] for pick in result.picks)
    slots = slot_scores(opponents, pool, n_field)
    return most_weak(team, opponents), sum(slot[c.id] for c, slot in zip(team, slots, strict=True))


@pytest.mark.parametrize(("size", "seed"), CASES)
def test_the_team_is_the_best_of_every_possible_team(size: int, seed: int):
    opponents, pool, n_field = small_case(size, seed)
    truth = expected(enumerate_teams(opponents, pool, n_field), size)
    result = build_counter_team(opponents, pool, CHART, n_field)
    answer = found(result, opponents, pool, n_field)
    if truth is None:
        assert answer is None
    else:
        limit, total = truth
        assert answer is not None and answer[0] <= limit and answer[1] == total
        assert result.weakness_rule == (RULE_KEPT if limit == size // 2 else LIMIT_RAISED)


def test_the_small_cases_reach_the_second_search_at_every_size_and_a_raised_limit():
    second, raised = set(), set()
    for size, seed in CASES:
        opponents, pool, n_field = small_case(size, seed)
        best = enumerate_teams(opponents, pool, n_field)
        truth = expected(best, size)
        keeping = [total for weak, total in best.items() if weak <= size // 2]
        if truth and max(best.values()) not in keeping:  # the best team breaks the rule
            second.add(size)
        if truth and truth[0] > size // 2:
            raised.add(size)
    assert (second, raised) == ({1, 2, 3, 4, 5, 6}, {1, 3, 5, 6})


def test_the_same_input_and_a_shuffled_pool_give_the_same_team():
    opponents, pool, n_field = small_case(6, seed=3)
    first = build_counter_team(opponents, pool, CHART, n_field)
    shuffled = random.Random(1).sample(pool, len(pool))
    assert build_counter_team(opponents, pool, CHART, n_field) == first
    assert build_counter_team(opponents, shuffled, CHART, n_field) == first


def test_every_advantage_in_the_small_cases_is_within_its_bound():
    for size, seed in CASES:
        opponents, pool, n_field = small_case(size, seed)
        bound = largest_advantage(n_field)
        assert all(-bound <= advantage(c, opponents, CHART, n_field) <= bound for c in pool)


# ---- The second search and its guard, on hand-made candidates.

# Two slots facing different opponents. The best pair, A and B, are both weak to fire;
# with one of two counters allowed to be weak to it, the best keeping the rule is A and C.
A, B, C = (
    Candidate(1, 10, 3, frozenset({"fire"})),
    Candidate(2, 9, 3, frozenset({"fire"})),
    Candidate(3, 1, 1, frozenset()),
)
OPPONENTS = [25, 6]


def test_the_second_search_finds_the_best_team_that_keeps_the_rule():
    assert choose_team([[A, B, C], [A, B, C]], OPPONENTS) == TeamChoice([A, C], RULE_KEPT)


def test_a_step_guard_of_one_returns_the_first_team():
    choice = choose_team([[A, B, C], [A, B, C]], OPPONENTS, step_guard=1)
    assert choice == TeamChoice([A, B], GUARD_REACHED)


def test_with_no_team_keeping_the_rule_the_limit_is_raised():
    assert choose_team([[A, B], [A, B]], OPPONENTS) == TeamChoice([A, B], LIMIT_RAISED)


def test_slots_are_searched_narrowest_first_and_the_team_comes_back_in_team_order():
    # Slot 1 has one candidate at its best margin, slot 0 has two, so slot 1 is decided
    # first; the answer still lists slot 0's counter first.
    wide = [Candidate(4, 30, 5, frozenset({"fire"})), Candidate(5, 29, 5, frozenset({"fire"}))]
    narrow = [Candidate(6, 40, 7, frozenset({"fire"})), Candidate(7, 2, 1, frozenset())]
    assert narrowest_first([wide, narrow]) == [1, 0]
    choice = choose_team([wide, narrow], OPPONENTS)
    assert choice == TeamChoice([wide[0], narrow[1]], RULE_KEPT)


# ---- What the page is told.


def test_a_pick_states_its_duel_in_numbers_the_reader_can_check():
    result = build_counter_team([CHARIZARD], [TYRANITAR], CHART, field_size=1)
    (pick,) = result.picks
    assert pick.line == "Tyranitar knocks out Charizard in 1 turn with Stone Edge"
    assert pick.reason == (
        "Tyranitar knocks out Charizard in 1 turn with Stone Edge (rock, 4×): 448 damage, "
        "80% accurate, against 138 HP. Charizard needs 3 turns to knock out Tyranitar with "
        "Earthquake: 72 damage against 160 HP. Charizard is faster, so it strikes first."
    )
    assert pick.outcome == "wins"
    assert (pick.counter, pick.opponent) == (
        Side(248, "tyranitar", "stone-edge", 1),
        Side(6, "charizard", "earthquake", 3),
    )
    assert result.grid == [[Cell("wins", 1, 3)]]
    four = ["overheat", "earthquake", "hurricane", "outrage"]
    assert result.opponent_moves == [OpponentMoves("Charizard", four, True)]


def test_a_counters_own_cell_is_its_picks_duel_and_the_others_allow_any_move():
    # Tyranitar with Crunch (dark, 1× on Venusaur) and Gust (flying, 2×): its pick against
    # Venusaur must use Gust, while against Charizard any move may be used. Only it hits
    # Venusaur for 2× and only Dragonite (Stone Edge) hits Charizard, so the team is forced.
    crunch_and_gust = dataclasses.replace(CENSUS["tyranitar"], moves=(MOVES[242], MOVES[16]))
    venusaur = armed("venusaur", "pokemon_3_venusaur")
    dragonite = armed("dragonite", "pokemon_149_dragonite")
    result = build_counter_team([venusaur, CHARIZARD], [crunch_and_gust, dragonite], CHART, 1)
    pick = result.picks[0]
    assert pick.counter.move == "gust"
    assert result.grid[0][0] == Cell(pick.outcome, pick.counter.turns, pick.opponent.turns)
    any_move = duel(crunch_and_gust, venusaur, CHART, counter_hits_hard=False)
    assert any_move.counter_turns != pick.counter.turns  # the two duels really differ here
    against_charizard = duel(crunch_and_gust, CHARIZARD, CHART, counter_hits_hard=False)
    assert result.grid[0][1].counter_turns == against_charizard.counter_turns


def test_when_nobody_hits_the_opponent_for_two_times_the_rule_is_waived_and_said():
    swift_only = dataclasses.replace(CENSUS["pikachu"], moves=(MOVES[129],))  # normal
    (pick,) = build_counter_team([CHARIZARD], [swift_only], CHART, field_size=1).picks
    assert pick.counter.move == "swift"
    assert "with Swift (normal, 1×)" in pick.reason


def test_too_small_a_pool_gives_no_team():
    assert build_counter_team([CHARIZARD, CHARIZARD], [TYRANITAR], CHART, field_size=1).picks == []


def test_each_weight_outweighs_six_counters_worth_of_everything_below_it():
    assert ADVANTAGE_WEIGHT > 6 * LARGEST_STAT_TOTAL
    for n_field in (1, 1025):
        below = 2 * largest_advantage(n_field) * ADVANTAGE_WEIGHT + LARGEST_STAT_TOTAL
        assert margin_weight(n_field) > 6 * below


# ---- Who may be picked.


def test_leaving_out_legendary_keeps_only_pokemon_known_to_be_neither():
    # Mewtwo is legendary and Mew mythical (samples/species_150_*, species_151_*); a
    # Pokémon whose flags were never read is left out too.
    unread = dataclasses.replace(CENSUS["pikachu"], is_legendary=None, is_mythical=None)
    entries = [CENSUS["charizard"], CENSUS["mewtwo"], CENSUS["mew"], unread]
    assert candidate_pool(entries, leave_out_legendary=True) == [CENSUS["charizard"]]
    assert candidate_pool(entries) == entries  # off by default
    assert len(candidate_pool(CENSUS.values(), leave_out_legendary=True)) == 931


def test_candidate_pool_drops_special_versions_and_removed_entries_only():
    charizard = CENSUS["charizard"]
    removed = dataclasses.replace(CENSUS["pikachu"], removed=True)
    assert candidate_pool([charizard, CENSUS["charizard-mega-x"], removed]) == [charizard]
    assert len(candidate_pool(CENSUS.values())) == 1025
