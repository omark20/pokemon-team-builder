"""Tests of the counter-team search (app/domain/counter.py).

Expected values never come from the code under test. They come from the worked
examples computed by hand, from the captured PokéAPI data in samples/, and from a
brute-force enumerator in this file: it tries every possible team with no pruning
and no shortcuts, and scores teams with its own reading of the type files.
"""

import dataclasses
import functools
import itertools
import json
import random
from collections.abc import Callable, Sequence
from pathlib import Path

import pytest

from app.domain.counter import (
    SCORE_LEVELS,
    CounterResult,
    Pokemon,
    ScoreLevel,
    build_counter_team,
    candidate_pool,
)
from app.domain.types import build_chart

SAMPLES = Path(__file__).resolve().parents[2] / "samples"
Team = tuple[Pokemon, ...]
Totals = tuple[int, ...]


def load_species_flags() -> dict[int, tuple[bool, bool]]:
    """(is_legendary, is_mythical) by Pokémon id, from samples/census_all_species.tsv.

    Each species row lists its varieties as Pokémon ids; every one takes the species' flags.
    """
    flags = {}
    for row in (SAMPLES / "census_all_species.tsv").read_text().splitlines()[1:]:
        _id, _name, legendary, mythical, _baby, varieties = row.split("\t")
        for variety in varieties.split(","):
            flags[int(variety.split(":")[0])] = (legendary == "true", mythical == "true")
    return flags


def load_census() -> dict[str, Pokemon]:
    """Every Pokémon in samples/census_all_pokemon.tsv, by name, with its species' flags."""
    flags = load_species_flags()
    census = {}
    for row in (SAMPLES / "census_all_pokemon.tsv").read_text().splitlines()[1:]:
        number, name, _species, is_default, types, *rest = row.split("\t")
        legendary, mythical = flags[int(number)]
        census[name] = Pokemon(
            id=int(number),
            name=name,
            types=tuple(types.split("/")),
            stats=tuple(int(value) for value in rest[:6]),
            is_default=is_default == "true",
            is_legendary=legendary,
            is_mythical=mythical,
        )
    return census


def load_type_files() -> list[dict]:
    """The captured /type responses of the 18 standard types (ids 1 to 18)."""
    files = [json.loads(path.read_text()) for path in SAMPLES.glob("type_*_*.json")]
    return [file for file in files if file["id"] <= 18]


def own_chart(type_files: list[dict]) -> dict[tuple[str, str], float]:
    """Attacker and defender to multiplier, read here from the `*_damage_to` lists."""
    listed = {"double_damage_to": 2.0, "half_damage_to": 0.5, "no_damage_to": 0.0}
    names = [file["name"] for file in type_files]
    chart = {(attacker, defender): 1.0 for attacker in names for defender in names}
    for file in type_files:
        for key, multiplier in listed.items():
            for defender in file["damage_relations"][key]:
                chart[file["name"], defender["name"]] = multiplier
    return chart


CENSUS = load_census()
POOL = candidate_pool(CENSUS.values())
POOL_931 = candidate_pool(CENSUS.values(), leave_out_legendary=True)
# The exactness tests run on both pools the product can be asked to search.
BOTH_POOLS = [pytest.param(POOL, id="all 1,025"), pytest.param(POOL_931, id="931, no legendary")]
TYPE_FILES = load_type_files()
CHART = build_chart(TYPE_FILES)  # the product's chart, passed to the product
OWN_CHART = own_chart(TYPE_FILES)  # this file's chart, used by the enumerator only
POINTS = {4.0: 2, 2.0: 1, 1.0: 0, 0.5: -1, 0.25: -2, 0.0: -3}


def team(names: str) -> Team:
    return tuple(CENSUS[name] for name in names.split())


# ---- This file's own scoring, written from the definitions, not from the product.


@functools.cache
def eff(attack_type: str, defender: Pokemon) -> float:
    multiplier = 1.0
    for defender_type in defender.types:
        multiplier *= OWN_CHART[attack_type, defender_type]
    return multiplier


def attack(attacker: Pokemon, defender: Pokemon) -> float:
    return max(eff(attack_type, defender) for attack_type in attacker.types)


@functools.cache
def matchup(counter: Pokemon, opponent: Pokemon) -> int:
    return POINTS[attack(counter, opponent)] - POINTS[attack(opponent, counter)]


def totals(counters: Team, opponents: Team) -> Totals:
    """(assigned points, coverage, base stats) of a team, compared in that order."""
    assigned = sum(matchup(c, e) for c, e in zip(counters, opponents, strict=True))
    coverage = sum(matchup(c, e) for c in counters for e in opponents)
    return assigned, coverage, sum(sum(c.stats) for c in counters)


def weakness_counts(counters: Team, opponents: Team) -> dict[str, int]:
    """For each opposing type, how many counters it hits for 2x or more."""
    opposing = {t for opponent in opponents for t in opponent.types}
    return {t: sum(eff(t, c) >= 2 for c in counters) for t in opposing}


def worst_weakness(counters: Team, opponents: Team) -> int:
    return max(weakness_counts(counters, opponents).values())


Measure = Callable[[Team, Team], Totals]


@functools.cache
def brute_force(
    opponents: Team,
    pool: Team,
    measure: Measure = totals,
    allow_repeats: bool = False,
    use_shared_weakness_rule: bool = True,
) -> tuple[int, Totals] | None:
    """The true optimum: (weakness limit it needs, best totals), or None for no team.

    Every team is tried. A slot takes any pool member that hits its opponent for 2x
    or more, or any pool member at all when none does. The limit starts at half the
    team size and is raised one at a time until some team fits.
    """
    size = len(opponents)
    able = [[c for c in pool if attack(c, e) >= 2] or list(pool) for e in opponents]
    teams = [t for t in itertools.product(*able) if allow_repeats or len(set(t)) == size]
    scored = [(worst_weakness(t, opponents), measure(t, opponents)) for t in teams]
    for limit in range(size // 2 if use_shared_weakness_rule else size, size + 1):
        fitting = [total for worst, total in scored if worst <= limit]
        if fitting:
            return limit, max(fitting)
    return None


def found(result: CounterResult, opponents: Team, measure: Measure = totals) -> object:
    """The product's answer in the enumerator's terms, measured by this file."""
    if not result.picks:
        return None
    counters = tuple(pick.counter for pick in result.picks)
    limit = max(len(opponents) // 2, worst_weakness(counters, opponents))
    return limit, measure(counters, opponents)


def picked(result: CounterResult) -> str:
    return " ".join(pick.counter.name for pick in result.picks)


# ---- The four worked examples: small pools, every number checkable by hand.

EXAMPLES = [
    pytest.param(
        "charizard",
        "golem tyranitar blastoise pikachu venusaur dragonite",
        "tyranitar",
        (3, 3, 600),
        id="1: an immunity, a 4x, and a tie broken by base stats (not golem)",
    ),
    pytest.param(
        "venusaur arcanine",
        "charizard gyarados nidoking",
        "charizard gyarados",
        (3, 5, 1074),
        id="2: the best pairing, not slot-by-slot greedy (gyarados nidoking)",
    ),
    pytest.param(
        "venusaur charizard",
        "golem lapras jolteon",
        "lapras jolteon",
        (1, 1, 1060),
        id="3: the shared-weakness rule rejects lapras golem",
    ),
    pytest.param(
        "venusaur charizard",
        "gyarados dragonite tyranitar",
        "gyarados tyranitar",
        (4, 4, 1140),
        id="4: coverage decides against the higher base stats of dragonite",
    ),
]


@pytest.mark.parametrize(("opponents", "pool", "expected_team", "expected_totals"), EXAMPLES)
def test_worked_example(opponents: str, pool: str, expected_team: str, expected_totals: Totals):
    result = build_counter_team(team(opponents), team(pool), CHART)
    assert picked(result) == expected_team
    assert tuple(result.totals.values()) == expected_totals
    assert not result.relaxed


REASONS = [
    pytest.param(
        "charizard",
        "golem tyranitar blastoise",
        0,
        "Tyranitar (rock, dark) hits Charizard for 4× with rock attacks. "
        "Charizard's best attack back does ½×. "
        "Across the whole opposing team its matchups add up to +3.",
        id="example 1: a positive coverage carries its sign",
    ),
    pytest.param(
        "venusaur charizard",
        "golem lapras jolteon",
        1,
        "Jolteon (electric) hits Charizard for 2× with electric attacks. "
        "Charizard's best attack back does 1×. "
        "Across the whole opposing team its matchups add up to 0.",
        id="example 3: a coverage of zero has no sign",
    ),
]


@pytest.mark.parametrize(("opponents", "pool", "slot", "expected"), REASONS)
def test_reason_sentence_states_the_true_multipliers_and_coverage(opponents, pool, slot, expected):
    result = build_counter_team(team(opponents), team(pool), CHART)
    assert result.picks[slot].reason == expected


def test_empty_team_gives_an_empty_result():
    result = build_counter_team((), POOL, CHART)
    assert result.picks == []
    assert result.pool_size == 1025


# ---- Exactness: the search against the true optimum on small pools.

CASES_PER_SIZE = 500


def small_case(rng: random.Random, size: int, candidates: list[Pokemon]) -> tuple[Team, Team]:
    """One seeded case: random, repeated or one-type opponents, and a small pool."""
    everyone = list(CENSUS.values())
    kind = rng.choice(["random", "repeated", "one type"])
    if kind == "random":
        opponents = rng.sample(everyone, size)
    elif kind == "repeated":
        opponents = rng.choices(rng.sample(everyone, (size + 1) // 2), k=size)
    else:
        shared = rng.choice(sorted({t for p in everyone for t in p.types}))
        opponents = rng.sample([p for p in everyone if shared in p.types], size)
    useful = [c for c in candidates if any(attack(c, e) >= 2 for e in opponents)]
    source = useful if rng.random() < 0.7 else candidates
    pool = rng.sample(source, rng.randint(size, 14 if size <= 4 else 8))
    return tuple(opponents), tuple(pool)


@functools.cache
def small_cases(size: int, leave_out_legendary: bool = False) -> list[tuple[Team, Team]]:
    """Seeded cases whose pools are drawn from all candidates or from the 931."""
    rng = random.Random(2026 + size + 100 * leave_out_legendary)
    candidates = POOL_931 if leave_out_legendary else POOL
    return [small_case(rng, size, candidates) for _ in range(CASES_PER_SIZE)]


@pytest.mark.parametrize("leave_out_legendary", [False, True], ids=["all", "no legendary"])
@pytest.mark.parametrize("size", range(1, 7))
def test_search_matches_brute_force_on_small_pools(size: int, leave_out_legendary: bool):
    for opponents, pool in small_cases(size, leave_out_legendary):
        result = build_counter_team(opponents, pool, CHART)
        truth = brute_force(opponents, pool)
        assert found(result, opponents) == truth, (opponents, pool)
        assert result.relaxed == (truth is not None and truth[0] > size // 2)
        assert not result.stopped_early


def test_small_cases_exercise_both_rules_the_fallback_and_no_team():
    """The comparison above means little unless each rule decides some case."""
    cases = [case for size in range(2, 5) for case in small_cases(size)]
    truths = [brute_force(*case) for case in cases]
    with_repeats = [brute_force(*case, allow_repeats=True) for case in cases]
    without_rule = [brute_force(*case, use_shared_weakness_rule=False) for case in cases]
    assert any(a != b for a, b in zip(truths, with_repeats, strict=True))
    assert any(a and b and a[1] != b[1] for a, b in zip(truths, without_rule, strict=True))
    assert any(a and a[0] > len(case[0]) // 2 for a, case in zip(truths, cases, strict=True))
    assert None in truths


# Inputs on which pruning with a later-slot figure taken at the wrong moment gives a
# wrong answer. A seeded random set meets one about once in 700, so they are named.
PRUNING_CASES = [
    (
        "quaquaval wooloo thundurus-therian lampent bastiodon grapploct",
        "iron-jugulis iron-treads nosepass dedenne carvanha togedemaru marowak",
        (9, 4, 2806),
    ),
    (
        "diglett-alola kartana magnemite",
        "centiskorch stufful cloyster ninetales slowking great-tusk",
        (6, 12, 1600),
    ),
    (
        "poipole glameow teddiursa geodude",
        "stufful blaziken kirlia iron-valiant passimian morelull quilladin",
        (4, 5, 1553),
    ),
    ("nihilego panpour thievul slaking", "dolliv bastiodon claydol bruxish", (6, 6, 1824)),
    ("primeape vanillite copperajah", "kadabra tirtouga emolga elgyem golett", (5, 5, 1058)),
    ("piloswine sunkern glimmora", "mudkip pelipper tropius gabite lucario", (7, 5, 1295)),
]


@pytest.mark.parametrize(("opponents", "pool", "expected_totals"), PRUNING_CASES)
def test_named_pruning_case(opponents: str, pool: str, expected_totals: Totals):
    strictest = len(opponents.split()) // 2
    assert brute_force(team(opponents), team(pool)) == (strictest, expected_totals)
    result = build_counter_team(team(opponents), team(pool), CHART)
    assert found(result, team(opponents)) == (strictest, expected_totals)


# ---- The real pool: 1,025 candidates from the census file.

ORICORIO = "oricorio-sensu calyrex-shadow spectrier pumpkaboo-super gimmighoul-roaming gengar-mega"
EISCUE = "eiscue-noice masquerain cryogonal solosis morpeko-full-belly karrablast"
SIX_ROTOM = "rotom rotom rotom rotom rotom rotom"

# Opponents, expected totals, and the expected team where it was worked out by name.
FULL_POOL_CASES = [
    ("charizard", (3, 3, 600), "tyranitar"),
    ("charizard charizard", (6, 12, 1200), "tyranitar diancie"),
    ("charizard blastoise venusaur", (9, 6, 1677), "archeops hydrapple celesteela"),
    (ORICORIO, (15, 79, 2910), None),
    (EISCUE, (18, 53, 3480), None),
    (SIX_ROTOM, (16, 96, 3333), None),
]


@pytest.mark.parametrize(("opponents", "expected_totals", "expected_team"), FULL_POOL_CASES)
def test_full_pool_reference_result(opponents: str, expected_totals: Totals, expected_team: str):
    # A step limit far above any search, so nothing here depends on a step count.
    result = build_counter_team(team(opponents), POOL, CHART, step_limit=10_000_000)
    assert tuple(result.totals.values()) == expected_totals
    assert expected_team in (None, picked(result))
    assert not result.stopped_early
    assert not result.relaxed


@pytest.mark.parametrize("pool", BOTH_POOLS)
@pytest.mark.parametrize("opponents", [ORICORIO, EISCUE, SIX_ROTOM])
def test_step_limit_bounds_the_work_and_still_returns_a_team(opponents: str, pool: list[Pokemon]):
    enemy = team(opponents)
    result = build_counter_team(enemy, pool, CHART, step_limit=50)
    counters = tuple(pick.counter for pick in result.picks)
    assert len(set(counters)) == 6
    assert all(attack(c, e) >= 2 for c, e in zip(counters, enemy, strict=True))
    assert result.stopped_early
    assert result.steps <= 50 * 4 + 6  # four strictness levels for six, plus the last resort
    assert result.relaxed == (worst_weakness(counters, enemy) > 3)


PROPERTY_TEAMS = [
    pytest.param("pikachu", id="one"),
    pytest.param("charizard blastoise venusaur", id="three"),
    pytest.param("charizard blastoise venusaur pikachu gengar dragonite", id="six, mixed"),
    pytest.param("charmander vulpix growlithe ponyta magmar flareon", id="all fire"),
    pytest.param("squirtle psyduck poliwag seel staryu vaporeon", id="all water"),
    pytest.param(SIX_ROTOM, id="one Pokémon six times"),
]


@pytest.mark.parametrize("opponents", PROPERTY_TEAMS)
def test_returned_team_obeys_the_four_rules(opponents: str):
    enemy = team(opponents)
    result = build_counter_team(enemy, POOL, CHART)
    counters = tuple(pick.counter for pick in result.picks)
    assert len(counters) == len(enemy)  # R1
    assert all(attack(c, e) >= 2 for c, e in zip(counters, enemy, strict=True))  # R2
    assert len(set(counters)) == len(counters)  # R3
    assert result.relaxed or worst_weakness(counters, enemy) <= len(enemy) // 2  # R4


@pytest.mark.parametrize("opponents", PROPERTY_TEAMS)
def test_reported_numbers_describe_the_returned_team(opponents: str):
    enemy = team(opponents)
    result = build_counter_team(enemy, POOL, CHART)
    counters = tuple(pick.counter for pick in result.picks)
    assert tuple(result.totals.values()) == totals(counters, enemy)
    assert result.grid == [[matchup(c, e) for e in enemy] for c in counters]
    assert [pick.coverage for pick in result.picks] == [sum(row) for row in result.grid]
    assert result.weakness_counts == weakness_counts(counters, enemy)


def test_result_does_not_depend_on_pool_order():
    enemy = team("charizard blastoise venusaur")
    shuffled = random.Random(7).sample(POOL, len(POOL))
    assert build_counter_team(enemy, shuffled, CHART) == build_counter_team(enemy, POOL, CHART)


def reduction_teams() -> list[Team]:
    """300 seeded random opposing teams of sizes 1 to 6, and 60 teams sharing one type."""
    rng = random.Random(1025)
    everyone = list(CENSUS.values())
    teams = [tuple(rng.sample(everyone, rng.randint(1, 6))) for _ in range(300)]
    for _ in range(60):
        shared = rng.choice(sorted({t for p in everyone for t in p.types}))
        teams.append(tuple(rng.sample([p for p in everyone if shared in p.types], 6)))
    return teams


@pytest.mark.parametrize("pool", BOTH_POOLS)
def test_keeping_n_per_pattern_gives_the_same_score_as_keeping_4n(pool: list[Pokemon]):
    """Checks the reduction only: two runs of the same search, one four times wider."""
    teams = reduction_teams()
    skipped = 0
    for enemy in teams:
        wider = build_counter_team(enemy, pool, CHART, keep=4 * len(enemy))
        if wider.stopped_early:
            skipped += 1
            continue
        assert found(build_counter_team(enemy, pool, CHART), enemy) == found(wider, enemy)
    print(f"{skipped} of {len(teams)} wider searches hit the step limit and were not compared")
    assert skipped * 10 <= len(teams)


# ---- The seams: who may be picked, and the table of score levels.


def test_leaving_out_legendary_keeps_only_pokemon_known_to_be_neither():
    # Mewtwo is legendary and Mew mythical (samples/species_150_*, species_151_*); a
    # Pokémon whose flags were never read is left out too.
    unread = dataclasses.replace(CENSUS["pikachu"], is_legendary=None, is_mythical=None)
    entries = [CENSUS["charizard"], CENSUS["mewtwo"], CENSUS["mew"], unread]
    assert candidate_pool(entries, leave_out_legendary=True) == [CENSUS["charizard"]]
    assert candidate_pool(entries) == entries  # off by default
    assert len(POOL_931) == 931


def test_candidate_pool_drops_special_versions_and_removed_entries_only():
    charizard = CENSUS["charizard"]
    removed = dataclasses.replace(CENSUS["pikachu"], removed=True)
    assert candidate_pool([charizard, CENSUS["charizard-mega-x"], removed]) == [charizard]
    assert len(POOL) == 1025


def speed(counter: Pokemon, _opponent: Pokemon, _opponents: Sequence[Pokemon], _chart) -> int:
    return counter.stats[5]


# A made-up fourth level below the real three, whose weights are scaled up to make room.
FOUR_LEVELS = (
    *(dataclasses.replace(level, weight=level.weight * 10_000) for level in SCORE_LEVELS),
    ScoreLevel("speed", speed, smallest=0, largest=255, weight=1),
)


@pytest.mark.parametrize("levels", [SCORE_LEVELS, FOUR_LEVELS], ids=["three levels", "four"])
def test_each_weight_outweighs_everything_below_it_for_six_counters(levels):
    for index, level in enumerate(levels):
        below = sum(6 * (low.largest - low.smallest) * low.weight for low in levels[index + 1 :])
        assert level.weight > below, level.name


def totals_with_speed(counters: Team, opponents: Team) -> Totals:
    return (*totals(counters, opponents), sum(c.stats[5] for c in counters))


def test_a_fourth_score_level_needs_no_change_to_the_search():
    for opponents, pool in small_cases(3):
        result = build_counter_team(opponents, pool, CHART, levels=FOUR_LEVELS)
        truth = brute_force(opponents, pool, measure=totals_with_speed)
        assert found(result, opponents, measure=totals_with_speed) == truth
