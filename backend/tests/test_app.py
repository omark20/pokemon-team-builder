"""Rules every request passes: health check, headers, origin check, hidden errors."""

import logging

import pytest
from conftest import SCAN_TOKEN
from fastapi.testclient import TestClient

from app import db, scan
from app.config import Settings
from app.main import create_app

BOOM_MESSAGE = "secret-looking text postgresql://user:pw@host/db"


def test_healthz_answers_without_touching_the_database(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = []
    monkeypatch.setattr(db, "connect", lambda url: calls.append(url))
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert calls == []


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


def test_unhandled_error_gives_generic_500_and_logs_class_not_message(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def fail(conn: object, scope: str) -> int:
        raise ValueError(BOOM_MESSAGE)

    monkeypatch.setattr(scan, "start_run", fail)
    with caplog.at_level(logging.INFO):
        response = client.post("/api/admin/scan", headers={"Authorization": f"Bearer {SCAN_TOKEN}"})
    assert response.status_code == 500
    body = response.json()
    assert set(body) == {"detail", "request_id"}
    assert BOOM_MESSAGE not in response.text
    [line] = [r.getMessage() for r in caplog.records if "request_failed" in r.getMessage()]
    assert f"request_id={body['request_id']}" in line
    assert "method=POST route=/api/admin/scan" in line
    assert "error_class=ValueError" in line
    assert "postgresql" not in caplog.text and "secret-looking" not in caplog.text


def test_unreachable_database_at_start_up_is_logged_without_its_message(
    caplog: pytest.LogCaptureFixture,
) -> None:
    unreachable = "postgresql://someone:hunter2@127.0.0.1:1/nowhere"
    settings = Settings(database_url=unreachable, scan_token=None, admin_token=None)
    with pytest.raises(RuntimeError), TestClient(create_app(settings)):
        pass
    assert "db_unreachable error_class=OperationalError" in caplog.text
    assert "hunter2" not in caplog.text and "someone" not in caplog.text
