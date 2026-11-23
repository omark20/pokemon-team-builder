"""The counter-team steps of `make smoke`, and the two that read the local database itself.

The expected counter teams were worked out by a separately written build on a live scan,
never by the code under test. If PokéAPI's data changes, a figure here can stop holding;
that is a reason to look, not to copy the new answer in.
"""

import math
import os
from typing import Any

import psycopg
from smoke_steps import DEFAULT_FORMS, LISTED, TEAM_A, Smoke, check

MOVES_NOT_LOADED = "The moves are not loaded yet"
POOL_WITHOUT_LEGENDARIES = 931  # the 94 flagged default forms left out (samples/README.md, fact 20)
# Visitor A (Charizard, Blastoise, Venusaur), slot by slot: the counter's id and name, its
# move and turns, the opponent's move back and turns, and how the duel ends.
DUELS_A = [
    (142, "aerodactyl", "stone-edge", 1, "outrage", 3, "wins"),
    (490, "manaphy", "energy-ball", 2, "outrage", 4, "wins"),
    (823, "corviknight", "brave-bird", 1, "petal-dance", 7, "wins"),
]
# With legendary and mythical Pokémon left out, Starmie takes Manaphy's place.
DUELS_A_NO_LEGENDARIES = [
    DUELS_A[0],
    (121, "starmie", "thunderbolt", 2, "outrage", 3, "wins"),
    DUELS_A[2],
]
# Charizard can learn Focus Blast (samples/pokemon_6_charizard_dual_type.json), which counts.
FOCUS_BLAST = {"id": 411, "name": "focus-blast"}
# The stored chart's cells for a move's type on each of a Pokémon's types.
CELLS_QUERY = (
    "SELECT e.multiplier FROM moves m JOIN type_effectiveness e ON e.attacker = m.type"
    " JOIN pokemon p ON e.defender = ANY (p.types) WHERE m.name = %s AND p.id = %s"
)


def _database(query: str, params: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
    """One statement on the local development database the app is running against."""
    with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True) as conn:
        cursor = conn.execute(query, params)
        return cursor.fetchall() if cursor.description else []


def counter_before_moves(smoke: Smoke) -> None:
    """With no duel data stored, as before the first scan, a counter team is 503."""
    _database("DELETE FROM duel_data")  # step 1's full scan stores it again
    smoke.new_team("D", "Smoke D", [6])
    answer = smoke.as_visitor("D", "GET", f"/api/teams/{smoke.teams['D']}/counter")
    seen = (answer.status_code, answer.json().get("detail"))
    check(seen == (503, MOVES_NOT_LOADED), f"503 {MOVES_NOT_LOADED!r}", seen)


def duel_data_complete(smoke: Smoke) -> None:
    """After the scan every stored Pokémon has its four, and every field Pokémon a baseline."""
    [counts] = _database(
        "SELECT count(*), count(d.pokemon_id),"
        " count(*) FILTER (WHERE p.is_default AND p.removed_at IS NULL),"
        " count(d.baseline) FILTER (WHERE p.is_default AND p.removed_at IS NULL),"
        " count(d.baseline)"
        " FROM pokemon p LEFT JOIN duel_data d ON d.pokemon_id = p.id"
    )
    expected = (LISTED, LISTED, DEFAULT_FORMS, DEFAULT_FORMS, DEFAULT_FORMS)
    check(counts == expected, f"rows, field and baselines {expected}", counts)


def counter_a(smoke: Smoke) -> None:
    body = _counter(smoke, {})
    _check_duels(body, DUELS_A)
    seen = (body["pool_size"], body["weakness_rule"])
    check(seen == (DEFAULT_FORMS, "kept"), "pool 1025, the shared-weakness rule kept", seen)


def legendary_filter(smoke: Smoke) -> None:
    body = _counter(smoke, {"leave_out_legendary": "true"})
    _check_duels(body, DUELS_A_NO_LEGENDARIES)
    seen = (body["pool_size"], body["legendary_left_out"])
    check(seen == (POOL_WITHOUT_LEGENDARIES, True), "pool 931, legendary_left_out", seen)


def chosen_move(smoke: Smoke) -> None:
    """Charizard, in A's first slot, given only Focus Blast fights with it; then A's team is
    set back to the default four."""
    path = f"/api/teams/{smoke.teams['A']}/members"
    body = {"pokemon_ids": TEAM_A, "move_ids": [[FOCUS_BLAST["id"]], None, None]}
    saved = smoke.as_visitor("A", "PUT", path, json=body)
    check(saved.status_code == 200, "200 saving a chosen move", saved.status_code)
    teams = smoke.as_visitor("A", "GET", "/api/teams").json()
    check(teams[0]["moves"] == [[FOCUS_BLAST], None, None], "the choice back, named", teams[0])
    answer = _counter(smoke, {})
    carried = answer["opponent_moves"][0]["moves"]
    check(carried == ["focus-blast"], "Charizard carrying Focus Blast only", carried)
    # Its move back is Focus Blast, or none if Focus Blast does nothing to the new counter.
    move_back = answer["picks"][0]["opponent"]["move"]
    check(move_back in ("focus-blast", None), "Charizard's move back Focus Blast", move_back)
    restored = smoke.as_visitor("A", "PUT", path, json={"pokemon_ids": TEAM_A})
    status = restored.status_code
    check(status == 200, "200 setting A back to the default four", status)


def another_team(smoke: Smoke) -> None:
    """Leaving out A's first counter team gives a whole team of others."""
    shown = [duel[0] for duel in DUELS_A]
    body = _counter(smoke, {"leave_out": [str(pokemon_id) for pokemon_id in shown]})
    picked = [pick["counter"]["id"] for pick in body["picks"]]
    seen = (len(picked), set(picked) & set(shown), body["pool_size"])
    expected = (len(TEAM_A), set(), DEFAULT_FORMS - len(shown))
    check(seen == expected, f"three other counters from a pool of 1022 {expected}", seen)
    print(f"smoke: the second team is {[p['counter']['name'] for p in body['picks']]}", flush=True)


def _counter(smoke: Smoke, params: dict[str, Any]) -> dict[str, Any]:
    path = f"/api/teams/{smoke.teams['A']}/counter"
    answer = smoke.as_visitor("A", "GET", path, params=params)
    check(answer.status_code == 200, "200 for A's counter team", answer.status_code)
    body: dict[str, Any] = answer.json()
    check(body["size"] == len(TEAM_A), f"{len(TEAM_A)} slots", body["size"])
    return body


def _check_duels(body: dict[str, Any], expected: list[tuple[Any, ...]]) -> None:
    """Each pick's duel as expected, and each counter's move 2× or more on its opponent,
    worked out from the stored chart and the move's stored type."""
    seen = [
        (
            pick["counter"]["id"],
            pick["counter"]["name"],
            pick["counter"]["move"],
            pick["counter"]["turns"],
            pick["opponent"]["move"],
            pick["opponent"]["turns"],
            pick["outcome"],
        )
        for pick in body["picks"]
    ]
    check(seen == expected, f"duels {expected}", seen)
    hits = [
        math.prod(
            cell for (cell,) in _database(CELLS_QUERY, (p["counter"]["move"], p["opponent"]["id"]))
        )
        for p in body["picks"]
    ]
    check(all(hit >= 2 for hit in hits), "every counter's move 2× or more", hits)
