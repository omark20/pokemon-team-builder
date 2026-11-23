"""Tests of one duel and of the moves it uses: which count, the default four, damage, turns.

Expected numbers are worked by hand from the captured data in samples/, step by step in
each test's comment; none comes from the code under test.
"""

import dataclasses

import pytest

from app.domain.default_moves import default_four
from app.domain.duel import Duel, best_hit, damage, duel, turns_to_knock_out
from app.domain.move_rules import accuracy, counts
from app.domain.moves import Move
from tests.captured import CENSUS, CHART, FIELD, MOVES, armed, learnable

TYRANITAR = armed("tyranitar", "pokemon_248_tyranitar")
CHARIZARD = armed("charizard", "pokemon_6_charizard_dual_type")
STONE_EDGE, EARTHQUAKE, FLAMETHROWER, SWIFT, ENERGY_BALL = (
    MOVES[i] for i in (444, 89, 53, 129, 412)
)

# ---- Which moves count.

# The 39 moves the phrases remove, as listed with each phrase in the specification.
LEFT_OUT = {
    "razor-wind", "hyper-beam", "solar-beam", "skull-bash", "sky-attack", "blast-burn",
    "hydro-cannon", "frenzy-plant", "giga-impact", "rock-wrecker", "roar-of-time", "freeze-shock",
    "ice-burn", "solar-blade", "prismatic-laser", "meteor-assault", "eternabeam", "meteor-beam",
    "fly", "dig", "dive", "bounce", "shadow-force", "sky-drop", "phantom-force",
    "self-destruct", "explosion", "dream-eater", "snore", "sucker-punch",
    "fake-out", "last-resort", "belch", "first-impression", "future-sight", "doom-desire",
    "focus-punch", "shell-trap", "synchronoise",
}  # fmt: skip


def damaging(move: Move) -> bool:
    """Physical or special, power above 0, a standard type: what the phrases then filter."""
    return move.damage_class != "status" and (move.power or 0) > 0 and move.type != "shadow"


def test_the_phrases_remove_exactly_the_39_listed_moves_and_leave_533():
    removed = {m.name for m in MOVES.values() if damaging(m) and not counts(m)}
    assert removed == LEFT_OUT
    assert sum(counts(m) for m in MOVES.values()) == 533


def test_hard_press_does_not_count_and_tachyon_cutter_cannot_miss():
    hard_press, tachyon_cutter = MOVES[912], MOVES[911]  # power 0; accuracy 0 in PokéAPI
    assert not counts(hard_press)
    assert counts(tachyon_cutter) and accuracy(tachyon_cutter) == 100


# ---- The four moves a Pokémon carries.


@pytest.mark.parametrize(
    ("name", "capture", "four"),
    [
        ("charizard", "pokemon_6_charizard_dual_type", "overheat earthquake hurricane outrage"),
        ("tyranitar", "pokemon_248_tyranitar", "foul-play superpower stone-edge earthquake"),
        ("dragonite", "pokemon_149_dragonite", "outrage superpower earthquake stone-edge"),
        ("blastoise", "pokemon_9_blastoise", "water-spout ice-beam outrage earthquake"),
        ("pikachu", "pokemon_25_pikachu_single_type", "volt-tackle double-edge surf play-rough"),
        ("garchomp", "pokemon_445_garchomp", "outrage earthquake stone-edge fire-fang"),
        ("gengar", "pokemon_94_gengar", "sludge-wave shadow-ball energy-ball focus-blast"),
        ("snorlax", "pokemon_143_snorlax", "double-edge superpower steel-roller earthquake"),
        ("alakazam", "pokemon_65_alakazam", "psychic focus-blast energy-ball shadow-ball"),
        ("machamp", "pokemon_68_machamp", "superpower stone-edge earthquake darkest-lariat"),
    ],
)
def test_default_four_of_the_captured_pokemon(name: str, capture: str, four: str):
    assert [move.name for move in armed(name, capture).moves] == four.split()


def test_a_pokemon_with_no_moves_listed_carries_none():
    assert learnable("pokemon_10195_venusaur_gmax_no_moves") == []
    gigantamax = armed("venusaur-gmax", "pokemon_10195_venusaur_gmax_no_moves")
    assert (gigantamax.moves, gigantamax.moves_listed) == ((), False)


def test_a_pokemon_with_no_counted_move_carries_none():
    growl, hyper_beam = MOVES[45], MOVES[63]  # a status move, and one that must recharge
    assert default_four(CENSUS["pikachu"], [growl, hyper_beam], FIELD, CHART) == ()


def test_fewer_than_four_when_fewer_types_are_on_offer():
    # Two counted moves of different types: both add something, nothing else is on offer.
    chosen = default_four(CENSUS["charizard"], [FLAMETHROWER, EARTHQUAKE, MOVES[45]], FIELD, CHART)
    assert sorted(chosen) == [53, 89]


def test_equal_strengths_go_to_the_lower_move_id():
    twin = dataclasses.replace(FLAMETHROWER, id=10_000, name="twin")  # the same in every respect
    assert default_four(CENSUS["charizard"], [twin, FLAMETHROWER], FIELD, CHART) == (53,)


# ---- Damage, the best move and turns.


def test_stone_edge_from_tyranitar_on_charizard():
    # Physical, 4×: 22 × 100 × 139 ÷ 83 = 3,684; ÷ 50 = 73; + 2 = 75; rock is Tyranitar's
    # own type, × 3 ÷ 2 = 112; rock on fire and flying is 4×, × 16 ÷ 4 = 448.
    assert damage(TYRANITAR, STONE_EDGE, CHARIZARD, CHART) == 448
    # 138 HP × 100 ÷ (448 × 80) is 0.39, rounded up to 1 turn.
    assert turns_to_knock_out(best_hit(TYRANITAR, CHARIZARD, CHART), CHARIZARD) == 1


def test_a_special_move_flamethrower_from_charizard_on_venusaur():
    # Special Attack 109 + 5 against Special Defense 100 + 5: 22 × 90 × 114 ÷ 105 = 2,149;
    # ÷ 50 = 42; + 2 = 44; fire is Charizard's own, 66; fire on grass and poison is 2×, 132.
    assert damage(CHARIZARD, FLAMETHROWER, CENSUS["venusaur"], CHART) == 132


def test_a_move_with_no_accuracy_swift_from_pikachu_on_charizard():
    # 22 × 60 × 55 ÷ 90 = 806; ÷ 50 = 16; + 2 = 18; not Pikachu's type; normal is 1×: 18.
    # Accuracy counts as 100: 138 × 100 ÷ (18 × 100) = 7.67, rounded up to 8 turns.
    pikachu = dataclasses.replace(CENSUS["pikachu"], moves=(SWIFT,))
    hit = best_hit(pikachu, CHARIZARD, CHART)
    assert hit is not None and hit.damage == 18
    assert turns_to_knock_out(hit, CHARIZARD) == 8


def test_a_quarter_multiplier_energy_ball_from_venusaur_on_charizard():
    # 22 × 90 × 105 ÷ 90 = 2,310; ÷ 50 = 46; + 2 = 48; grass is Venusaur's own, 72;
    # grass on fire and flying is ¼×, × 1 ÷ 4 = 18.
    assert damage(CENSUS["venusaur"], ENERGY_BALL, CHARIZARD, CHART) == 18


def test_an_immunity_does_nothing_and_is_never_the_best_move():
    assert damage(TYRANITAR, EARTHQUAKE, CHARIZARD, CHART) == 0  # ground on flying
    only_earthquake = dataclasses.replace(TYRANITAR, moves=(EARTHQUAKE,))
    assert best_hit(only_earthquake, CHARIZARD, CHART) is None
    assert turns_to_knock_out(None, CHARIZARD) == 10


def test_a_pokemon_with_no_moves_needs_ten_turns():
    gigantamax = armed("venusaur-gmax", "pokemon_10195_venusaur_gmax_no_moves")
    assert duel(CHARIZARD, gigantamax, CHART, counter_hits_hard=True).opponent_turns == 10


# ---- The duel.


def test_tyranitar_beats_charizard_with_four_moves_a_side():
    # Charizard's best of its four on Tyranitar is Earthquake: 22 × 100 × 89 ÷ 115 = 1,702;
    # ÷ 50 = 34; + 2 = 36; ground on rock and dark is 2×: 72. 160 × 100 ÷ 7,200 → 3 turns.
    # Charizard is faster (100 against 61). Margin 2 × (3 - 1) - 1 = +3.
    fight = duel(TYRANITAR, CHARIZARD, CHART, counter_hits_hard=True)
    assert fight.opponent_hit is not None and fight.opponent_hit.move.name == "earthquake"
    assert (fight.opponent_hit.damage, fight.counter_turns, fight.opponent_turns) == (72, 1, 3)
    assert (fight.speed_edge, fight.margin) == (-1, 3)


def test_aerodactyl_beats_charizard_by_five():
    # Stone Edge: 22 × 100 × 110 ÷ 83 = 2,915; ÷ 50 = 58; + 2 = 60; same type, 90; 4×, 360.
    # 138 × 100 ÷ (360 × 80) → 1 turn. Charizard's best back is Outrage (Overheat and
    # Hurricane are ½× on rock, Earthquake does nothing to flying): 22 × 120 × 89 ÷ 70 =
    # 3,356; ÷ 50 = 67; + 2 = 69; 1×. 140 × 100 ÷ 6,900 → 3 turns. Aerodactyl is faster
    # (130 against 100): margin 2 × (3 - 1) + 1 = +5.
    aerodactyl = armed("aerodactyl", "pokemon_142_aerodactyl")
    fight = duel(aerodactyl, CHARIZARD, CHART, counter_hits_hard=True)
    assert fight.counter_hit is not None and fight.opponent_hit is not None
    assert (fight.counter_hit.move.name, fight.counter_hit.damage) == ("stone-edge", 360)
    assert (fight.opponent_hit.move.name, fight.opponent_hit.damage) == ("outrage", 69)
    assert (fight.counter_turns, fight.opponent_turns, fight.margin) == (1, 3, 5)


def test_allowed_focus_blast_charizard_would_win_instead():
    # Focus Blast, 236 damage, accuracy 70: 160 × 100 ÷ (236 × 70) → 1 turn, and Charizard
    # strikes first: margin 2 × (1 - 1) - 1 = -1. The four do not include it.
    focus_blast = MOVES[411]
    assert damage(CHARIZARD, focus_blast, TYRANITAR, CHART) == 236
    with_it = dataclasses.replace(CHARIZARD, moves=(focus_blast,))
    assert duel(TYRANITAR, with_it, CHART, counter_hits_hard=True).margin == -1


@pytest.mark.parametrize(
    ("counter_turns", "opponent_turns", "speed_edge", "margin"),
    [
        (2, 2, 1, 1),  # equal turns, counter faster: its last hit lands first
        (2, 3, -1, 1),  # one turn fewer but slower: still ahead
        (2, 2, 0, 0),  # equal turns and speed: a draw
        (3, 2, 1, -1),  # one turn more though faster: the opponent wins
    ],
)
def test_the_margins_sign_in_the_four_orderings(counter_turns, opponent_turns, speed_edge, margin):
    assert Duel(None, None, counter_turns, opponent_turns, speed_edge).margin == margin


def test_a_counter_may_only_use_a_move_that_hits_for_two_times_or_more():
    # Carrying only Earthquake, ground on grass and poison is ½ × 2 = 1×: it may use it in
    # general, but it is no counter for Venusaur.
    only_neutral = dataclasses.replace(CHARIZARD, moves=(EARTHQUAKE,))
    assert duel(only_neutral, CENSUS["venusaur"], CHART, counter_hits_hard=True).counter_hit is None
    assert (
        duel(only_neutral, CENSUS["venusaur"], CHART, counter_hits_hard=False).counter_hit
        is not None
    )
