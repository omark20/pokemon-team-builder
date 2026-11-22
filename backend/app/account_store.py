"""Accounts in the database: creating, deleting, signing a browser in and out, the merge.

An account is a visitor record with a username and a password hash and no token; an
anonymous visitor's record has a token and no username. Every function here keeps that
so. Each runs inside the request's one transaction (`db.connection_for`), so a refusal
part-way through leaves nothing changed. Nothing here hashes a password: the routes do
that before borrowing a connection, so none is held while hashing.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import NamedTuple

import psycopg
from fastapi import HTTPException, Request, Response

from app import auth, db
from app.routes.teams import MAX_TEAMS

MAX_SESSIONS = 10  # signed-in browsers per account; the eleventh sign-in drops the oldest
TAKEN = "That username is taken."
SIGNED_IN = "You are already signed in. Sign out to create another account."
RECORD_CHANGED = "This browser's teams changed while signing up. Try again."

# The teams that fit, oldest first, move to the account; the rest stay on the browser's
# record and are deleted with it.
MOVE_TEAMS = """
    UPDATE teams SET user_id = %(account)s
    WHERE id IN (SELECT id FROM teams WHERE user_id = %(browser)s
                 ORDER BY created_at, id LIMIT %(room)s)
"""
COPY_DISMISSALS = """
    INSERT INTO dismissals (user_id, change_id)
    SELECT %(account)s, change_id FROM dismissals WHERE user_id = %(browser)s
    ON CONFLICT DO NOTHING
"""
# Sessions past their 30 days, and all but the newest ten.
PRUNE_SESSIONS = """
    DELETE FROM sessions
    WHERE user_id = %(account)s
      AND (created_at <= %(since)s
           OR id NOT IN (SELECT id FROM sessions WHERE user_id = %(account)s
                         ORDER BY created_at DESC, id DESC LIMIT %(keep)s))
"""


class Account(NamedTuple):
    """An account's record: its internal ID, its name as first typed, its password hash."""

    id: int
    username: str
    password_hash: str


@dataclass(frozen=True)
class Merge:
    teams_added: int
    teams_not_added: int


def find_account(conn: db.Conn, username: str) -> Account | None:
    """The account with this name, whatever capitals, or None."""
    row = conn.execute(
        "SELECT id, username, password_hash FROM users WHERE username_key = %s",
        (username.lower(),),
    ).fetchone()
    return None if row is None else Account(*row)


def make_account(
    request: Request,
    response: Response,
    conn: db.Conn,
    username: str,
    password_hash: str,
    now: datetime,
) -> int:
    """Make the account and sign this browser in to it; returns its ID.

    A browser with an anonymous record turns that record into the account, so its teams
    stay where they are and its token is erased; one without becomes a new visitor
    record, under the same limits as any. A browser already signed in is refused.
    """
    identity = auth.identify(request, conn, now)
    if identity is not None and identity.signed_in:
        raise HTTPException(409, SIGNED_IN)
    if find_account(conn, username) is not None:
        raise HTTPException(409, TAKEN)
    try:
        if identity is None:
            auth.admit_new_visitor(request, conn)
            account_id = _insert_account(conn, username, password_hash)
        else:
            account_id = _convert(conn, identity.user_id, username, password_hash)
    except psycopg.errors.UniqueViolation:
        raise HTTPException(409, TAKEN) from None  # the same name, made a moment before
    start_session(request, response, conn, account_id, now)
    return account_id


def _insert_account(conn: db.Conn, username: str, password_hash: str) -> int:
    row = conn.execute(
        "INSERT INTO users (username, username_key, password_hash) VALUES (%s, %s, %s)"
        " RETURNING id",
        (username, username.lower(), password_hash),
    ).fetchone()
    assert row is not None  # INSERT ... RETURNING always returns the new row
    return int(row[0])


def _convert(conn: db.Conn, user_id: int, username: str, password_hash: str) -> int:
    row = conn.execute(
        "UPDATE users SET username = %s, username_key = %s, password_hash = %s,"
        " token_hash = NULL WHERE id = %s AND token_hash IS NOT NULL RETURNING id",
        (username, username.lower(), password_hash, user_id),
    ).fetchone()
    if row is None:  # a sign-in from this browser merged the record away meanwhile
        raise HTTPException(409, RECORD_CHANGED)
    return user_id


def sign_in(
    request: Request, response: Response, conn: db.Conn, account_id: int, now: datetime
) -> Merge | None:
    """Sign this browser in to the account, whose password has been checked; None if the
    account was deleted since then, and nothing is changed.

    The account's record is locked first, then the browser's anonymous record, always in
    that order. A browser signed in to an account, this one or another, has that session
    deleted and nothing merged; an anonymous browser's teams and dismissals are merged.
    """
    locked = conn.execute("SELECT id FROM users WHERE id = %s FOR UPDATE", (account_id,))
    if locked.fetchone() is None:  # deleted from another browser after the password check
        return None
    identity = auth.identify(request, conn, now)
    merge = Merge(0, 0)
    if identity is not None and identity.signed_in:
        conn.execute("DELETE FROM sessions WHERE token_hash = %s", (auth.cookie_hash(request),))
    elif identity is not None:
        merge = _merge(conn, account_id, identity.user_id)
    start_session(request, response, conn, account_id, now)
    return merge


def _merge(conn: db.Conn, account_id: int, browser_id: int) -> Merge:
    """Move the browser's teams in, oldest first, up to MAX_TEAMS; copy its dismissals;
    delete its record, which takes any team that did not fit and its token with it."""
    locked = conn.execute(
        "SELECT id FROM users WHERE id = %s AND token_hash IS NOT NULL FOR UPDATE", (browser_id,)
    ).fetchone()
    if locked is None:  # merged or turned into an account by another request meanwhile
        return Merge(0, 0)
    held = _team_count(conn, account_id)
    brought = _team_count(conn, browser_id)
    ids = {"account": account_id, "browser": browser_id, "room": max(0, MAX_TEAMS - held)}
    moved = conn.execute(MOVE_TEAMS, ids).rowcount
    conn.execute(COPY_DISMISSALS, ids)
    conn.execute("DELETE FROM users WHERE id = %s", (browser_id,))
    return Merge(moved, brought - moved)


def _team_count(conn: db.Conn, user_id: int) -> int:
    row = conn.execute("SELECT count(*) FROM teams WHERE user_id = %s", (user_id,)).fetchone()
    return int(row[0]) if row else 0


def start_session(
    request: Request, response: Response, conn: db.Conn, account_id: int, now: datetime
) -> None:
    """A new session for this browser, its cookie set to last as long; then the account's
    expired sessions and all but its newest MAX_SESSIONS are removed."""
    value, token_hash = auth.new_token()
    conn.execute(
        "INSERT INTO sessions (user_id, token_hash, created_at) VALUES (%s, %s, %s)",
        (account_id, token_hash, now),
    )
    since = now - auth.SESSION_LIFETIME
    conn.execute(PRUNE_SESSIONS, {"account": account_id, "since": since, "keep": MAX_SESSIONS})
    auth.set_cookie(request, response, value, int(auth.SESSION_LIFETIME.total_seconds()))


def end_session(conn: db.Conn, request: Request) -> int | None:
    """Delete this browser's session; the account's ID if there was one, else None."""
    token_hash = auth.cookie_hash(request)
    row = conn.execute(
        "DELETE FROM sessions WHERE token_hash = %s RETURNING user_id", (token_hash,)
    ).fetchone()
    return None if row is None else int(row[0])


def signed_in_account(conn: db.Conn, request: Request, now: datetime) -> Account | None:
    """The account this browser is signed in to, or None."""
    identity = auth.identify(request, conn, now)
    if identity is None or not identity.signed_in:
        return None
    row = conn.execute(
        "SELECT id, username, password_hash FROM users WHERE id = %s", (identity.user_id,)
    ).fetchone()
    return None if row is None else Account(*row)


def delete_account(conn: db.Conn, account_id: int) -> None:
    """Remove the account; its teams and their members, its dismissals and every one of
    its sessions go with it (the tables' ON DELETE CASCADE), so the name is free again."""
    conn.execute("DELETE FROM users WHERE id = %s AND username IS NOT NULL", (account_id,))
