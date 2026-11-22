"""A visitor's own teams: list, create, rename, set members, delete.

Add, remove and reorder are all one request that sends the complete ordered list of
Pokémon IDs, stored in one transaction under a lock on the team row, numbered 1 to n.
So positions cannot have gaps or clashes, and the same Pokémon may fill several slots.
A team that is not the caller's is a 404, the same as one that does not exist.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from psycopg.rows import dict_row
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app import auth, db, limits
from app.routes.params import PathId, PokemonId

router = APIRouter(prefix="/api/teams")
writes = [Depends(limits.limit_writes)]

MAX_TEAMS = 20
MAX_MEMBERS = 6

TEAM_QUERY = """
    SELECT t.id, t.name,
           coalesce(array_agg(m.pokemon_id ORDER BY m.position)
                    FILTER (WHERE m.pokemon_id IS NOT NULL), '{}') AS pokemon_ids
    FROM teams t LEFT JOIN team_members m ON m.team_id = t.id
    WHERE t.user_id = %(user_id)s AND (%(team_id)s::bigint IS NULL OR t.id = %(team_id)s)
    GROUP BY t.id ORDER BY t.id
"""

# Strict: a number sent as text, or true for 1, is refused rather than converted.
STRICT = ConfigDict(extra="forbid", strict=True)
TeamName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]


class NameBody(BaseModel):
    model_config = STRICT
    name: TeamName


class MembersBody(BaseModel):
    model_config = STRICT
    pokemon_ids: list[PokemonId] = Field(max_length=MAX_MEMBERS)


@router.get("")
def list_teams(request: Request) -> list[dict[str, Any]]:
    """The caller's teams in creation order; [] without a cookie, which creates no visitor."""
    with db.connection_for(request) as conn:
        user_id = auth.current_user(request, conn)
        return [] if user_id is None else _teams(conn, user_id)


@router.post("", status_code=201, dependencies=writes)
def create_team(body: NameBody, request: Request, response: Response) -> dict[str, Any]:
    """Create an empty team; a first-time visitor gets their record and cookie here."""
    with db.connection_for(request) as conn:
        user_id = auth.current_user(request, conn) or auth.create_user(request, response, conn)
        # Locking the visitor's row makes the count and the insert one step per visitor.
        conn.execute("SELECT id FROM users WHERE id = %s FOR UPDATE", (user_id,))
        counted = conn.execute(
            "SELECT count(*) FROM teams WHERE user_id = %s", (user_id,)
        ).fetchone()
        if counted is not None and counted[0] >= MAX_TEAMS:
            raise HTTPException(409, f"A visitor can have at most {MAX_TEAMS} teams")
        row = conn.execute(
            "INSERT INTO teams (user_id, name) VALUES (%s, %s) RETURNING id", (user_id, body.name)
        ).fetchone()
        assert row is not None  # INSERT ... RETURNING always returns the new row
        return _team(conn, user_id, row[0])


@router.patch("/{team_id}", dependencies=writes)
def rename_team(team_id: PathId, body: NameBody, request: Request) -> dict[str, Any]:
    with db.connection_for(request) as conn:
        user_id = _owner(request, conn, team_id)
        conn.execute("UPDATE teams SET name = %s WHERE id = %s", (body.name, team_id))
        return _team(conn, user_id, team_id)


@router.put("/{team_id}/members", dependencies=writes)
def set_members(team_id: PathId, body: MembersBody, request: Request) -> dict[str, Any]:
    """Replace the team's members with this ordered list, in slots 1 to n."""
    with db.connection_for(request) as conn:
        user_id = _owner(request, conn, team_id)
        wanted = set(body.pokemon_ids)
        found = conn.execute("SELECT id FROM pokemon WHERE id = ANY(%s)", (list(wanted),))
        if {pokemon_id for (pokemon_id,) in found} != wanted:
            raise HTTPException(422, "Unknown Pokémon ID")
        conn.execute("DELETE FROM team_members WHERE team_id = %s", (team_id,))
        conn.cursor().executemany(
            "INSERT INTO team_members (team_id, position, pokemon_id) VALUES (%s, %s, %s)",
            [(team_id, position, pid) for position, pid in enumerate(body.pokemon_ids, start=1)],
        )
        return _team(conn, user_id, team_id)


@router.delete("/{team_id}", status_code=204, dependencies=writes)
def delete_team(team_id: PathId, request: Request) -> Response:
    with db.connection_for(request) as conn:
        _owner(request, conn, team_id)
        conn.execute("DELETE FROM teams WHERE id = %s", (team_id,))
        return Response(status_code=204)


def _owner(request: Request, conn: db.Conn, team_id: int) -> int:
    """The caller's ID if the team is theirs, with the team row locked; otherwise 404."""
    user_id = auth.current_user(request, conn)
    owned = conn.execute(
        "SELECT id FROM teams WHERE id = %s AND user_id = %s FOR UPDATE", (team_id, user_id)
    ).fetchone()
    if user_id is None or owned is None:
        raise HTTPException(404, "Team not found")
    return user_id


def _teams(conn: db.Conn, user_id: int, team_id: int | None = None) -> list[dict[str, Any]]:
    cursor = conn.cursor(row_factory=dict_row)
    return cursor.execute(TEAM_QUERY, {"user_id": user_id, "team_id": team_id}).fetchall()


def _team(conn: db.Conn, user_id: int, team_id: int) -> dict[str, Any]:
    [team] = _teams(conn, user_id, team_id)
    return team
