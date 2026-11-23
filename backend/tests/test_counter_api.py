"""The counter-team endpoint: wiring stored teams, Pokémon and chart to the counter search.

The search itself (app/domain/counter.py) is tested in test_counter.py. The stored
Pokémon are the 15 captured in samples/; 12 of them are default forms (ids below 10000),
so the candidate pool has 12.
"""

import psycopg
import pytest
from fake_pokeapi import FakePokeApi, run_fake_scan, species_path
from fastapi.testclient import TestClient

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
    other = TestClient(visitor.app, base_url="https://testserver")
    other.post(TEAMS, json={"name": "Theirs"})
    assert other.get(f"{TEAMS}/{team_id}/counter").status_code == 404


def test_an_unloaded_type_chart_is_503(visitor: TestClient, conn: psycopg.Connection) -> None:
    team_id = team_with(visitor, [6])
    conn.execute("DELETE FROM type_effectiveness")
    assert visitor.get(f"{TEAMS}/{team_id}/counter").status_code == 503


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
    assert (body["legendary_left_out"], body["pool_size"]) == (True, 11)
    picks = [pick["counter"] for pick in body["picks"]]
    assert len(picks) == 3
    assert not any(c["is_legendary"] or c["is_mythical"] for c in picks)
    default = client.get(f"{TEAMS}/{team_id}/counter").json()
    assert (default["legendary_left_out"], default["pool_size"]) == (False, 12)


def test_leaving_out_legendaries_before_the_flags_are_read_is_503(
    visitor: TestClient, conn: psycopg.Connection
) -> None:
    team_id = team_with(visitor, [6])
    conn.execute("UPDATE pokemon SET is_legendary = NULL, is_mythical = NULL")
    filtered = visitor.get(f"{TEAMS}/{team_id}/counter", params={"leave_out_legendary": "true"})
    assert (filtered.status_code, filtered.json()["detail"]) == (503, counter.FLAGS_NOT_LOADED)
    assert visitor.get(f"{TEAMS}/{team_id}/counter").status_code == 200
