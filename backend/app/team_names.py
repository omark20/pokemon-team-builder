"""Team names are unique per owner, ignoring capitals.

The rule is the database's: a unique index on the owner and the lower-case name,
`teams_owner_name`, so no writer can break it. Capitals are compared the way the index
compares them, by the database's own `lower`. `free_name` is the one rule for naming a
clash the visitor did not type, used by the sign-in merge (account_store.py) and by
`make_names_unique`, the start-up step that repairs names stored before the index
existed and then creates it.
"""

import logging
from collections.abc import Callable, Container

from app.db import Conn
from app.logs import log_event

logger = logging.getLogger(__name__)

MAX_NAME = 50  # the column's limit, and the longest name a visitor may type
INDEX = "teams_owner_name"
TAKEN = "You already have a team with that name"


def free_name(name: str, taken: Container[str], lower: Callable[[str], str]) -> str:
    """`name` if its lower case is not taken, else the first of "name (2)", "name (3)", …
    that is free, the name part shortened so the whole fits in 50 characters.

    It always ends: each number gives a different result, and at most 40 names are in
    play, an account's 20 and a browser's 20 during a sign-in.
    """
    candidate, number = name, 2
    while lower(candidate) in taken:
        suffix = f" ({number})"
        candidate = name[: MAX_NAME - len(suffix)].rstrip() + suffix
        number += 1
    return candidate


def database_lower(conn: Conn) -> Callable[[str], str]:
    """The database's own lower case, the one the index compares by."""

    def lower(text: str) -> str:
        row = conn.execute("SELECT lower(%s)", (text,)).fetchone()
        assert row is not None  # SELECT of an expression always returns one row
        return str(row[0])

    return lower


def make_names_unique(conn: Conn) -> None:
    """Rename every team whose name clashes with an older team of the same owner, then
    create the index, in one transaction with writes to `teams` locked out meanwhile.

    With the index in place there is nothing to do, and nothing is locked.
    """
    if conn.execute("SELECT to_regclass(%s)", (INDEX,)).fetchone() != (None,):
        return
    with conn.transaction():
        conn.execute("LOCK TABLE teams IN SHARE ROW EXCLUSIVE MODE")  # reads go on
        renamed = _rename_clashes(conn)
        conn.execute(f"CREATE UNIQUE INDEX IF NOT EXISTS {INDEX} ON teams (user_id, lower(name))")
    log_event(logger, logging.INFO, "team_names_made_unique", renamed=renamed)


def _rename_clashes(conn: Conn) -> int:
    """Within each owner, oldest first, keep the first team of each name and rename the
    others by `free_name`; the number renamed."""
    rows = conn.execute(
        "SELECT id, user_id, name, lower(name) FROM teams ORDER BY user_id, created_at, id"
    ).fetchall()
    lower = database_lower(conn)
    used: dict[int, set[str]] = {}  # per owner, every lower-case name in use
    for _, user_id, _, name_key in rows:
        used.setdefault(user_id, set()).add(name_key)
    kept: set[tuple[int, str]] = set()
    renamed = 0
    for team_id, user_id, name, name_key in rows:
        if (user_id, name_key) not in kept:
            kept.add((user_id, name_key))
            continue
        new_name = free_name(name, used[user_id], lower)
        used[user_id].add(lower(new_name))
        conn.execute("UPDATE teams SET name = %s WHERE id = %s", (new_name, team_id))
        renamed += 1
    return renamed
