"""`make smoke`: drive the real app and its database through the HTTP API, step by step.

It starts the app on 127.0.0.1, on a port free at the time, against the local development
database, runs the steps in order, prints "ok" or "FAIL" with what was expected and what
came back, and stops the app however it ends. The scan in step 1 reads the live PokéAPI.
The host is a constant, so this script cannot be pointed at the public site; the token
is the local one from the git-ignored .env, and no token or cookie is ever printed.
"""

import os
import subprocess
import sys
from collections.abc import Callable

import httpx
from local_app import HOST, free_port, start_app, wait_until_up
from smoke_steps import (
    Smoke,
    SmokeFailure,
    account_a,
    alert_for_a,
    back_to_baseline,
    clean_up,
    counter_a,
    delete_account_a,
    full_list,
    full_scan,
    legendary_filter,
    no_alert_for_b,
    no_demo_active,
    patch_stored_alone,
    patched_scan,
    reset,
    team_a,
)

STEPS: list[tuple[str, Callable[[Smoke], None]]] = [
    ("0 no demo is active", no_demo_active),
    ("1 a full live scan ends ok", full_scan),
    ("2 the list matches the captures", full_list),
    ("3 visitor A's team is stored in order", team_a),
    ("3b A's account keeps the team across signing out and in", account_a),
    ("4 A's counter team is the expected one", counter_a),
    ("4b leaving out legendaries changes the pool and the picks", legendary_filter),
    ("5 storing a patch alone changes nothing", patch_stored_alone),
    ("6 a scan applies the patch", patched_scan),
    ("7 A gets the demo alert and the list shows it", alert_for_a),
    ("8 B, without Charizard, gets nothing", no_alert_for_b),
    ("9 reset", reset),
    ("10 everything is back and the next scan is a no-op", back_to_baseline),
    ("11 A deletes the account this run made", delete_account_a),
]


def run_steps(smoke: Smoke, app: subprocess.Popen[bytes]) -> bool:
    """Every step in order; stop at the first that fails."""
    name = "start the app"
    try:
        problem = wait_until_up(app, str(smoke.http.base_url).rstrip("/"))
        if problem:
            raise SmokeFailure(f"the app to start ({problem})")
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
    port = free_port()
    app = start_app(port)
    try:
        with httpx.Client(base_url=f"http://{HOST}:{port}", timeout=30) as http:
            smoke = Smoke(http, os.environ["SCAN_TOKEN"], admin_token=os.environ["ADMIN_TOKEN"])
            passed = run_steps(smoke, app)
    finally:
        app.terminate()
        app.wait(timeout=10)
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
