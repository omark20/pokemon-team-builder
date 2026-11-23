"""The counter-team endpoint: wiring stored teams, Pokémon, moves and chart to the core.

The core itself (app/domain/counter.py) is tested in test_counter.py. The stored
Pokémon are the 21 captured in samples/; 18 of them are default forms (ids below 10000),
so the field, and the candidate pool, has 18.
"""

import json
from dataclasses import asdict
from typing import Any

import psycopg
import pytest
from fake_pokeapi import FakePokeApi, run_fake_scan, species_path
from fastapi.testclient import TestClient

from app import duel_store
from app.domain.counter import build_counter_team, candidate_pool
from app.routes import counter

TEAMS = "/api/teams"


@pytest.fixture
def visitor(client: TestClient, conn: psycopg.Connection, source: FakePokeApi) -> TestClient:
    run_fake_scan(conn, source)
    return client


def team_with(client: TestClient, pokemon_ids: list[int]) -> int:
    team_id: int = client.post(TEAMS, json={"name": "Team 1"}).json()["id"]
    client.put(f"{TEAMS}/{team_id}/members", json={"pokemon_ids": pokemon_ids})
    return team_id


ANSWER_KEYS = {
    "size",
    "picks",
    "grid",
    "opponent_moves",
    "weakness_counts",
    "weakness_rule",
    "no_candidate_for",
}


def test_a_saved_team_of_three_gets_one_counter_per_slot(visitor: TestClient) -> None:
    team_id = team_with(visitor, [6, 9, 3])
    body = visitor.get(f"{TEAMS}/{team_id}/counter").json()
    assert set(body) == ANSWER_KEYS | {"pool_size", "legendary_left_out"}
    assert (body["size"], body["pool_size"]) == (3, 18)
    assert [pick["opponent"]["id"] for pick in body["picks"]] == [6, 9, 3]
    assert len({pick["counter"]["id"] for pick in body["picks"]}) == 3
    assert [len(row) for row in body["grid"]] == [3, 3, 3]
    outcomes = {pick["outcome"] for pick in body["picks"]} | {
        cell["outcome"] for row in body["grid"] for cell in row
    }
    assert outcomes <= {"wins", "draws with", "loses to"}


def test_an_empty_team_gets_a_message_instead_of_counters(visitor: TestClient) -> None:
    team_id = team_with(visitor, [])
    body = visitor.get(f"{TEAMS}/{team_id}/counter").json()
    assert (body["size"], body["picks"]) == (0, [])
    assert body["message"]


def test_another_visitors_team_is_404(visitor: TestClient) -> None:
    team_id = team_with(visitor, [6])
    other = TestClient(visitor.app, base_url="https://testserver")
    other.post(TEAMS, json={"name": "Theirs"})
    assert other.get(f"{TEAMS}/{team_id}/counter").status_code == 404


@pytest.mark.parametrize(
    ("table", "detail"),
    [("type_effectiveness", counter.CHART_NOT_LOADED), ("duel_data", counter.MOVES_NOT_LOADED)],
)
def test_before_a_scan_has_stored_the_chart_or_the_duel_data_it_is_503(
    visitor: TestClient, conn: psycopg.Connection, table: str, detail: str
) -> None:
    team_id = team_with(visitor, [6])
    conn.execute(f"DELETE FROM {table}")
    answer = visitor.get(f"{TEAMS}/{team_id}/counter")
    assert (answer.status_code, answer.json()["detail"]) == (503, detail)


def test_a_pokemon_without_a_stored_baseline_is_never_a_counter(
    visitor: TestClient, conn: psycopg.Connection
) -> None:
    team_id = team_with(visitor, [6, 9, 3])
    first = visitor.get(f"{TEAMS}/{team_id}/counter").json()
    picked = first["picks"][0]["counter"]["id"]
    conn.execute("UPDATE duel_data SET baseline = NULL WHERE pokemon_id = %s", (picked,))
    again = visitor.get(f"{TEAMS}/{team_id}/counter").json()
    assert again["pool_size"] == 17
    assert picked not in [pick["counter"]["id"] for pick in again["picks"]]


def test_an_opponent_fights_with_its_stored_four_none_without_a_row(
    visitor: TestClient, conn: psycopg.Connection
) -> None:
    team_id = team_with(visitor, [6, 10195])
    four = conn.execute("SELECT move_ids FROM duel_data WHERE pokemon_id = 6").fetchone()
    names = dict(conn.execute("SELECT id, name FROM moves"))
    moves = visitor.get(f"{TEAMS}/{team_id}/counter").json()["opponent_moves"]
    assert four is not None and moves[0]["moves"] == [names[move_id] for move_id in four[0]]
    assert (moves[1]["moves"], moves[1]["moves_listed"]) == ([], False)  # PokéAPI lists none
    conn.execute("DELETE FROM duel_data WHERE pokemon_id = 6")  # stored after the last refresh
    moves = visitor.get(f"{TEAMS}/{team_id}/counter").json()["opponent_moves"]
    assert (moves[0]["moves"], moves[0]["moves_listed"]) == ([], True)


def test_with_both_counter_places_taken_a_third_is_503_and_other_reads_answer(
    visitor: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    team_id = team_with(visitor, [6])
    monkeypatch.setattr(counter, "COUNTER_WAIT_SECONDS", 0.01)  # no need to wait two seconds
    places = visitor.app.state.counter_places
    assert places.acquire(blocking=False) and places.acquire(blocking=False)
    try:
        refused = visitor.get(f"{TEAMS}/{team_id}/counter")
        assert (refused.status_code, refused.headers["retry-after"]) == (503, "1")
        assert visitor.get("/api/scan/status").status_code == 200
    finally:
        places.release()
        places.release()
    assert visitor.get(f"{TEAMS}/{team_id}/counter").status_code == 200


def test_leaving_out_legendaries_removes_them_from_the_pool_and_the_picks(
    client: TestClient, conn: psycopg.Connection, source: FakePokeApi
) -> None:
    source.answers[species_path(248)]["is_legendary"] = True  # Tyranitar, for this test only
    run_fake_scan(conn, source)
    team_id = team_with(client, [6, 9, 3])
    body = client.get(f"{TEAMS}/{team_id}/counter", params={"leave_out_legendary": "true"}).json()
    assert (body["legendary_left_out"], body["pool_size"]) == (True, 17)
    picks = [pick["counter"]["id"] for pick in body["picks"]]
    assert len(picks) == 3 and 248 not in picks
    default = client.get(f"{TEAMS}/{team_id}/counter").json()
    assert (default["legendary_left_out"], default["pool_size"]) == (False, 18)


def test_leaving_out_legendaries_before_the_flags_are_read_is_503(
    visitor: TestClient, conn: psycopg.Connection
) -> None:
    team_id = team_with(visitor, [6])
    conn.execute("UPDATE pokemon SET is_legendary = NULL, is_mythical = NULL")
    filtered = visitor.get(f"{TEAMS}/{team_id}/counter", params={"leave_out_legendary": "true"})
    assert (filtered.status_code, filtered.json()["detail"]) == (503, counter.FLAGS_NOT_LOADED)
    assert visitor.get(f"{TEAMS}/{team_id}/counter").status_code == 200


def test_the_field_size_passed_to_the_core_is_the_number_of_stored_baselines(
    visitor: TestClient, conn: psycopg.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    sizes: list[int] = []
    build = counter.build_counter_team

    def recording(*arguments: Any) -> Any:
        sizes.append(arguments[3])
        return build(*arguments)

    monkeypatch.setattr(counter, "build_counter_team", recording)
    team_id = team_with(visitor, [6])
    conn.execute("UPDATE duel_data SET baseline = NULL WHERE pokemon_id = 3")
    assert visitor.get(f"{TEAMS}/{team_id}/counter").status_code == 200
    assert sizes == [17]  # 18 field Pokémon, one without a baseline; 21 stored in all


@pytest.mark.parametrize(
    "leave_out",
    [[str(i) for i in range(1, 62)], ["six"], ["0"], ["-1"], ["1.5"], ["6", "6"]],
    ids=["61-ids", "not-a-number", "zero", "negative", "fraction", "repeated"],
)
def test_a_leave_out_list_that_breaks_a_rule_is_422(
    visitor: TestClient, leave_out: list[str]
) -> None:
    team_id = team_with(visitor, [6])
    answer = visitor.get(f"{TEAMS}/{team_id}/counter", params={"leave_out": leave_out})
    assert answer.status_code == 422


def test_leaving_out_the_first_team_gives_the_best_team_of_the_smaller_pool(
    visitor: TestClient, conn: psycopg.Connection
) -> None:
    team_id = team_with(visitor, [6, 3])  # each has candidates that hit it for 2×
    first = visitor.get(f"{TEAMS}/{team_id}/counter").json()
    shown = [pick["counter"]["id"] for pick in first["picks"]]
    params = {"leave_out": [str(i) for i in shown]}
    second = visitor.get(f"{TEAMS}/{team_id}/counter", params=params).json()
    fighters, chart = duel_store.load_fighters(conn), duel_store.load_chart(conn)
    assert fighters is not None and chart is not None
    smaller = [p for p in candidate_pool(fighters.field) if p.id not in shown]
    opponents = [fighters.by_id[6], fighters.by_id[3]]
    built = build_counter_team(opponents, smaller, chart, len(fighters.field), may_waive=False)
    expected = asdict(built)
    assert {key: second[key] for key in expected} == json.loads(json.dumps(expected))
    picked = [pick["counter"]["id"] for pick in second["picks"]]
    assert len(picked) == 2 and not set(picked) & set(shown)
    assert second["pool_size"] == 18 - 2


def test_leaving_out_no_candidate_changes_nothing(visitor: TestClient) -> None:
    team_id = team_with(visitor, [6, 9, 3])
    plain = visitor.get(f"{TEAMS}/{team_id}/counter").json()
    params = {"leave_out": ["10034", "2147483647"]}  # a special form, and no Pokémon at all
    assert visitor.get(f"{TEAMS}/{team_id}/counter", params=params).json() == plain


def test_with_anything_left_out_a_slot_nothing_can_hit_for_2x_gives_no_team(
    visitor: TestClient,
) -> None:
    """With only the 17 captured moves stored, nothing hits Blastoise for 2×: the rule is
    waived for it alone, and never once a candidate has been left out."""
    team_id = team_with(visitor, [9])
    plain = visitor.get(f"{TEAMS}/{team_id}/counter").json()
    assert (len(plain["picks"]), plain["no_candidate_for"]) == (1, None)
    params = {"leave_out": [str(plain["picks"][0]["counter"]["id"])]}
    out = visitor.get(f"{TEAMS}/{team_id}/counter", params=params).json()
    assert (out["picks"], out["grid"], out["no_candidate_for"]) == ([], [], "blastoise")
