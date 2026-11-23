"""The scan's duel step against the fake PokéAPI built from samples/, on the test database.

The expected fours and baselines are worked out by the core from the sample files
themselves (captured.py and the captured /pokemon answers), not through the database,
so the test checks what the step reads and stores, not only that it ran.
"""

import json
import logging
from dataclasses import replace
from typing import Any

import psycopg
import pytest
from captured import CENSUS, CHART, MOVES, SAMPLES
from fake_pokeapi import MOVE_LIST, FakePokeApi, run_fake_scan

from app import scan_duel
from app.domain.counter_score import margin_sum
from app.domain.default_moves import default_four, field_types
from app.domain.moves import parse_move_ids
from app.pokeapi import UpstreamError
from app.scan import utc_now
from app.scan_store import Run

FIELD_IDS = {3, 6, 9, 25, 34, 59, 65, 68, 76, 94, 130, 131, 135, 142, 143, 149, 248, 445}


def duel_rows(conn: psycopg.Connection) -> dict[int, tuple[list[int], int | None]]:
    rows = conn.execute("SELECT pokemon_id, move_ids, baseline FROM duel_data")
    return {pokemon_id: (move_ids, baseline) for pokemon_id, move_ids, baseline in rows}


def expected_rows() -> dict[int, tuple[list[int], int | None]]:
    """The fours and baselines the core gives for the fake's 21 Pokémon and 17 moves."""
    served = {json.loads(p.read_text())["id"] for p in SAMPLES.glob("move_[0-9]*_*.json")}
    answers = [json.loads(p.read_text()) for p in SAMPLES.glob("pokemon_[0-9]*_*.json")]
    learnable = {CENSUS[answer["name"]]: parse_move_ids(answer) for answer in answers}
    types = field_types(learnable)
    armed = []
    for entry, move_ids in learnable.items():
        known = [MOVES[i] for i in move_ids if i in served]
        four = default_four(entry, known, types, CHART)
        armed.append(replace(entry, moves=tuple(MOVES[i] for i in four)))
    field = [entry for entry in armed if entry.is_default]  # none is removed in the fake
    return {
        entry.id: (
            [move.id for move in entry.moves],
            margin_sum(entry, field, CHART) if entry.is_default else None,
        )
        for entry in armed
    }


def run_status(conn: psycopg.Connection, run_id: int) -> str:
    row = conn.execute("SELECT status FROM scan_runs WHERE id = %s", (run_id,)).fetchone()
    assert row is not None
    return str(row[0])


def test_a_full_run_stores_every_four_and_a_baseline_for_each_field_pokemon(
    conn: psycopg.Connection, source: FakePokeApi, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO):
        run_id, status = run_fake_scan(conn, source)
    assert status == "ok"
    stored = duel_rows(conn)
    assert stored == expected_rows()
    assert {i for i, (_, baseline) in stored.items() if baseline is not None} == FIELD_IDS
    assert any(four for four, _ in stored.values())  # the captured moves arm some of them
    logged = [line for line in caplog.messages if line.startswith("duel_data_stored")]
    assert len(logged) == 1 and f"run_id={run_id} pokemon=21 field=18 " in logged[0]


def test_the_step_pauses_after_each_baseline(conn: psycopg.Connection, source: FakePokeApi) -> None:
    run_fake_scan(conn, source)
    pauses: list[float] = []
    assert scan_duel.refresh(conn, Run(0, utc_now, utc_now()), pauses.append)
    assert pauses == [scan_duel.PAUSE_SECONDS] * len(FIELD_IDS)


def test_a_step_that_fails_keeps_the_stored_rows_and_the_run_is_incomplete(
    conn: psycopg.Connection,
    source: FakePokeApi,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    run_fake_scan(conn, source)
    conn.execute("UPDATE duel_data SET baseline = 7 WHERE pokemon_id = 6")
    before = duel_rows(conn)

    def failing(*_: Any) -> int:
        raise RuntimeError("the core failed")

    monkeypatch.setattr(scan_duel, "margin_sum", failing)
    with caplog.at_level(logging.INFO):
        run_id, status = run_fake_scan(conn, source)
    assert (status, run_status(conn, run_id)) == ("incomplete", "incomplete")
    assert duel_rows(conn) == before
    assert any(line.startswith(f"duel_data_failed run_id={run_id}") for line in caplog.messages)


def test_a_step_with_no_stored_moves_is_skipped_and_the_run_is_incomplete(
    conn: psycopg.Connection, source: FakePokeApi, caplog: pytest.LogCaptureFixture
) -> None:
    source.answers[MOVE_LIST] = UpstreamError("http_404", retryable=False)
    with caplog.at_level(logging.INFO):
        run_id, status = run_fake_scan(conn, source)
    assert status == "incomplete"
    assert duel_rows(conn) == {}
    expected = f"duel_data_skipped run_id={run_id} reason=no_moves"
    assert [line for line in caplog.messages if line.startswith("duel_data_")] == [expected]


def test_a_run_of_chosen_pokemon_leaves_the_duel_data_alone(
    conn: psycopg.Connection, source: FakePokeApi
) -> None:
    run_fake_scan(conn, source)
    conn.execute("UPDATE duel_data SET baseline = 7 WHERE pokemon_id = 6")
    before = duel_rows(conn)
    _, status = run_fake_scan(conn, source, pokemon_ids=[6])
    assert status == "ok"
    assert duel_rows(conn) == before


def test_each_full_run_replaces_every_row(conn: psycopg.Connection, source: FakePokeApi) -> None:
    run_fake_scan(conn, source)
    conn.execute("UPDATE duel_data SET baseline = 7, move_ids = '{}' WHERE pokemon_id = 6")
    conn.execute("UPDATE duel_data SET baseline = 7 WHERE pokemon_id = 10034")  # not in the field
    run_fake_scan(conn, source)
    assert duel_rows(conn) == expected_rows()
