"""The counter-team endpoint: wiring stored teams, Pokémon and chart to the counter core.

The search itself is tested in test_counter.py. The stored Pokémon are the 14 captured in
samples/; 12 of them are default forms (ids below 10000), so the candidate pool has 12.
"""

import psycopg
import pytest
from fake_pokeapi import FakePokeApi, run_fake_scan
from fastapi.testclient import TestClient

TEAMS = "/api/teams"


@pytest.fixture
def visitor(client: TestClient, conn: psycopg.Connection, source: FakePokeApi) -> TestClient:
    run_fake_scan(conn, source)
    return client


def team_with(client: TestClient, pokemon_ids: list[int]) -> int:
    team_id: int = client.post(TEAMS, json={"name": "Team 1"}).json()["id"]
    client.put(f"{TEAMS}/{team_id}/members", json={"pokemon_ids": pokemon_ids})
    return team_id


def test_a_saved_team_of_three_gets_one_counter_per_slot(visitor: TestClient) -> None:
    team_id = team_with(visitor, [6, 9, 3])
    body = visitor.get(f"{TEAMS}/{team_id}/counter").json()
    assert body["size"] == 3
    assert [pick["opponent"]["id"] for pick in body["picks"]] == [6, 9, 3]
    assert body["pool_size"] == 12
    assert body["stopped_early"] is False


def test_an_empty_team_gets_a_message_instead_of_counters(visitor: TestClient) -> None:
    team_id = team_with(visitor, [])
    body = visitor.get(f"{TEAMS}/{team_id}/counter").json()
    assert (body["size"], body["picks"]) == (0, [])
    assert body["message"]


def test_another_visitors_team_is_404(visitor: TestClient) -> None:
    team_id = team_with(visitor, [6])
    with TestClient(visitor.app, base_url="https://testserver") as other:
        other.post(TEAMS, json={"name": "Theirs"})
        assert other.get(f"{TEAMS}/{team_id}/counter").status_code == 404


def test_an_unloaded_type_chart_is_503(visitor: TestClient, conn: psycopg.Connection) -> None:
    team_id = team_with(visitor, [6])
    conn.execute("DELETE FROM type_effectiveness")
    assert visitor.get(f"{TEAMS}/{team_id}/counter").status_code == 503
