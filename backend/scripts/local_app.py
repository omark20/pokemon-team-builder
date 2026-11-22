"""Starting the app as a child process on this computer, for `make smoke` and `make burst`.

The host is always 127.0.0.1, so neither script can reach the public site. The port is
chosen free when the script runs: with a fixed port, a script could get an answer from
another copy of the app already listening there, take it for its own, and send its
requests to that copy and its database.
"""

import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx

HOST = "127.0.0.1"
BACKEND = Path(__file__).resolve().parents[1]
START_SECONDS = 30


def free_port() -> int:
    """A port nothing listens on right now, chosen by the operating system."""
    with socket.socket() as probe:
        probe.bind((HOST, 0))
        return int(probe.getsockname()[1])


def start_app(
    port: int, environment: dict[str, str] | None = None, quiet: bool = False
) -> subprocess.Popen[bytes]:
    """The app as uvicorn runs it on the host (one worker), on HOST and this port.

    `quiet` leaves out the access log, a line per request, for scripts that send thousands.
    """
    command = [sys.executable, "-m", "uvicorn", "app.main:app", "--host", HOST]
    command += ["--port", str(port), "--workers", "1", "--no-server-header"]
    command += ["--log-level", "warning"] if quiet else []
    return subprocess.Popen(command, cwd=BACKEND, env=environment)


def wait_until_up(app: subprocess.Popen[bytes], address: str) -> str | None:
    """None once our own child answers /healthz; otherwise what went wrong."""
    deadline = time.monotonic() + START_SECONDS
    while time.monotonic() < deadline:
        try:
            answered = httpx.get(address + "/healthz").status_code == 200
        except httpx.TransportError:
            answered = False
        # An answer counts only while our child is still running: otherwise it came from
        # someone else.
        if app.poll() is not None:
            return "the app exited while starting"
        if answered:
            return None
        time.sleep(0.5)
    return f"/healthz did not answer within {START_SECONDS} seconds"
