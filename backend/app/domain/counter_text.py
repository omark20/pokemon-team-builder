"""The sentences the page shows about a duel, built from the duel's own numbers.

Every number in a sentence is one the score was worked out from, so a sentence cannot
disagree with the choice it explains. Pokémon names are written as the page writes
them (first letter capital); move names as words ("stone-edge" is "Stone Edge"). Pure.
"""

from app.domain.duel import MOST_TURNS, Duel, Hit
from app.domain.move_rules import accuracy
from app.domain.pokemon import Pokemon, hp_at_level_50

WRITTEN_MULTIPLIERS = {16: "4×", 8: "2×", 4: "1×", 2: "½×", 1: "¼×", 0: "0×"}


def pokemon_name(pokemon: Pokemon) -> str:
    return pokemon.name[:1].upper() + pokemon.name[1:]


def move_name(hit: Hit) -> str:
    return " ".join(word.capitalize() for word in hit.move.name.split("-"))


def turn_count(turns: int) -> str:
    """A number of turns as written: "4", or "10 or more" at the ceiling."""
    return f"{turns} or more" if turns == MOST_TURNS else str(turns)


def turns_text(turns: int) -> str:
    return "1 turn" if turns == 1 else f"{turn_count(turns)} turns"


def outcome(duel: Duel) -> str:
    """The label next to a pick: how its duel ends for the counter."""
    if duel.margin > 0:
        return "wins"
    return "draws with" if duel.margin == 0 else "loses to"


def pick_line(duel: Duel, counter: Pokemon, opponent: Pokemon) -> str:
    """One line per pick: "Garchomp knocks out Charizard in 1 turn with Stone Edge"."""
    ours, theirs = pokemon_name(counter), pokemon_name(opponent)
    if duel.margin < 0:
        return (
            f"{ours} loses to {theirs}: {theirs} knocks it out in "
            f"{turns_text(duel.opponent_turns)}, {ours} needs {turn_count(duel.counter_turns)}"
        )
    if duel.margin == 0:
        return f"{ours} draws with {theirs}: each needs {turns_text(duel.counter_turns)}"
    with_move = f" with {move_name(duel.counter_hit)}" if duel.counter_hit else ""
    return f"{ours} knocks out {theirs} in {turns_text(duel.counter_turns)}{with_move}"


def side_sentence(
    attacker: Pokemon, defender: Pokemon, hit: Hit | None, turns: int, wins: bool, with_type: bool
) -> str:
    """What one side does to the other, e.g. "Charizard needs 2 turns to knock out
    Garchomp with Outrage: 96 damage against 168 HP." The winner "knocks out"; with
    `with_type` the move's type and multiplier follow its name: "Stone Edge (rock, 4×)"."""
    us, them = pokemon_name(attacker), pokemon_name(defender)
    if hit is None:
        return f"{us} has no move that damages {them}."
    if wins:
        verb = f"{us} knocks out {them} in {turns_text(turns)}"
    else:
        verb = f"{us} needs {turns_text(turns)} to knock out {them}"
    move = move_name(hit)
    if with_type:
        move += f" ({hit.move.type}, {WRITTEN_MULTIPLIERS[hit.quarters]})"
    chance = accuracy(hit.move)
    accurate = f", {chance}% accurate," if chance < 100 else ""
    return (
        f"{verb} with {move}: {hit.damage} damage{accurate} against {hp_at_level_50(defender)} HP."
    )


def speed_sentence(duel: Duel, counter: Pokemon, opponent: Pokemon) -> str:
    if duel.speed_edge == 0:
        return "They are equally fast, so neither strikes first."
    faster = counter if duel.speed_edge > 0 else opponent
    return f"{pokemon_name(faster)} is faster, so it strikes first."


def reason(duel: Duel, counter: Pokemon, opponent: Pokemon) -> str:
    """The "Why?" text: each side's best move and its numbers, then who strikes first.

    The counter's move gives its type and multiplier, because that is what makes it a
    counter.
    """
    ours = side_sentence(
        counter, opponent, duel.counter_hit, duel.counter_turns, duel.margin > 0, True
    )
    theirs = side_sentence(
        opponent, counter, duel.opponent_hit, duel.opponent_turns, duel.margin < 0, False
    )
    return f"{ours} {theirs} {speed_sentence(duel, counter, opponent)}"
