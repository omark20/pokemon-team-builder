"""Optional accounts: who am I, create or delete an account, sign in, sign out.

A password is a secret type from the moment the body is read, so it cannot be printed
by accident, and the app's validation errors never quote input (main.py). The rules a
username or password must meet are checked here and answered with the rule's sentence.
Hashing takes one of two places and holds no database connection: a connection is
borrowed to read, given back, the hash is worked out, and one is borrowed again to
write. The routes are plain functions, so hashing runs in a worker thread, never on the
event loop. No username, password, hash or token is ever logged.
"""

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from app import account_store, accounts, auth, db, limits
from app.logs import log_event

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

HASH_PLACES = 2  # password hashes worked out at once: each takes 19 MiB and a CPU
HASH_WAIT_SECONDS = 2.0  # then 503, rather than holding a worker thread longer
WRONG = "Wrong username or password."
WRONG_PASSWORD = "Wrong password."  # deleting: the caller is signed in, so no name to hide
NOT_SIGNED_IN = "You are not signed in to an account."
BUSY = "Too many sign-ins at once. Try again in a moment."


class Credentials(BaseModel):
    """The body of sign-up and sign-in. The username's length here only bounds what is
    read; its rules are checked in the route."""

    model_config = ConfigDict(extra="forbid", strict=True)
    username: str = Field(max_length=64)
    password: SecretStr


class PasswordBody(BaseModel):
    """The body of deleting an account: the current password, and no username, so one
    account cannot name another."""

    model_config = ConfigDict(extra="forbid", strict=True)
    password: SecretStr


@contextmanager
def _hash_place(request: Request) -> Iterator[None]:
    """Hold one of the HASH_PLACES while hashing; 503 if none frees up in time."""
    places = request.app.state.hash_places
    if not places.acquire(timeout=HASH_WAIT_SECONDS):
        if request.app.state.limiter.first_refusal("sign_in", limits.client_address(request)):
            log_event(logger, logging.WARNING, "hashing_busy", request_id=request.state.request_id)
        raise HTTPException(503, BUSY, headers={"Retry-After": "1"})
    try:
        yield
    finally:
        places.release()


@router.get("/session")
def who_am_i(request: Request) -> dict[str, str | None]:
    """The signed-in account's name, or null; no database work without a cookie."""
    if auth.cookie_hash(request) is None:
        return {"username": None}
    with db.connection_for(request) as conn:
        account = account_store.signed_in_account(conn, request, datetime.now(UTC))
    return {"username": None if account is None else account.username}


@router.post("/account", status_code=201, dependencies=[Depends(limits.limit_account)])
def create_account(body: Credentials, request: Request, response: Response) -> dict[str, str]:
    """Create an account and sign this browser in; its anonymous teams stay its own."""
    username, password = body.username, body.password.get_secret_value()
    problem = accounts.username_problem(username) or accounts.password_problem(password, username)
    if problem is not None:
        raise HTTPException(422, problem)
    with _hash_place(request):
        password_hash = accounts.hash_password(password)
    now = datetime.now(UTC)
    with db.connection_for(request) as conn:
        account_id = account_store.make_account(
            request, response, conn, username, password_hash, now
        )
    _log(request, "account_created", account_id)
    return {"username": username}


@router.post("/session")
def sign_in(body: Credentials, request: Request, response: Response) -> dict[str, Any]:
    """Sign in, and merge this browser's anonymous teams into the account up to 20, each
    renamed if the account already has its name (`teams_renamed` counts them).

    An unknown name and a wrong password get the same answer after the same work: for an
    unknown name a dummy hash is verified.
    """
    limits.enforce_sign_in(request, body.username)
    with db.connection_for(request) as conn:
        account = account_store.find_account(conn, body.username)
    with _hash_place(request):
        stored = None if account is None else account.password_hash
        matched = accounts.password_matches(stored, body.password.get_secret_value())
    if account is None or not matched:
        _log(request, "sign_in_failed", None if account is None else account.id)
        raise HTTPException(401, WRONG)
    now = datetime.now(UTC)
    with db.connection_for(request) as conn:
        merge = account_store.sign_in(request, response, conn, account.id, now)
    if merge is None:  # the account was deleted while its password was being checked
        _log(request, "sign_in_failed", account.id)
        raise HTTPException(401, WRONG)
    _log(request, "signed_in", account.id)
    return {"username": account.username, **vars(merge)}


@router.delete("/session", status_code=204, dependencies=[Depends(limits.limit_writes)])
def sign_out(request: Request) -> Response:
    """End this browser's session and clear its cookie. Harmless without one; an
    anonymous visitor's cookie is left alone, so their teams are not cut off."""
    response = Response(status_code=204)
    if auth.cookie_hash(request) is None:
        return response
    with db.connection_for(request) as conn:
        account_id = account_store.end_session(conn, request)
    if account_id is not None:
        auth.clear_cookie(request, response)
        _log(request, "signed_out", account_id)
    return response


@router.post(
    "/account/delete",
    status_code=204,
    dependencies=[Depends(limits.limit_deletes_per_address)],
)
def delete_account(body: PasswordBody, request: Request) -> Response:
    """Delete the signed-in account, its teams, dismissals and sessions; clear the cookie.

    The password is checked like a sign-in. Attempts count per signed-in browser and
    against the address's sign-in count, never per username: a stranger cannot use them
    up, and one stolen session cannot use up the owner's own session's attempts.
    """
    with db.connection_for(request) as conn:
        account = account_store.signed_in_account(conn, request, datetime.now(UTC))
    if account is None:
        raise HTTPException(401, NOT_SIGNED_IN)
    session = auth.cookie_hash(request)
    assert session is not None  # the account was found by this cookie
    limits.enforce(request, "delete_session", key=session.hex())
    with _hash_place(request):
        matched = accounts.password_matches(account.password_hash, body.password.get_secret_value())
    if not matched:
        raise HTTPException(401, WRONG_PASSWORD)
    with db.connection_for(request) as conn:
        account_store.delete_account(conn, account.id)
    _log(request, "account_deleted", account.id)
    response = Response(status_code=204)
    auth.clear_cookie(request, response)
    return response


def _log(request: Request, event: str, account_id: int | None) -> None:
    """One account event: the request's ID and the account's internal number, if any."""
    fields: dict[str, int | str] = {"request_id": request.state.request_id}
    if account_id is not None:
        fields["user_id"] = account_id
    log_event(logger, logging.INFO, event, **fields)
