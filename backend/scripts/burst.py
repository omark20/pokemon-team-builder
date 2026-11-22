"""`make burst`: bursts of reads against the app on a database held to the deployed size.

The database is Compose's `db-burst` service: 0.1 CPU, 256 MB, reached over TLS, as the
deployed one is. The app runs as it does on the host, one uvicorn worker. Two bursts:

1. 720 reads of /api/scan/status from one address, 24 at a time: the first 600 are
   answered and the rest refused with 429, the read limit doing its job.
2. 3,000 reads from five addresses, 48 at a time, more at once than the app has worker
   threads: every one answered, none refused or failed.

Then the database is stopped and started with the app left running, as the host does
for maintenance: while it is down every read is a 503 within about two seconds, and
within 30 seconds of its return reads are answered again, with no restart of the app.

Throughout, /healthz is asked every quarter of a second and must answer within 5 seconds
every time, since the host restarts a service whose health check stops answering.
"""

import os
import subprocess
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import httpx
from local_app import HOST, free_port, start_app, wait_until_up

DATABASE = "postgresql://pokemon:{password}@127.0.0.1:5435/pokemon?sslmode=require"
COMPOSE = ["docker", "compose", "--profile", "burst"]
DOWN_READS = 10
DOWN_READ_SECONDS = 2.5  # the pool's 2-second wait, and a little for the answer
RECOVERY_SECONDS = 30
HEALTH_EVERY_SECONDS = 0.25
HEALTH_TIMEOUT_SECONDS = 5


@dataclass(frozen=True)
class Burst:
    name: str
    total: int
    at_once: int
    addresses: int  # one: the connection's own; more: sent as the edge's address header
    expected: dict[int, int]  # status code: how many


BURSTS = [
    Burst("one address past its read limit", 720, 24, 1, {200: 600, 429: 120}),
    Burst("five addresses, more at once than worker threads", 3000, 48, 5, {200: 3000}),
]


class HealthProbe:
    """Asks /healthz on a timer in its own thread; counts the answers that were not 200."""

    def __init__(self, address: str) -> None:
        self.address = address
        self.asked = 0
        self.failed = 0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run)

    def __enter__(self) -> "HealthProbe":
        self._thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self._stop.set()
        self._thread.join()

    def _run(self) -> None:
        with httpx.Client(base_url=self.address, timeout=HEALTH_TIMEOUT_SECONDS) as http:
            while not self._stop.wait(HEALTH_EVERY_SECONDS):
                self.asked += 1
                try:
                    ok = http.get("/healthz").status_code == 200
                except httpx.HTTPError:
                    ok = False
                self.failed += not ok


def run_burst(burst: Burst, address: str) -> tuple[Counter[int | str], float]:
    """Send the burst; the count of each status code (or error), and the seconds taken."""
    codes: Counter[int | str] = Counter()
    limits = httpx.Limits(max_connections=burst.at_once)
    with httpx.Client(base_url=address, timeout=30, limits=limits) as http:

        def one(number: int) -> None:
            visitor = f"203.0.113.{number % burst.addresses + 1}"
            headers = {} if burst.addresses == 1 else {"cf-connecting-ip": visitor}
            try:
                codes[http.get("/api/scan/status", headers=headers).status_code] += 1
            except httpx.HTTPError as exc:
                codes[type(exc).__name__] += 1

        start = time.perf_counter()
        with ThreadPoolExecutor(burst.at_once) as pool:
            list(pool.map(one, range(burst.total)))
    return codes, time.perf_counter() - start


def check(burst: Burst, address: str) -> bool:
    with HealthProbe(address) as health:
        codes, seconds = run_burst(burst, address)
    passed = dict(codes) == burst.expected and health.failed == 0
    print(
        f"burst: {'ok  ' if passed else 'FAIL'} {burst.name}: {dict(codes)} in {seconds:.1f} s"
        f" (expected {burst.expected}); /healthz {health.asked - health.failed}/{health.asked}",
        flush=True,
    )
    return passed


def timed_read(http: httpx.Client, number: int) -> tuple[int | str, float]:
    """One status read from its own address, so the read limit never refuses it."""
    start = time.perf_counter()
    try:
        headers = {"cf-connecting-ip": f"198.51.100.{number % 250 + 1}"}
        code: int | str = http.get("/api/scan/status", headers=headers).status_code
    except httpx.HTTPError as exc:
        code = type(exc).__name__
    return code, time.perf_counter() - start


def seconds_until_answered(http: httpx.Client) -> float | None:
    """Seconds until a read is answered 200 again, or None after RECOVERY_SECONDS."""
    start = time.monotonic()
    for number in range(1000):
        if timed_read(http, number)[0] == 200:
            return time.monotonic() - start
        if time.monotonic() - start > RECOVERY_SECONDS:
            return None
        time.sleep(0.5)
    return None


def database_gone_and_back(address: str) -> bool:
    with HealthProbe(address) as health, httpx.Client(base_url=address, timeout=10) as http:
        subprocess.run([*COMPOSE, "stop", "db-burst"], check=True, capture_output=True)
        down = [timed_read(http, number) for number in range(DOWN_READS)]
        subprocess.run([*COMPOSE, "start", "db-burst"], check=True, capture_output=True)
        back_after = seconds_until_answered(http)
    codes = Counter(code for code, _ in down)
    slowest = max(seconds for _, seconds in down)
    passed = codes == {503: DOWN_READS} and slowest <= DOWN_READ_SECONDS
    passed = passed and back_after is not None and health.failed == 0
    recovered = "never" if back_after is None else f"{back_after:.1f} s after start"
    print(
        f"burst: {'ok  ' if passed else 'FAIL'} database gone and back: while down {dict(codes)},"
        f" slowest {slowest:.1f} s; answered again {recovered};"
        f" /healthz {health.asked - health.failed}/{health.asked}",
        flush=True,
    )
    return passed


def main() -> int:
    port = free_port()
    address = f"http://{HOST}:{port}"
    database_url = DATABASE.format(password=os.environ["POSTGRES_PASSWORD"])
    app = start_app(port, os.environ | {"DATABASE_URL": database_url}, quiet=True)
    try:
        problem = wait_until_up(app, address)
        if problem:
            print(f"burst: FAIL {problem}", flush=True)
        passed = not problem and all([check(burst, address) for burst in BURSTS])
        passed = passed and database_gone_and_back(address)
    finally:
        app.terminate()
        app.wait(timeout=10)
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
