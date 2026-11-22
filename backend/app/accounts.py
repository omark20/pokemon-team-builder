"""Usernames and passwords: the rules they must meet, and how passwords are hashed.

Accounts are optional. A username is 3 to 20 of a-z (either case), digits, `_`, `-` and
`.`, starting with a letter or digit, and is unique whatever the capitals. A password is
8 to 128 characters of anything, never trimmed, and is refused if it is one of the
commonly used passwords or the username itself. Passwords are hashed with Argon2id at
OWASP's second minimum setting: 19 MiB of memory, 2 passes, 1 lane. No database or web
code here.
"""

import re
import secrets
from pathlib import Path

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

USERNAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{2,19}")
MIN_PASSWORD, MAX_PASSWORD = 8, 128

# Written out, not the library's defaults (64 MiB, 3 passes, 4 lanes), which are heavier.
HASHER = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1)

# SecLists' 100k-most-used-passwords-NCSC.txt, those of 8 or more characters, lower case.
# The first line names the source and its licence.
COMMON_PASSWORDS = frozenset(
    Path(__file__).with_name("common_passwords.txt").read_text(encoding="utf-8").splitlines()[1:]
)

# Verified when a typed username matches no account, so that case takes the same time
# as a wrong password and the answer cannot tell the two apart.
DUMMY_HASH = HASHER.hash(secrets.token_urlsafe(16))


def username_problem(username: str) -> str | None:
    """The rule a username breaks, in words for the visitor, or None."""
    if USERNAME.fullmatch(username):
        return None
    return "A username is 3 to 20 letters, digits, _, - or ., starting with a letter or digit."


def password_problem(password: str, username: str) -> str | None:
    """The rule a password breaks, in words for the visitor, or None."""
    if len(password) < MIN_PASSWORD:
        return f"A password needs at least {MIN_PASSWORD} characters."
    if len(password) > MAX_PASSWORD:
        return f"A password can be at most {MAX_PASSWORD} characters."
    if password.lower() in COMMON_PASSWORDS:
        return "That password is too common. Choose another."
    if password.lower() == username.lower():
        return "The password can't be the username."
    return None


def hash_password(password: str) -> str:
    """The stored form: Argon2id, with its salt and settings written into the string."""
    return HASHER.hash(password)


def password_matches(stored_hash: str | None, password: str) -> bool:
    """Whether the password matches; with no stored hash, the dummy one is verified.

    A password over MAX_PASSWORD cannot be right, as none can be set: it fails, after the
    dummy hash is verified against its first MAX_PASSWORD characters, so the answer takes
    the time of any other and a long body is never hashed whole.
    """
    fits = len(password) <= MAX_PASSWORD
    checked = stored_hash if fits and stored_hash is not None else DUMMY_HASH
    try:
        matched = HASHER.verify(checked, password[:MAX_PASSWORD])
    except (VerificationError, InvalidHashError):  # a wrong password, or a damaged hash
        return False
    return matched and checked is not DUMMY_HASH
