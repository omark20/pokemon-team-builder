"""The steps of `make smoke` and what they share; `smoke.py` runs them in order.

Expected values come from the captures in samples/, never from the app's own output.
"""

import time
from dataclasses import dataclass, field
from typing import Any

import httpx

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
# Two Charizard: the full-pool answer includes Diancie, which is mythical
# (census_all_species.tsv). Leaving out the 94 flagged default forms leaves 931 (fact 20).
TEAM_C = [6, 6]
MYTHICAL_PICK = "diancie"
POOL_WITHOUT_LEGENDARIES = 931
# The demo patch: Charizard's attack, 84 in the capture, as if PokéAPI now said 94.
PATCH = {"pokemon": {"6": {"attack": 94}}, "type_chart": []}
ATTACK_BEFORE, ATTACK_AFTER = 84, 94


class SmokeFailure(Exception):
    """A step did not hold; the message says what was expected and what came back."""


@dataclass
class Smoke:
    """What the steps share: the HTTP client, the local token, and baselines taken."""

    http: httpx.Client
    scan_token: str
    list_baseline: list[dict[str, Any]] = field(default_factory=list)
    admin_token: str = ""
    cookies: dict[str, str] = field(default_factory=dict)  # visitor name: uid value
    teams: dict[str, int] = field(default_factory=dict)  # visitor name: their team's ID
    alert_baselines: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    patched: bool = False  # this run stored a demo patch, so it must reset it

    def scan_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.scan_token}"}

    def admin_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.admin_token}"}

    def alerts(self, visitor: str) -> list[dict[str, Any]]:
        alerts: list[dict[str, Any]] = self.as_visitor(visitor, "GET", "/api/alerts").json()
        return alerts

    def demo_active(self) -> bool:
        return bool(self.http.get("/api/scan/status").json()["demo_active"])

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
    scan_and_wait(smoke, None)


def scan_and_wait(smoke: Smoke, body: dict[str, Any] | None) -> dict[str, Any]:
    """Trigger a scan, wait for it, and require it to end ok with 0 failed."""
    response = smoke.http.post("/api/admin/scan", headers=smoke.scan_headers(), json=body)
    check(response.status_code == 202, "202 from the scan trigger", response.status_code)
    run = wait_for_run(smoke, response.json()["run_id"])
    check(
        run["status"] == "ok" and run["failed"] == 0,
        "the run to end ok with 0 failed",
        f"{run['status']} with {run['failed']} failed; see the app's lines for run_id={run['id']}",
    )
    return run


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


def legendary_filter(smoke: Smoke) -> None:
    smoke.new_team("C", "Smoke C", TEAM_C)
    path = f"/api/teams/{smoke.teams['C']}/counter"
    default = [p["counter"]["name"] for p in smoke.as_visitor("C", "GET", path).json()["picks"]]
    check(MYTHICAL_PICK in default, f"{MYTHICAL_PICK} among the default picks", default)
    options = {"params": {"leave_out_legendary": "true"}}
    body = smoke.as_visitor("C", "GET", path, **options).json()
    names = [pick["counter"]["name"] for pick in body["picks"]]
    seen = (body["pool_size"], body["legendary_left_out"], MYTHICAL_PICK in names)
    expected = (POOL_WITHOUT_LEGENDARIES, True, False)
    check(seen == expected, f"pool 931, legendary_left_out, no {MYTHICAL_PICK}", seen)


def patch_stored_alone(smoke: Smoke) -> None:
    smoke.new_team("B", "Smoke B", [25])
    smoke.alert_baselines = {visitor: smoke.alerts(visitor) for visitor in ("A", "B")}
    with_scan_token = smoke.http.put(
        "/api/admin/demo/overrides", headers=smoke.scan_headers(), json=PATCH
    )
    check(with_scan_token.status_code == 401, "401 for SCAN_TOKEN", with_scan_token.status_code)
    stored = smoke.http.put("/api/admin/demo/overrides", headers=smoke.admin_headers(), json=PATCH)
    check(stored.status_code == 200, "200 for ADMIN_TOKEN", stored.status_code)
    smoke.patched = True
    check(smoke.alerts("A") == smoke.alert_baselines["A"], "A's alerts unchanged", "a new alert")
    check(smoke.demo_active(), "demo_active true", "false")


def patched_scan(smoke: Smoke) -> None:
    run = scan_and_wait(smoke, {"pokemon_ids": [6]})
    check(run["changed"] == 1, "1 changed", run["changed"])


def alert_for_a(smoke: Smoke) -> None:
    known = {alert["id"] for alert in smoke.alert_baselines["A"]}
    new = [alert for alert in smoke.alerts("A") if alert["id"] not in known]
    seen = [
        (
            a["pokemon_id"],
            a["field"],
            a["old_value"],
            a["new_value"],
            a["is_demo"],
            a["your_pokemon"],
        )
        for a in new
    ]
    expected = [(6, "attack", ATTACK_BEFORE, ATTACK_AFTER, True, [6])]
    check(seen == expected, f"one new alert {expected}", seen)
    entry = next(e for e in smoke.http.get("/api/pokemon").json() if e["id"] == 6)
    check(entry["stats"][1] == ATTACK_AFTER, "the list to show attack 94", entry["stats"])


def no_alert_for_b(smoke: Smoke) -> None:
    check(smoke.alerts("B") == smoke.alert_baselines["B"], "B's alerts unchanged", "a new alert")


def reset(smoke: Smoke) -> None:
    response = smoke.http.post("/api/admin/demo/reset", headers=smoke.admin_headers())
    check(response.status_code == 200, "200 from reset", response.status_code)
    smoke.patched = False


def back_to_baseline(smoke: Smoke) -> None:
    check(smoke.alerts("A") == smoke.alert_baselines["A"], "A's alerts back", "a demo alert left")
    listed = smoke.http.get("/api/pokemon").json()
    check(listed == smoke.list_baseline, "the list equal to step 2's", "a different list")
    check(not smoke.demo_active(), "demo_active false", "true")
    run = scan_and_wait(smoke, {"pokemon_ids": [6]})
    check(run["changed"] == 0, "the next scan to change nothing", run["changed"])
    check(smoke.alerts("A") == smoke.alert_baselines["A"], "A's alerts still back", "an alert")


def clean_up(smoke: Smoke) -> None:
    """Reset a demo this run stored and delete its teams, whatever happened before."""
    if smoke.patched:
        smoke.http.post("/api/admin/demo/reset", headers=smoke.admin_headers())
    for visitor, team_id in smoke.teams.items():
        smoke.as_visitor(visitor, "DELETE", f"/api/teams/{team_id}")


def _has(entry: dict[str, Any], expected: dict[str, Any]) -> bool:
    return all(entry[key] == value for key, value in expected.items())
