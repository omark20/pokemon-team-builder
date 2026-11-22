"""Username and password rules, and password hashing. No database."""

import pytest

from app import accounts
from app.accounts import (
    COMMON_PASSWORDS,
    MAX_PASSWORD,
    MIN_PASSWORD,
    hash_password,
    password_matches,
    password_problem,
    username_problem,
)


@pytest.mark.parametrize(
    ("username", "allowed"),
    [
        ("ash", True),
        ("Ash_Ketchum-1.0", True),
        ("1st", True),
        ("x" * 20, True),
        ("ab", False),
        ("x" * 21, False),
        ("ash ketchum", False),
        ("ash\x00", False),
        (".ash", False),
        ("аsh", False),  # a Cyrillic а that looks like a Latin a
    ],
    ids=[
        "3",
        "mixed",
        "digit-first",
        "20",
        "2",
        "21",
        "space",
        "control",
        "leading-dot",
        "other-alphabet",
    ],
)
def test_usernames(username: str, allowed: bool) -> None:
    assert (username_problem(username) is None) == allowed


@pytest.mark.parametrize(
    ("password", "allowed"),
    [
        ("correct horse", True),
        ("пароль-длинный", True),
        ("x" * 128, True),
        ("abc1234", False),
        ("x" * 129, False),
        ("PassWord1", False),  # "password1" is on the list
        ("MistyRules", False),  # the username, in other capitals
    ],
    ids=["spaces", "other-alphabet", "128", "7", "129", "common", "the-username"],
)
def test_passwords(password: str, allowed: bool) -> None:
    assert (password_problem(password, "mistyrules") is None) == allowed


def test_a_hash_verifies_its_password_only_and_names_its_settings() -> None:
    stored = hash_password("correct horse")
    assert stored.startswith("$argon2id$v=19$m=19456,t=2,p=1$")
    assert password_matches(stored, "correct horse")
    assert not password_matches(stored, "correct horsf")


def test_no_stored_hash_never_matches() -> None:
    assert not password_matches(None, "correct horse")


def test_the_shipped_list_holds_only_long_enough_lower_case_entries() -> None:
    assert len(COMMON_PASSWORDS) == 46_483  # SecLists NCSC list, 8 or more characters, lower case
    assert all(len(entry) >= MIN_PASSWORD for entry in COMMON_PASSWORDS)
    assert all(entry == entry.lower() for entry in COMMON_PASSWORDS)


def test_a_password_over_the_maximum_fails_after_the_dummy_work_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stored = hash_password("x" * MAX_PASSWORD)
    verified: list[tuple[str, int]] = []

    class SpyHasher:
        def verify(self, stored_hash: str, password: str) -> bool:
            verified.append((stored_hash, len(password)))
            return bool(accounts.PasswordHasher.verify(real, stored_hash, password))

    real = accounts.HASHER
    monkeypatch.setattr(accounts, "HASHER", SpyHasher())
    assert not password_matches(stored, "x" * MAX_PASSWORD + "y" * 16_000)
    assert verified == [(accounts.DUMMY_HASH, MAX_PASSWORD)]
