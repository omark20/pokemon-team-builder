"""Scan endpoints: the public record of recent runs, and the scheduler's trigger."""

from typing import Annotated, Any

import psycopg
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from psycopg.rows import dict_row
from pydantic import BaseModel, ConfigDict, Field

from app import auth, scan
from app.db import Connection

router = APIRouter()

PokemonId = Annotated[int, Field(ge=1, le=2_147_483_647)]


class ScanRequest(BaseModel):
    """Optional body of the trigger: scan only these Pokémon."""

    model_config = ConfigDict(extra="forbid")
    pokemon_ids: list[PokemonId] = Field(min_length=1, max_length=50)


@router.get("/api/scan/status")
def scan_status(conn: Connection) -> dict[str, Any]:
    """The five most recent runs, newest first, with only their public fields."""
    runs = (
        conn.cursor(row_factory=dict_row)
        .execute(
            "SELECT id, started_at, finished_at, status, scope, scanned, changed, failed"
            " FROM scan_runs ORDER BY id DESC LIMIT 5"
        )
        .fetchall()
    )
    # Demo overrides arrive with their tables at a later milestone; until then none exist.
    return {"runs": runs, "demo_active": False}


@router.post("/api/admin/scan", status_code=202, dependencies=[Depends(auth.require_scan_token)])
def trigger_scan(
    request: Request,
    background: BackgroundTasks,
    conn: Connection,
    body: ScanRequest | None = None,
) -> dict[str, int]:
    """Start a scan in the background and answer at once; the caller polls the status."""
    scope = "full" if body is None else "subset"
    try:
        run_id = scan.start_run(conn, scope)
    except psycopg.errors.UniqueViolation:
        raise HTTPException(409, "A scan is already running") from None
    background.add_task(scan.finish_run, request.app.state.settings.database_url, run_id)
    return {"run_id": run_id}
