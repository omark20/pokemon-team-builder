"""Shared fixtures: a real Postgres test database, emptied before every test.

The test database is `pokemon_test` on the server named by DATABASE_URL (the local
Docker Postgres). Tests use their own tokens, never the ones in .env.
"""

import os
from collections.abc import Iterator

import psycopg
import pytest
from fake_pokeapi import FakePokeApi
from fastapi.testclient import TestClient
from psycopg.conninfo import make_conninfo

from app import db, pokemon_list
from app.config import Settings
from app.main import create_app

TEST_DB = "pokemon_test"
SCAN_TOKEN = "scan-token-for-tests"
ADMIN_TOKEN = "admin-token-for-tests"


@pytest.fixture(scope="session")
def test_database_url() -> str:
    """Address of the test database, created on first use."""
    server_url = os.environ["DATABASE_URL"]
    with psycopg.connect(server_url, autocommit=True) as conn:
        exists = conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (TEST_DB,))
        if exists.fetchone() is None:
            conn.execute(f"CREATE DATABASE {TEST_DB}")
    return make_conninfo(server_url, dbname=TEST_DB)


@pytest.fixture
def database_url(test_database_url: str) -> str:
    """The test database with every table dropped; the app recreates them at start-up."""
    with psycopg.connect(test_database_url, autocommit=True) as conn:
        conn.execute("DROP SCHEMA public CASCADE")
        conn.execute("CREATE SCHEMA public")
    return test_database_url


@pytest.fixture
def settings(database_url: str) -> Settings:
    return Settings(database_url=database_url, scan_token=SCAN_TOKEN, admin_token=ADMIN_TOKEN)


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    """A client for a freshly started app. https, as the deployed site is."""
    with TestClient(create_app(settings), base_url="https://testserver") as test_client:
        yield test_client


@pytest.fixture
def conn(database_url: str, client: TestClient) -> Iterator[psycopg.Connection]:
    """A direct connection for arranging and inspecting rows, after the schema exists."""
    with psycopg.connect(database_url, autocommit=True) as connection:
        yield connection


@pytest.fixture(autouse=True)
def empty_list_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """The in-memory Pokémon list is process-wide; every test starts without it."""
    monkeypatch.setattr(pokemon_list, "_body", None)


@pytest.fixture
def connect_calls(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Every database connection the app opens from now on, recorded and then opened."""
    calls: list[str] = []
    real_connect = db.connect

    def counting_connect(database_url: str) -> psycopg.Connection:
        calls.append(database_url)
        return real_connect(database_url)

    monkeypatch.setattr(db, "connect", counting_connect)
    return calls


@pytest.fixture
def source() -> FakePokeApi:
    """A fake PokéAPI answering from samples/; tests change its answers."""
    return FakePokeApi()
