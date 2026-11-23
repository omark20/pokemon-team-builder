"""The scan's moves step against a fake PokéAPI built from samples/, on the test database.

The fake lists the 17 captured moves and the 21 captured Pokémon. Expected moves come
from census_all_moves.tsv, read separately from the code under test.
"""

import logging
from typing import Any

import psycopg
import pytest
from fake_pokeapi import (
    MOVE_LIST,
    FakePokeApi,
    census_moves,
    move_path,
    pokemon_path,
    run_fake_scan,
)

from app.pokeapi import UpstreamError

STONE_EDGE, FLAMETHROWER, CHARIZARD, VENUSAUR_GMAX = 444, 53, 6, 10195
CENSUS = census_moves()


def move_rows(conn: psycopg.Connection) -> dict[int, tuple[Any, ...]]:
    rows = conn.execute("SELECT id, name, type, damage_class, power, accuracy, priority FROM moves")
    return {row[0]: tuple(row) for row in rows}


def move_lists(conn: psycopg.Connection) -> dict[int, list[int]]:
    rows = conn.execute("SELECT pokemon_id, move_ids FROM pokemon_moves")
    return {pokemon_id: move_ids for pokemon_id, move_ids in rows}


def run_status(conn: psycopg.Connection, run_id: int) -> tuple[Any, ...] | None:
    return conn.execute(
        "SELECT status, scanned, changed, failed FROM scan_runs WHERE id = %s", (run_id,)
    ).fetchone()


def test_a_full_run_stores_every_listed_move_and_every_move_list_with_no_change(
    conn: psycopg.Connection, source: FakePokeApi
) -> None:
    run_id, status = run_fake_scan(conn, source)
    assert (status, run_status(conn, run_id)) == ("ok", ("ok", 21, 0, 0))
    expected = {move_id: tuple(vars(CENSUS[move_id]).values())[:-1] for move_id in move_rows(conn)}
    assert len(expected) == 17
    assert move_rows(conn) == expected
    texts = dict(conn.execute("SELECT id, short_effect FROM moves WHERE id IN (153, 799, 827)"))
    assert texts == {
        153: "User faints.",
        799: "Boosts the user’s Speed and lowers their Defense by one stage after inflicting"
        " damage two to five times in a row.",  # scale-shot lists this English entry twice
        827: None,  # dire-claw has no English text
    }
    lists = move_lists(conn)
    assert len(lists) == 21
    assert STONE_EDGE in lists[248] and FLAMETHROWER in lists[CHARIZARD]  # Tyranitar, Charizard
    assert lists[VENUSAUR_GMAX] == []  # PokéAPI lists no moves for it
    assert conn.execute("SELECT count(*) FROM changes").fetchone() == (0,)


@pytest.mark.parametrize(
    ("answer", "unread"),
    [
        (UpstreamError("http_503", retryable=True), "reason=http_503"),
        (None, "reason=http_404"),
        ({"id": FLAMETHROWER, "name": "flamethrower"}, "reason=parse_error rule=malformed"),
    ],
    ids=["server-error", "not-found", "garbage-body"],
)
def test_a_move_that_cannot_be_read_keeps_its_stored_row_and_the_run_is_incomplete(
    conn: psycopg.Connection,
    source: FakePokeApi,
    caplog: pytest.LogCaptureFixture,
    answer: object,
    unread: str,
) -> None:
    run_fake_scan(conn, source)
    conn.execute(
        "UPDATE moves SET power = 1, short_effect = 'old' WHERE id IN (%s, %s)",
        (FLAMETHROWER, STONE_EDGE),
    )
    source.answers[move_path(FLAMETHROWER)] = answer
    with caplog.at_level(logging.INFO):
        run_id, status = run_fake_scan(conn, source)
    assert (status, run_status(conn, run_id)) == ("incomplete", ("incomplete", 21, 0, 0))
    rows = move_rows(conn)
    assert len(rows) == 17
    assert rows[FLAMETHROWER][4] == 1  # left as stored, not refreshed, blanked or deleted
    assert rows[STONE_EDGE][4] == 100  # a move that was read is refreshed
    texts = dict(conn.execute("SELECT id, short_effect FROM moves WHERE id IN (53, 444)"))
    assert texts == {FLAMETHROWER: "old", STONE_EDGE: "Has an increased chance for a critical hit."}
    expected = f"move_unread run_id={run_id} move_id={FLAMETHROWER} {unread}"
    assert [line for line in caplog.messages if "move_unread" in line] == [expected]


def test_a_move_list_that_cannot_be_read_skips_the_step_and_the_pokemon_still_run(
    conn: psycopg.Connection, source: FakePokeApi, caplog: pytest.LogCaptureFixture
) -> None:
    run_fake_scan(conn, source)
    stored = move_rows(conn)
    source.answers[MOVE_LIST] = UpstreamError("timeout", retryable=True)
    source.requested.clear()
    with caplog.at_level(logging.INFO):
        run_id, status = run_fake_scan(conn, source)
    assert (status, run_status(conn, run_id)) == ("incomplete", ("incomplete", 21, 0, 0))
    assert move_rows(conn) == stored
    assert {path for path in source.requested if path.startswith("move")} == {MOVE_LIST}
    expected = f"move_list_rejected run_id={run_id} reason=timeout"
    assert [line for line in caplog.messages if "move_list_rejected" in line] == [expected]


def test_a_pokemon_whose_move_list_breaks_a_rule_keeps_its_stored_list_and_counts_failed(
    conn: psycopg.Connection, source: FakePokeApi, caplog: pytest.LogCaptureFixture
) -> None:
    run_fake_scan(conn, source)
    stored = move_lists(conn)[CHARIZARD]
    charizard = source.answers[pokemon_path(CHARIZARD)]
    charizard["moves"][0]["move"]["url"] = "https://pokeapi.co/api/v2/pokemon/6/"
    charizard["stats"][1]["base_stat"] = 90  # the rest of the answer is still saved
    with caplog.at_level(logging.INFO):
        run_id, status = run_fake_scan(conn, source)
    assert (status, run_status(conn, run_id)) == ("incomplete", ("incomplete", 21, 1, 1))
    assert move_lists(conn)[CHARIZARD] == stored
    expected = f"moves_unread run_id={run_id} pokemon_id={CHARIZARD} rule=move_url"
    assert [line for line in caplog.messages if "moves_unread" in line] == [expected]


def test_a_run_of_chosen_pokemon_fetches_no_moves(
    conn: psycopg.Connection, source: FakePokeApi
) -> None:
    run_fake_scan(conn, source, pokemon_ids=[CHARIZARD])
    assert not any(path.startswith("move") for path in source.requested)
    assert move_rows(conn) == {}
    assert list(move_lists(conn)) == [CHARIZARD]
