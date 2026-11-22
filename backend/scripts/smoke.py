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
from pathlib import Path

import httpx
from smoke_steps import (
    Smoke,
    SmokeFailure,
    alert_for_a,
    back_to_baseline,
    clean_up,
    counter_a,
    full_list,
    full_scan,
    no_alert_for_b,
    no_demo_active,
    patch_stored_alone,
    patched_scan,
    reset,
    team_a,
)

ADDRESS = "http://127.0.0.1:8765"
BACKEND = Path(__file__).resolve().parents[1]
START_SECONDS = 30
STEPS: list[tuple[str, Callable[[Smoke], None]]] = [
    ("0 no demo is active", no_demo_active),
    ("1 a full live scan ends ok", full_scan),
    ("2 the list matches the captures", full_list),
    ("3 visitor A's team is stored in order", team_a),
    ("4 A's counter team is the expected one", counter_a),
    ("5 storing a patch alone changes nothing", patch_stored_alone),
    ("6 a scan applies the patch", patched_scan),
    ("7 A gets the demo alert and the list shows it", alert_for_a),
    ("8 B, without Charizard, gets nothing", no_alert_for_b),
    ("9 reset", reset),
    ("10 everything is back and the next scan is a no-op", back_to_baseline),
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
            smoke = Smoke(http, os.environ["SCAN_TOKEN"], admin_token=os.environ["ADMIN_TOKEN"])
            passed = run_steps(smoke, app)
    finally:
        app.terminate()
        app.wait(timeout=10)
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
