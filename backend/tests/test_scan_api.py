"""The scan trigger and the public run history (scan_runs)."""

import psycopg
import pytest
from conftest import SCAN_TOKEN
from fastapi.testclient import TestClient

from app import scan

SCAN = "/api/admin/scan"
BEARER = {"Authorization": f"Bearer {SCAN_TOKEN}"}


@pytest.fixture
def started_scans(monkeypatch: pytest.MonkeyPatch) -> list[tuple[object, ...]]:
    """Scans the trigger hands to the background, recorded instead of run against PokéAPI."""
    started: list[tuple[object, ...]] = []
    monkeypatch.setattr(scan, "scan_with_pokeapi", lambda *args: started.append(args))
    return started


@pytest.mark.parametrize(
    ("body", "scope", "pokemon_ids"),
    [(None, "full", None), ({"pokemon_ids": [6, 25]}, "subset", [6, 25])],
)
def test_trigger_with_token_starts_a_run(
    client: TestClient,
    conn: psycopg.Connection,
    started_scans: list[tuple[object, ...]],
    body: dict[str, list[int]] | None,
    scope: str,
    pokemon_ids: list[int] | None,
) -> None:
    response = client.post(SCAN, headers=BEARER, json=body)
    assert response.status_code == 202
    run_id = response.json()["run_id"]
    row = conn.execute("SELECT status, scope FROM scan_runs WHERE id = %s", (run_id,))
    assert row.fetchone() == ("running", scope)
    [(_, started_run_id, started_ids)] = started_scans
    assert (started_run_id, started_ids) == (run_id, pokemon_ids)


@pytest.mark.parametrize(
    "body",
    [
        {"pokemon_ids": list(range(1, 52))},
        {"pokemon_ids": []},
        {"pokemon_ids": [0]},
        {"pokemon_ids": [2_147_483_648]},
        {"pokemon_ids": ["six"]},
        {"pokemon_ids": [6], "user_id": 1},
    ],
)
def test_trigger_rejects_bad_bodies(client: TestClient, body: dict[str, object]) -> None:
    assert client.post(SCAN, headers=BEARER, json=body).status_code == 422


def test_trigger_while_a_run_is_in_progress_is_409(
    client: TestClient, conn: psycopg.Connection
) -> None:
    conn.execute("INSERT INTO scan_runs (status, scope) VALUES ('running', 'full')")
    assert client.post(SCAN, headers=BEARER).status_code == 409
    assert conn.execute("SELECT count(*) FROM scan_runs").fetchone() == (1,)


def test_database_allows_only_one_running_row(client: TestClient, conn: psycopg.Connection) -> None:
    conn.execute("INSERT INTO scan_runs (status, scope) VALUES ('running', 'full')")
    with pytest.raises(psycopg.errors.UniqueViolation):
        conn.execute("INSERT INTO scan_runs (status, scope) VALUES ('running', 'subset')")


def test_status_lists_five_newest_runs_with_public_fields_only(
    client: TestClient, conn: psycopg.Connection
) -> None:
    for number in range(7):
        conn.execute(
            "INSERT INTO scan_runs (status, scope, note) VALUES ('ok', 'full', %s)",
            (f"internal {number}",),
        )
    body = client.get("/api/scan/status").json()
    assert body["demo_active"] is False
    assert [run["id"] for run in body["runs"]] == [7, 6, 5, 4, 3]
    expected = {"id", "started_at", "finished_at", "status", "scope", "scanned", "changed"}
    assert set(body["runs"][0]) == expected | {"failed", "started_by"}
    assert "internal" not in str(body)
