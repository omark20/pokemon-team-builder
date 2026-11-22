"""Reading the settings: blank tokens, and the two tokens kept apart."""

import pytest

from app.config import load_settings


@pytest.mark.parametrize(
    ("scan", "admin", "expected"),
    [
        ("scan-secret", "admin-secret", ("scan-secret", "admin-secret")),
        ("   ", "admin-secret", (None, "admin-secret")),
        ("", "\t", (None, None)),
    ],
    ids=["both-set", "blank-scan", "empty-and-blank"],
)
def test_a_blank_token_counts_as_unset(
    monkeypatch: pytest.MonkeyPatch, scan: str, admin: str, expected: tuple[str | None, ...]
) -> None:
    monkeypatch.setenv("SCAN_TOKEN", scan)
    monkeypatch.setenv("ADMIN_TOKEN", admin)
    settings = load_settings()
    assert (settings.scan_token, settings.admin_token) == expected


def test_the_two_tokens_must_differ(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCAN_TOKEN", "same-secret")
    monkeypatch.setenv("ADMIN_TOKEN", "same-secret")
    with pytest.raises(RuntimeError) as refused:
        load_settings()
    assert "SCAN_TOKEN and ADMIN_TOKEN" in str(refused.value)
    assert "same-secret" not in str(refused.value)
