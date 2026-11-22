"""`make smoke`: drive the real app and its database through the HTTP API, step by step.

It starts the app on 127.0.0.1:8765 against the local development database, runs the
steps in order, prints "ok" or "FAIL" with what was expected and what came back, and
stops the app however it ends. The scan in step 1 reads the live PokéAPI. The address is
a constant, so this script cannot be pointed at the public site; the token is the local
one from the git-ignored .env, and no token or cookie is ever printed.
"""

import os
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

ADDRESS = "http://127.0.0.1:8765"
BACKEND = Path(__file__).resolve().parents[1]
START_SECONDS = 30
SCAN_WAIT_SECONDS = 15 * 60
POLL_SECONDS = 2

# Expected values from the captures: samples/README.md facts 10 to 12, and the detail
# files pokemon_6_charizard_dual_type.json and pokemon_25_pikachu_single_type.json.
LISTED = 1351
DEFAULT_FORMS = 1025
WITHOUT_SPRITE = 9
CHARIZARD = {"name": "charizard", "types": ["fire", "flying"], "stats": [78, 84, 78, 109, 85, 100]}
PIKACHU = {"name": "pikachu", "types": ["electric"]}
# Visitor A's team and its counter team on the full pool (the plan's worked full-pool
# figure, also returned by an independently written search).
TEAM_A = [6, 9, 3]
COUNTERS_A = ["archeops", "hydrapple", "celesteela"]
TOTALS_A = {"assigned_points": 9, "coverage": 6, "base_stats": 1677}
POOL_SIZE = DEFAULT_FORMS


class SmokeFailure(Exception):
    """A step did not hold; the message says what was expected and what came back."""


@dataclass
class Smoke:
    """What the steps share: the HTTP client, the local token, and baselines taken."""

    http: httpx.Client
    scan_token: str
    list_baseline: list[dict[str, Any]] = field(default_factory=list)
    cookies: dict[str, str] = field(default_factory=dict)  # visitor name: uid value
    teams: dict[str, int] = field(default_factory=dict)  # visitor name: their team's ID

    def scan_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.scan_token}"}

    def as_visitor(self, visitor: str, method: str, path: str, **options: Any) -> httpx.Response:
        """A request carrying the visitor's cookie, sent by hand: a Secure cookie is not
        sent back over plain http by standard cookie handling."""
        cookie = {"Cookie": f"uid={self.cookies[visitor]}"}
        return self.http.request(method, path, headers=cookie, **options)

    def new_team(self, visitor: str, name: str, members: list[int]) -> None:
        """Create the visitor's team (and the visitor) and set its members."""
        response = self.http.post("/api/teams", json={"name": name})
        check(response.status_code == 201, f"201 creating {name}", response.status_code)
        self.cookies[visitor] = response.cookies["uid"]
        self.http.cookies.clear()  # each visitor's cookie goes only where it is sent by hand
        self.teams[visitor] = response.json()["id"]
        path = f"/api/teams/{self.teams[visitor]}/members"
        put = self.as_visitor(visitor, "PUT", path, json={"pokemon_ids": members})
        check(put.status_code == 200, f"200 setting {name}'s members", put.status_code)


def check(holds: bool, expected: str, got: object) -> None:
    if not holds:
        raise SmokeFailure(f"expected {expected}, got {got}")


def no_demo_active(smoke: Smoke) -> None:
    status = smoke.http.get("/api/scan/status").json()
    check(
        status["demo_active"] is False,
        "no active demo (one is active in this database; this script resets only its own)",
        f"demo_active={status['demo_active']}",
    )


def full_scan(smoke: Smoke) -> None:
    response = smoke.http.post("/api/admin/scan", headers=smoke.scan_headers())
    check(response.status_code == 202, "202 from the scan trigger", response.status_code)
    run = wait_for_run(smoke, response.json()["run_id"])
    check(
        run["status"] == "ok" and run["failed"] == 0,
        "the run to end ok with 0 failed",
        f"{run['status']} with {run['failed']} failed; see the app's lines for run_id={run['id']}",
    )


def wait_for_run(smoke: Smoke, run_id: int) -> dict[str, Any]:
    """Poll the status every 2 seconds until the run has finished, for 15 minutes at most."""
    deadline = time.monotonic() + SCAN_WAIT_SECONDS
    while time.monotonic() < deadline:
        runs = smoke.http.get("/api/scan/status").json()["runs"]
        run: dict[str, Any] = next(r for r in runs if r["id"] == run_id)
        if run["finished_at"] is not None:
            return run
        time.sleep(POLL_SECONDS)
    raise SmokeFailure(f"run {run_id} to finish within 15 minutes")


def full_list(smoke: Smoke) -> None:
    entries = smoke.http.get("/api/pokemon").json()
    by_id = {entry["id"]: entry for entry in entries}
    counts = (
        len(entries),
        sum(e["is_default"] for e in entries),
        sum(e["sprite_url"] is None for e in entries),
    )
    check(
        counts == (LISTED, DEFAULT_FORMS, WITHOUT_SPRITE),
        "1351 entries, 1025 default, 9 without a sprite",
        counts,
    )
    check(_has(by_id[6], CHARIZARD), f"entry 6 to be {CHARIZARD}", by_id[6])
    check(_has(by_id[25], PIKACHU), f"entry 25 to be {PIKACHU}", by_id[25])
    smoke.list_baseline = entries


def team_a(smoke: Smoke) -> None:
    smoke.new_team("A", "Smoke A", TEAM_A)
    teams = smoke.as_visitor("A", "GET", "/api/teams").json()
    members = [team["pokemon_ids"] for team in teams if team["id"] == smoke.teams["A"]]
    check(members == [TEAM_A], f"A's team to hold {TEAM_A} in that order", members)


def counter_a(smoke: Smoke) -> None:
    body = smoke.as_visitor("A", "GET", f"/api/teams/{smoke.teams['A']}/counter").json()
    names = [pick["counter"]["name"] for pick in body["picks"]]
    check(names == COUNTERS_A, f"counters {COUNTERS_A} in slot order", names)
    check(body["totals"] == TOTALS_A, f"totals {TOTALS_A}", body["totals"])
    flags = (body["pool_size"], body["stopped_early"], body["relaxed"])
    check(flags == (POOL_SIZE, False, False), "pool 1025, not stopped early or relaxed", flags)


def clean_up(smoke: Smoke) -> None:
    """Delete the teams this run made, whatever happened before."""
    for visitor, team_id in smoke.teams.items():
        smoke.as_visitor(visitor, "DELETE", f"/api/teams/{team_id}")


def _has(entry: dict[str, Any], expected: dict[str, Any]) -> bool:
    return all(entry[key] == value for key, value in expected.items())


STEPS: list[tuple[str, Callable[[Smoke], None]]] = [
    ("0 no demo is active", no_demo_active),
    ("1 a full live scan ends ok", full_scan),
    ("2 the list matches the captures", full_list),
    ("3 visitor A's team is stored in order", team_a),
    ("4 A's counter team is the expected one", counter_a),
]


def start_app() -> subprocess.Popen[bytes]:
    """The app as a child process on the smoke address, against the local database."""
    command = [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1"]
    command += ["--port", ADDRESS.rsplit(":", 1)[1], "--workers", "1", "--no-server-header"]
    return subprocess.Popen(command, cwd=BACKEND)


def wait_until_up(app: subprocess.Popen[bytes], http: httpx.Client) -> None:
    deadline = time.monotonic() + START_SECONDS
    while time.monotonic() < deadline:
        if app.poll() is not None:
            raise SmokeFailure("the app to start (it exited; is port 8765 already taken?)")
        try:
            if http.get("/healthz").status_code == 200:
                return
        except httpx.TransportError:
            pass
        time.sleep(0.5)
    raise SmokeFailure(f"/healthz to answer within {START_SECONDS} seconds")


def run_steps(smoke: Smoke, app: subprocess.Popen[bytes]) -> bool:
    """Every step in order; stop at the first that fails."""
    name = "start the app"
    try:
        wait_until_up(app, smoke.http)
        for name, step in STEPS:
            step(smoke)
            print(f"smoke: ok   {name}", flush=True)
    except SmokeFailure as failure:
        print(f"smoke: FAIL {name}: {failure}", flush=True)
        return False
    finally:
        clean_up(smoke)
    return True


def main() -> int:
    app = start_app()
    try:
        with httpx.Client(base_url=ADDRESS, timeout=30) as http:
            passed = run_steps(Smoke(http, os.environ["SCAN_TOKEN"]), app)
    finally:
        app.terminate()
        app.wait(timeout=10)
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
