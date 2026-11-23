"""The public Pokémon list: what it returns, and that it is served from memory.

Expected values are read off samples/pokemon_6_charizard_dual_type.json.
"""

import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

import psycopg
import pytest
from conftest import ADMIN_TOKEN
from fake_pokeapi import FakePokeApi, pokemon_path, run_fake_scan
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import pokemon_list

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
    assert len(entries) == 21
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


def test_the_list_shows_a_demo_value_after_its_scan_and_the_original_after_reset(
    client: TestClient, conn: psycopg.Connection, source: FakePokeApi
) -> None:
    run_fake_scan(conn, source)
    by_id(client)
    admin = {"Authorization": f"Bearer {ADMIN_TOKEN}"}
    client.put("/api/admin/demo/overrides", headers=admin, json={"pokemon": {"6": {"attack": 94}}})
    run_fake_scan(conn, source, pokemon_ids=[6])
    assert by_id(client)[6]["stats"][1] == 94
    client.post("/api/admin/demo/reset", headers=admin)
    assert by_id(client)[6]["stats"][1] == 84


def test_waiting_for_a_connection_does_not_make_other_list_requests_queue() -> None:
    """With the copy empty, one request stuck waiting for a connection must not hold back
    another, here one whose connection fails at once."""
    waiting, release = threading.Event(), threading.Event()

    @contextmanager
    def slow_connection() -> Iterator[None]:
        waiting.set()
        release.wait(timeout=10)
        raise HTTPException(503)
        yield

    @contextmanager
    def failing_connection() -> Iterator[None]:
        raise HTTPException(503)
        yield

    def fails(connect: Callable[[], Any]) -> None:
        with pytest.raises(HTTPException):
            pokemon_list.get(connect)

    stuck = threading.Thread(target=fails, args=(slow_connection,))
    stuck.start()
    assert waiting.wait(timeout=5)
    other = threading.Thread(target=fails, args=(failing_connection,))
    other.start()
    other.join(timeout=5)
    finished_while_the_other_waited = not other.is_alive()
    release.set()
    stuck.join(timeout=10)
    assert finished_while_the_other_waited
