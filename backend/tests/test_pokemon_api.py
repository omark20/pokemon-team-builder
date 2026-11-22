"""The public Pokémon list: what it returns, and that it is served from memory.

Expected values are read off samples/pokemon_6_charizard_dual_type.json.
"""

import psycopg
from fake_pokeapi import FakePokeApi, pokemon_path, run_fake_scan
from fastapi.testclient import TestClient

CHARIZARD_ENTRY = {
    "id": 6,
    "name": "charizard",
    "is_default": True,
    "types": ["fire", "flying"],
    "stats": [78, 84, 78, 109, 85, 100],
    "sprite_url": "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/6.png",
    "removed": False,
}


def by_id(client: TestClient) -> dict[int, dict[str, object]]:
    return {entry["id"]: entry for entry in client.get("/api/pokemon").json()}


def test_list_holds_every_stored_row(
    client: TestClient, conn: psycopg.Connection, source: FakePokeApi
) -> None:
    run_fake_scan(conn, source)
    conn.execute("UPDATE pokemon SET removed_at = now() WHERE id = 25")
    response = client.get("/api/pokemon")
    assert response.headers["content-encoding"] == "gzip"
    entries = {entry["id"]: entry for entry in response.json()}
    assert len(entries) == 14
    assert entries[6] == CHARIZARD_ENTRY
    assert entries[10264]["sprite_url"] is None
    assert entries[25]["removed"] is True


def test_a_second_request_opens_no_database_connection(
    client: TestClient, conn: psycopg.Connection, source: FakePokeApi, connect_calls: list[str]
) -> None:
    run_fake_scan(conn, source)
    first = client.get("/api/pokemon").content
    connect_calls.clear()
    assert client.get("/api/pokemon").content == first
    assert connect_calls == []


def test_a_scan_that_records_a_change_shows_in_the_next_response(
    client: TestClient, conn: psycopg.Connection, source: FakePokeApi
) -> None:
    run_fake_scan(conn, source)
    by_id(client)
    source.answers[pokemon_path(6)]["stats"][1]["base_stat"] = 94
    run_fake_scan(conn, source)
    assert by_id(client)[6]["stats"] == [78, 94, 78, 109, 85, 100]


def test_a_scan_that_changes_nothing_keeps_the_copy_in_memory(
    client: TestClient, conn: psycopg.Connection, source: FakePokeApi, connect_calls: list[str]
) -> None:
    run_fake_scan(conn, source)
    by_id(client)
    run_fake_scan(conn, source)
    connect_calls.clear()
    by_id(client)
    assert connect_calls == []
