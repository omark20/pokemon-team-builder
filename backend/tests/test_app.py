"""Rules every request passes: health check, headers, origin check, hidden errors."""

import threading
from collections.abc import Iterator

import anyio.to_thread
import pytest
from conftest import SCAN_TOKEN
from fastapi.testclient import TestClient

from app import auth, scan
from app.config import Settings
from app.main import create_app

BOOM_MESSAGE = "secret-looking text postgresql://user:pw@host/db"


def test_healthz_answers_without_touching_the_database(
    client: TestClient, connect_calls: list[str]
) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert connect_calls == []


def test_security_headers_on_every_response(client: TestClient) -> None:
    refused = client.post("/api/admin/scan", headers={"Origin": "https://evil.example"})
    for response in (client.get("/healthz"), client.get("/no-such-page"), refused):
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["x-frame-options"] == "DENY"
        assert response.headers["referrer-policy"] == "no-referrer"
        assert response.headers["strict-transport-security"] == "max-age=31536000"
        policy = response.headers["content-security-policy"]
        assert "default-src 'self'" in policy
        assert "img-src 'self' https://raw.githubusercontent.com data:" in policy
        assert "frame-ancestors 'none'" in policy
        assert "unsafe-inline" not in policy


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
def test_documentation_routes_are_off(client: TestClient, path: str) -> None:
    assert client.get(path).status_code == 404


def test_write_from_another_site_is_refused(client: TestClient) -> None:
    response = client.post("/api/admin/scan", headers={"Origin": "https://evil.example"})
    assert response.status_code == 403


def test_write_from_own_origin_or_without_origin_reaches_the_token_check(
    client: TestClient,
) -> None:
    own = client.post("/api/admin/scan", headers={"Origin": "https://testserver"})
    without = client.post("/api/admin/scan")
    assert own.status_code == 401
    assert without.status_code == 401


def test_get_with_foreign_origin_is_not_refused(client: TestClient) -> None:
    response = client.get("/healthz", headers={"Origin": "https://evil.example"})
    assert response.status_code == 200


def test_unhandled_error_gives_a_generic_500_with_only_a_request_id(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(*args: object) -> int:
        raise ValueError(BOOM_MESSAGE)

    monkeypatch.setattr(scan, "start_run", fail)
    response = client.post("/api/admin/scan", headers={"Authorization": f"Bearer {SCAN_TOKEN}"})
    assert response.status_code == 500
    assert set(response.json()) == {"detail", "request_id"}
    assert BOOM_MESSAGE not in response.text


def test_unreachable_database_at_start_up_is_logged_without_its_message(
    caplog: pytest.LogCaptureFixture,
) -> None:
    unreachable = "postgresql://someone:hunter2@127.0.0.1:1/nowhere"
    settings = Settings(database_url=unreachable, scan_token=None, admin_token=None)
    with pytest.raises(RuntimeError), TestClient(create_app(settings)):
        pass
    assert "db_unreachable error_class=OperationalError" in caplog.text
    assert "hunter2" not in caplog.text and "someone" not in caplog.text


def test_healthz_answers_while_every_worker_thread_is_busy(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The host restarts a service whose health check stops answering, so /healthz must
    not need a worker thread: here every one is held inside a database route."""
    threads = 2
    held, release = threading.Semaphore(0), threading.Event()

    def blocked_current_user(*args: object) -> None:
        held.release()
        release.wait(timeout=10)

    def set_thread_limit() -> None:
        anyio.to_thread.current_default_thread_limiter().total_tokens = threads

    monkeypatch.setattr(auth, "current_user", blocked_current_user)
    client.portal.call(set_thread_limit)  # type: ignore[union-attr]
    readers = [threading.Thread(target=client.get, args=("/api/teams",)) for _ in range(threads)]
    for reader in readers:
        reader.start()
    for _ in range(threads):
        assert held.acquire(timeout=5)  # both worker threads are now inside a route
    health: list[int] = []
    probe = threading.Thread(target=lambda: health.append(client.get("/healthz").status_code))
    probe.start()
    probe.join(timeout=5)
    answered_while_busy = list(health)  # read before the worker threads are let go
    release.set()
    for reader in readers:
        reader.join(timeout=10)
    assert answered_while_busy == [200]


def _chunks(total: int) -> Iterator[bytes]:
    """A body sent in pieces with no Content-Length, as a chunked upload is."""
    yield b'{"name": "'
    for _ in range(total // 1024):
        yield b"x" * 1024
    yield b'"}'


@pytest.mark.parametrize(
    ("method", "path", "size"),
    [
        ("POST", "/api/teams", 20 * 1024),
        ("POST", "/api/admin/scan", 20 * 1024),  # no token: refused before the token check
        ("PUT", "/api/admin/demo/overrides", 80 * 1024),
    ],
)
@pytest.mark.parametrize("chunked", [False, True], ids=["content-length", "chunked"])
def test_an_oversized_body_is_refused_with_413_before_it_is_read(
    client: TestClient, method: str, path: str, size: int, chunked: bool
) -> None:
    body: bytes | Iterator[bytes] = _chunks(size) if chunked else b"x" * size
    headers = {"Content-Type": "application/json"}
    response = client.request(method, path, content=body, headers=headers)
    assert response.status_code == 413
    assert response.headers["x-content-type-options"] == "nosniff"
