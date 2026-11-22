"""Per-address request limits: the real numbers, and what a full bucket covers."""

import logging

import pytest
from fastapi.testclient import TestClient

from app.limits import Limit, RateLimiter

READ_ENDPOINTS = ["/api/scan/status", "/api/teams", "/api/pokemon"]


@pytest.fixture
def full_read_bucket(client: TestClient) -> TestClient:
    """The client's address has used up a read bucket of two requests."""
    client.app.state.limiter = RateLimiter({"read": Limit(2, 60)})
    for _ in range(2):
        assert client.get("/api/pokemon").status_code == 200
    return client


@pytest.mark.parametrize(
    ("method", "path", "body", "allowed", "window"),
    [
        ("GET", "/api/pokemon", None, 600, 60),
        ("PATCH", "/api/teams/1", {"name": "x"}, 120, 60),
        ("POST", "/api/teams", {"name": "x"}, 20, 3600),
    ],
    ids=["reads", "writes", "new-visitors"],
)
def test_the_request_after_the_limit_is_refused_with_retry_after(
    client: TestClient, method: str, path: str, body: object, allowed: int, window: int
) -> None:
    for _ in range(allowed):
        client.cookies.clear()  # so that each team create is a first-time visitor
        assert client.request(method, path, json=body).status_code != 429
    client.cookies.clear()
    refused = client.request(method, path, json=body)
    assert refused.status_code == 429
    assert 1 <= int(refused.headers["retry-after"]) <= window


def test_one_full_read_bucket_refuses_every_read_endpoint(full_read_bucket: TestClient) -> None:
    for path in READ_ENDPOINTS:
        assert full_read_bucket.get(path).status_code == 429, path


def test_a_new_made_up_cookie_on_each_request_does_not_avoid_the_limit(
    full_read_bucket: TestClient,
) -> None:
    for number in range(3):
        cookie = {"Cookie": f"uid=made-up-{number}"}
        response = full_read_bucket.get("/api/scan/status", headers=cookie)
        assert response.status_code == 429


def test_a_refused_request_opens_no_database_connection(
    full_read_bucket: TestClient, connect_calls: list[str]
) -> None:
    assert full_read_bucket.get("/api/scan/status").status_code == 429
    assert connect_calls == []


def test_another_address_has_its_own_bucket(full_read_bucket: TestClient) -> None:
    other = TestClient(full_read_bucket.app, base_url="https://testserver", client=("10.0.0.2", 1))
    assert other.get("/api/pokemon").status_code == 200


def test_refusals_are_logged_once_per_address_per_window(
    full_read_bucket: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO):
        for _ in range(3):
            full_read_bucket.get("/api/pokemon")
    [line] = [message for message in caplog.messages if "rate_limited" in message]
    assert line.endswith("route=/api/pokemon bucket=read")
