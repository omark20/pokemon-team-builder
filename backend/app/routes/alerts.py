"""A visitor's alerts: changes from the last 7 days that involve their teams' Pokémon.

Computed when asked, from the teams the visitor has now, so nothing per visitor is
written at scan time. A change involves the visitor if it is about a Pokémon on any of
their teams, about a type-chart cell whose attacking or defending type is a type of
one of those Pokémon, or about a move one of those team members carries: one chosen
for its slot, or, in a slot with no choice, one of the Pokémon's default four as
stored now. A Pokémon that could learn a move but does not carry it is not involved.
Each alert names the visitor's Pokémon it touches, once each, and `move` names the
move of a move alert (null for the other kinds).
"""

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from psycopg.rows import dict_row

from app import auth, db, limits
from app.routes.params import PathId

router = APIRouter(prefix="/api/alerts")

MAX_ALERTS = 100

# `mine` is one row per team slot: its Pokémon, that Pokémon's types, and the moves the
# slot carries (its chosen moves, else the Pokémon's stored default four).
ALERTS_QUERY = """
    WITH mine AS (
        SELECT p.id, p.types, coalesce(m.move_ids, d.move_ids, '{}') AS carried
        FROM teams t
        JOIN team_members m ON m.team_id = t.id
        JOIN pokemon p ON p.id = m.pokemon_id
        LEFT JOIN duel_data d ON d.pokemon_id = p.id
        WHERE t.user_id = %(user_id)s
    )
    SELECT c.id, c.pokemon_id, c.attacker, c.defender, mv.name AS move, c.field,
           c.old_value, c.new_value, c.detected_at, c.is_demo,
           array_agg(DISTINCT mine.id ORDER BY mine.id) AS your_pokemon
    FROM changes c
    JOIN mine ON c.pokemon_id = mine.id
              OR c.attacker = ANY (mine.types)
              OR c.defender = ANY (mine.types)
              OR c.move_id = ANY (mine.carried)
    LEFT JOIN moves mv ON mv.id = c.move_id
    WHERE c.detected_at > %(now)s - interval '7 days'
      AND NOT EXISTS (
          SELECT 1 FROM dismissals d WHERE d.user_id = %(user_id)s AND d.change_id = c.id
      )
    GROUP BY c.id, mv.name
    ORDER BY c.detected_at DESC, c.id DESC
    LIMIT %(limit)s
"""


def alerts_for(conn: db.Conn, user_id: int, now: datetime) -> list[dict[str, Any]]:
    """The visitor's undismissed alerts newer than 7 days before `now`, newest first."""
    params = {"user_id": user_id, "now": now, "limit": MAX_ALERTS}
    return conn.cursor(row_factory=dict_row).execute(ALERTS_QUERY, params).fetchall()


@router.get("")
def list_alerts(request: Request) -> list[dict[str, Any]]:
    with db.connection_for(request) as conn:
        user_id = auth.current_user(request, conn)
        return [] if user_id is None else alerts_for(conn, user_id, datetime.now(UTC))


@router.post("/{change_id}/dismiss", status_code=204, dependencies=[Depends(limits.limit_writes)])
def dismiss(change_id: PathId, request: Request) -> Response:
    """Hide this alert for this visitor for good. Repeating it is harmless."""
    with db.connection_for(request) as conn:
        user_id = auth.current_user(request, conn)
        known = conn.execute("SELECT 1 FROM changes WHERE id = %s", (change_id,)).fetchone()
        if user_id is None or known is None:
            raise HTTPException(404, "Alert not found")
        conn.execute(
            "INSERT INTO dismissals (user_id, change_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (user_id, change_id),
        )
        return Response(status_code=204)
