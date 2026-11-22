"""The HTTP source of PokéAPI: what each kind of answer or failure becomes.

PokéAPI is replaced by httpx's MockTransport, so no request leaves this computer.
"""

from collections.abc import Callable

import httpx
import pytest

from app.pokeapi import BASE_URL, PokeApiSource, UpstreamError

Answer = Callable[[httpx.Request], httpx.Response]


def respond(status: int, content: bytes = b"{}") -> Answer:
    return lambda request: httpx.Response(status, content=content)


def fail_with(error: type[httpx.RequestError]) -> Answer:
    def answer(request: httpx.Request) -> httpx.Response:
        raise error("simulated", request=request)

    return answer


def source_answering(answer: Answer) -> PokeApiSource:
    return PokeApiSource(httpx.Client(base_url=BASE_URL, transport=httpx.MockTransport(answer)))


@pytest.mark.parametrize(
    ("answer", "outcome"),
    [
        (respond(200, b'{"id": 6}'), {"id": 6}),
        (respond(404), None),
    ],
    ids=["ok", "not-found"],
)
def test_an_answer_is_its_json_and_a_404_is_none(answer: Answer, outcome: object) -> None:
    assert source_answering(answer).get("pokemon/6/") == outcome


@pytest.mark.parametrize(
    ("path", "answer", "reason", "retryable"),
    [
        ("pokemon/6/", respond(500), "http_500", True),
        ("pokemon/6/", respond(503), "http_503", True),
        ("pokemon/6/", respond(429), "http_429", True),
        ("pokemon/6/", respond(403), "http_403", False),
        ("pokemon/6/", respond(200, b"not json"), "invalid_json", False),
        ("pokemon/6/", fail_with(httpx.ReadTimeout), "timeout", True),
        ("pokemon/6/", fail_with(httpx.ConnectError), "connection", True),
        ("pokemon/6/", fail_with(httpx.DecodingError), "request_failed", False),
        ("pokemon/6/", fail_with(httpx.TooManyRedirects), "request_failed", False),
        ("pokemon/6\x00/", respond(200), "invalid_url", False),
        ("https://example.com/pokemon/6/", respond(200), "foreign_url", False),
    ],
    ids=[
        "500",
        "503",
        "429",
        "403",
        "invalid-json",
        "timeout",
        "connection",
        "decoding",
        "redirects",
        "invalid-url",
        "foreign-url",
    ],
)
def test_every_failure_is_an_upstream_error_saying_whether_to_retry(
    path: str, answer: Answer, reason: str, retryable: bool
) -> None:
    with pytest.raises(UpstreamError) as failed:
        source_answering(answer).get(path)
    assert (failed.value.reason, failed.value.retryable) == (reason, retryable)
