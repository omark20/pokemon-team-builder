"""Scan endpoints: the public record of recent runs, and the scheduler's trigger."""

from typing import Any

import psycopg
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from psycopg.rows import dict_row
from pydantic import BaseModel, ConfigDict, Field

from app import auth, db, demo, scan
from app.routes.params import PokemonId

router = APIRouter()


class ScanRequest(BaseModel):
    """Optional body of the trigger: scan only these Pokémon."""

    model_config = ConfigDict(extra="forbid")
    pokemon_ids: list[PokemonId] = Field(min_length=1, max_length=50)


@router.get("/api/scan/status")
def scan_status(request: Request) -> dict[str, Any]:
    """The five most recent runs, newest first, with only their public fields."""
    with db.connection_for(request) as conn:
        runs = (
            conn.cursor(row_factory=dict_row)
            .execute(
                "SELECT id, started_at, finished_at, status, scope, scanned, changed, failed"
                " FROM scan_runs ORDER BY id DESC LIMIT 5"
            )
            .fetchall()
        )
        return {"runs": runs, "demo_active": demo.is_active(conn)}


@router.post("/api/admin/scan", status_code=202, dependencies=[Depends(auth.require_scan_token)])
def trigger_scan(
    request: Request,
    background: BackgroundTasks,
    body: ScanRequest | None = None,
) -> dict[str, int]:
    """Start a scan in the background and answer at once; the caller polls the status."""
    with db.connection_for(request) as conn:
        pokemon_ids = None if body is None else body.pokemon_ids
        try:
            run_id = scan.start_run(conn, "full" if body is None else "subset", scan.utc_now())
        except psycopg.errors.UniqueViolation:
            raise HTTPException(409, "A scan is already running") from None
        database_url = request.app.state.settings.database_url
        background.add_task(scan.scan_with_pokeapi, database_url, run_id, pokemon_ids)
        return {"run_id": run_id}
