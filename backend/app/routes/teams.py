"""A visitor's own teams: list, create, rename, set members, delete.

Add, remove and reorder are all one request that sends the complete ordered list of
Pokémon IDs, stored in one transaction under a lock on the team row, numbered 1 to n.
So positions cannot have gaps or clashes, and the same Pokémon may fill several slots.
The same request may send, beside each Pokémon, the moves chosen for that slot, or null
for its default four; a choice belongs to the slot and travels with it. A team that is
not the caller's is a 404, the same as one that does not exist.
"""

import unicodedata
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from psycopg.rows import dict_row
from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

from app import auth, db, duel_store, limits
from app.chosen_moves import counted
from app.routes.params import MoveId, PathId, PokemonId

router = APIRouter(prefix="/api/teams")
writes = [Depends(limits.limit_writes)]

MAX_TEAMS = 20
MAX_MEMBERS = 6
MAX_MOVES = 4
NOT_LEARNABLE = "A chosen move is not one this Pokémon can learn"
NOT_COUNTED = "A chosen move is not one that can be used in a duel"

# `moves` is parallel to `pokemon_ids`: per slot, its chosen moves as {id, name} in the
# order chosen, or null for the default four. Moves are never deleted, so each has a name.
TEAM_QUERY = """
    SELECT t.id, t.name,
           coalesce(array_agg(m.pokemon_id ORDER BY m.position)
                    FILTER (WHERE m.pokemon_id IS NOT NULL), '{}') AS pokemon_ids,
           coalesce(json_agg(picked.moves ORDER BY m.position)
                    FILTER (WHERE m.pokemon_id IS NOT NULL), '[]') AS moves
    FROM teams t LEFT JOIN team_members m ON m.team_id = t.id
    LEFT JOIN LATERAL (
        SELECT json_agg(json_build_object('id', mv.id, 'name', mv.name) ORDER BY slot.n) AS moves
        FROM unnest(m.move_ids) WITH ORDINALITY AS slot(id, n) JOIN moves mv ON mv.id = slot.id
    ) picked ON true
    WHERE t.user_id = %(user_id)s AND (%(team_id)s::bigint IS NULL OR t.id = %(team_id)s)
    GROUP BY t.id ORDER BY t.id
"""

# Strict: a number sent as text, or true for 1, is refused rather than converted.
STRICT = ConfigDict(extra="forbid", strict=True)


def _readable(name: str) -> str:
    """Refuse control characters (a NUL breaks the database, a newline or tab the tab
    bar) and a name with nothing visible in it, such as a lone zero-width space."""
    categories = [unicodedata.category(character) for character in name]
    if "Cc" in categories:
        raise ValueError("a team name cannot contain control characters")
    if not any(category[0] not in "CZ" for category in categories):
        raise ValueError("a team name needs at least one visible character")
    return name


TeamName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=50),
    AfterValidator(_readable),
]


class NameBody(BaseModel):
    model_config = STRICT
    name: TeamName


def _no_repeat(move_ids: list[int]) -> list[int]:
    if len(set(move_ids)) != len(move_ids):
        raise ValueError("a slot cannot hold the same move twice")
    return move_ids


ChosenMoves = Annotated[
    list[MoveId], Field(min_length=1, max_length=MAX_MOVES), AfterValidator(_no_repeat)
]


class MembersBody(BaseModel):
    """The whole ordered team, and optionally each slot's chosen moves (null: default four)."""

    model_config = STRICT
    pokemon_ids: list[PokemonId] = Field(max_length=MAX_MEMBERS)
    move_ids: list[ChosenMoves | None] | None = None

    @model_validator(mode="after")
    def _one_entry_per_slot(self) -> "MembersBody":
        if self.move_ids is not None and len(self.move_ids) != len(self.pokemon_ids):
            raise ValueError("move_ids needs one entry per Pokémon")
        return self

    def chosen(self) -> list[list[int] | None]:
        """Each slot's chosen moves, or None; all None when none were sent."""
        return self.move_ids or [None] * len(self.pokemon_ids)


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
        # A Pokémon flagged removed upstream is still allowed: a team that holds one must
        # still be able to save its other changes.
        found = conn.execute("SELECT id FROM pokemon WHERE id = ANY(%s)", (list(wanted),))
        if {pokemon_id for (pokemon_id,) in found} != wanted:
            raise HTTPException(422, "Unknown Pokémon ID")
        slots = list(zip(body.pokemon_ids, body.chosen(), strict=True))
        _check_choices(conn, slots)
        conn.execute("DELETE FROM team_members WHERE team_id = %s", (team_id,))
        conn.cursor().executemany(
            "INSERT INTO team_members (team_id, position, pokemon_id, move_ids)"
            " VALUES (%s, %s, %s, %s)",
            [(team_id, position, *slot) for position, slot in enumerate(slots, start=1)],
        )
        return _team(conn, user_id, team_id)


@router.delete("/{team_id}", status_code=204, dependencies=writes)
def delete_team(team_id: PathId, request: Request) -> Response:
    with db.connection_for(request) as conn:
        _owner(request, conn, team_id)
        conn.execute("DELETE FROM teams WHERE id = %s", (team_id,))
        return Response(status_code=204)


def _check_choices(conn: db.Conn, slots: list[tuple[int, list[int] | None]]) -> None:
    """422 unless every chosen move is one its slot's Pokémon can learn and use in a duel."""
    chosen = {move_id for _, move_ids in slots for move_id in move_ids or ()}
    if not chosen:
        return
    moves = duel_store.load_moves_named(conn, chosen)
    lists = duel_store.load_move_lists(conn, {pokemon_id for pokemon_id, _ in slots})
    for pokemon_id, move_ids in slots:
        for move_id in move_ids or ():
            if move_id not in lists.get(pokemon_id, set()):
                raise HTTPException(422, NOT_LEARNABLE)
            if not counted(move_id, moves):
                raise HTTPException(422, NOT_COUNTED)


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
