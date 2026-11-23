"""Choosing a team member's moves: saving them, reading them back, the moves a Pokémon
may be given, and the counter team fighting with them.

The stored data is the fake PokéAPI's: the 21 captured Pokémon and the 17 captured
moves. Charizard (6) can learn ten of those moves; of them flamethrower (53),
earthquake (89), swift (129), focus-blast (411) and scale-shot (799) count in a duel,
hyper-beam (63) does not (it must recharge), and it cannot learn stone-edge (444).
"""

import json
from dataclasses import asdict, replace
from typing import Any

import psycopg
import pytest
from captured import SAMPLES
from fake_pokeapi import FakePokeApi, run_fake_scan
from fastapi.testclient import TestClient

from app import duel_store
from app.domain.counter import build_counter_team, candidate_pool
from app.domain.move_rules import counts
from app.domain.moves import parse_move, parse_move_ids
from app.routes import teams

TEAMS = "/api/teams"
CHARIZARD, PIKACHU, GIGANTAMAX = 6, 25, 10195
FLAMETHROWER, HYPER_BEAM, STONE_EDGE, FOCUS_BLAST = 53, 63, 444, 411


@pytest.fixture
def visitor(client: TestClient, conn: psycopg.Connection, source: FakePokeApi) -> TestClient:
    run_fake_scan(conn, source)
    return client


def new_team(client: TestClient) -> int:
    team_id: int = client.post(TEAMS, json={"name": "Team"}).json()["id"]
    return team_id


def put(client: TestClient, team_id: int, body: dict[str, Any]) -> Any:
    return client.put(f"{TEAMS}/{team_id}/members", json=body)


@pytest.mark.parametrize(
    ("move_ids", "detail"),
    [
        ([[FLAMETHROWER, 89, 129, FOCUS_BLAST, 799]], None),  # a fifth move
        ([[FLAMETHROWER, FLAMETHROWER]], None),  # a repeat within a slot
        ([[]], None),  # chosen, but nothing chosen
        ([["53"]], None),  # strict: a move ID sent as text
        ([None, None], None),  # one entry too many for one Pokémon
        ([[STONE_EDGE]], teams.NOT_LEARNABLE),
        ([[HYPER_BEAM]], teams.NOT_COUNTED),
    ],
    ids=["fifth", "repeat", "empty", "text", "wrong-length", "not-learnable", "not-counted"],
)
def test_a_choice_that_breaks_a_rule_is_refused_and_nothing_is_stored(
    visitor: TestClient, conn: psycopg.Connection, move_ids: list[Any], detail: str | None
) -> None:
    team_id = new_team(visitor)
    put(visitor, team_id, {"pokemon_ids": [CHARIZARD]})
    refused = put(visitor, team_id, {"pokemon_ids": [CHARIZARD], "move_ids": move_ids})
    assert refused.status_code == 422
    if detail is not None:
        assert refused.json()["detail"] == detail
    stored = conn.execute("SELECT move_ids FROM team_members WHERE team_id = %s", (team_id,))
    assert stored.fetchall() == [(None,)]


def test_another_visitors_team_cannot_be_given_moves(visitor: TestClient) -> None:
    team_id = new_team(visitor)
    other = TestClient(visitor.app, base_url="https://testserver")
    other.post(TEAMS, json={"name": "Theirs"})
    body = {"pokemon_ids": [CHARIZARD], "move_ids": [[FLAMETHROWER]]}
    assert put(other, team_id, body).status_code == 404


def test_choices_belong_to_slots_and_come_back_named_in_order(visitor: TestClient) -> None:
    team_id = new_team(visitor)
    chosen = [[FOCUS_BLAST, FLAMETHROWER], None]
    saved = put(visitor, team_id, {"pokemon_ids": [CHARIZARD, CHARIZARD], "move_ids": chosen})
    named = [
        {"id": FOCUS_BLAST, "name": "focus-blast"},
        {"id": FLAMETHROWER, "name": "flamethrower"},
    ]
    assert saved.json()["moves"] == [named, None]
    swapped = {"pokemon_ids": [CHARIZARD, CHARIZARD], "move_ids": chosen[::-1]}
    assert put(visitor, team_id, swapped).json()["moves"] == [None, named]
    assert visitor.get(TEAMS).json()[0]["moves"] == [None, named]
    without = put(visitor, team_id, {"pokemon_ids": [CHARIZARD, CHARIZARD]})
    assert without.json()["moves"] == [None, None]  # left out: every slot its usual four


def expected_moves(pokemon_file: str) -> list[int]:
    """The captured moves this captured Pokémon can learn that count, smallest ID first."""
    learnable = set(parse_move_ids(json.loads((SAMPLES / pokemon_file).read_text())))
    moves = [parse_move(json.loads(p.read_text())) for p in SAMPLES.glob("move_[0-9]*_*.json")]
    return sorted(move.id for move in moves if move.id in learnable and counts(move))


def test_a_pokemons_moves_are_those_it_can_learn_that_count_and_its_usual_four(
    visitor: TestClient, conn: psycopg.Connection
) -> None:
    body = visitor.get(f"/api/pokemon/{CHARIZARD}/moves").json()
    assert [move["id"] for move in body["moves"]] == expected_moves(
        "pokemon_6_charizard_dual_type.json"
    )
    assert body["moves"][0] == {
        "id": FLAMETHROWER,
        "name": "flamethrower",
        "type": "fire",
        "damage_class": "special",
        "power": 90,
        "accuracy": 100,
    }
    usual = conn.execute("SELECT move_ids FROM duel_data WHERE pokemon_id = 6").fetchone()
    assert usual is not None and (body["usual"], body["moves_listed"]) == (usual[0], True)
    gigantamax = visitor.get(f"/api/pokemon/{GIGANTAMAX}/moves").json()
    assert gigantamax == {"moves": [], "usual": [], "moves_listed": False}


def test_moves_of_an_unknown_pokemon_are_404_and_before_a_scan_503(
    visitor: TestClient, conn: psycopg.Connection
) -> None:
    assert visitor.get("/api/pokemon/7/moves").status_code == 404
    conn.execute("DELETE FROM pokemon_moves WHERE pokemon_id = %s", (PIKACHU,))
    assert visitor.get(f"/api/pokemon/{PIKACHU}/moves").status_code == 503


def counter(client: TestClient, team_id: int) -> dict[str, Any]:
    body: dict[str, Any] = client.get(f"{TEAMS}/{team_id}/counter").json()
    return body


def test_an_opponent_with_chosen_moves_fights_with_them(
    visitor: TestClient, conn: psycopg.Connection
) -> None:
    """The route's answer is the core's own answer for Charizard carrying only Focus Blast."""
    team_id = new_team(visitor)
    put(visitor, team_id, {"pokemon_ids": [CHARIZARD], "move_ids": [[FOCUS_BLAST]]})
    answer = counter(visitor, team_id)
    fighters = duel_store.load_fighters(conn)
    chart = duel_store.load_chart(conn)
    assert fighters is not None and chart is not None
    focus_blast = duel_store.load_moves_named(conn, [FOCUS_BLAST])[FOCUS_BLAST]
    opponent = replace(fighters.by_id[CHARIZARD], moves=(focus_blast,))
    pool = candidate_pool(fighters.field)
    expected = asdict(build_counter_team([opponent], pool, chart, len(fighters.field)))
    assert {key: answer[key] for key in expected} == json.loads(json.dumps(expected))
    assert answer["opponent_moves"][0]["moves"] == ["focus-blast"]
    put(visitor, team_id, {"pokemon_ids": [CHARIZARD]})
    assert counter(visitor, team_id)["picks"] != answer["picks"]  # the choice made a difference


def test_a_chosen_move_no_longer_listed_is_left_out_and_then_the_usual_four(
    visitor: TestClient, conn: psycopg.Connection
) -> None:
    team_id = new_team(visitor)
    put(visitor, team_id, {"pokemon_ids": [CHARIZARD], "move_ids": [[FOCUS_BLAST, FLAMETHROWER]]})
    drop = "UPDATE pokemon_moves SET move_ids = array_remove(move_ids, %s) WHERE pokemon_id = 6"
    conn.execute(drop, (FOCUS_BLAST,))
    assert counter(visitor, team_id)["opponent_moves"][0]["moves"] == ["flamethrower"]
    conn.execute(drop, (FLAMETHROWER,))  # now none of the choice is usable: the usual four
    usual = conn.execute("SELECT move_ids FROM duel_data WHERE pokemon_id = 6").fetchone()
    names = dict(conn.execute("SELECT id, name FROM moves"))
    assert usual is not None
    expected = [names[i] for i in usual[0]]
    assert counter(visitor, team_id)["opponent_moves"][0]["moves"] == expected
    stored = conn.execute("SELECT move_ids FROM team_members WHERE team_id = %s", (team_id,))
    assert stored.fetchone() == ([FOCUS_BLAST, FLAMETHROWER],)  # the choice is not rewritten
