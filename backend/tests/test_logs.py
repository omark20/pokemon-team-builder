"""The log helpers: one line per event, outside text escaped, exceptions without messages."""

import logging

import pytest

from app.logs import log_event, log_exception, outside

logger = logging.getLogger("test")


def test_event_line_is_name_then_fields(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO):
        log_event(logger, logging.WARNING, "pokemon_skipped", run_id=12, reason="timeout")
    assert caplog.messages == ["pokemon_skipped run_id=12 reason=timeout"]


def test_outside_text_cannot_start_a_new_line_or_run_long() -> None:
    quoted = outside("fire\nWARNING app.scan forged=1" + "x" * 200)
    # 30 characters before the x's, so 70 of them survive the cut at 100.
    assert quoted == "'fire\\nWARNING app.scan forged=1" + "x" * 70 + "'"


def test_exception_is_logged_by_class_and_frames_only(caplog: pytest.LogCaptureFixture) -> None:
    def fail() -> None:
        raise KeyError("hidden message")

    try:
        fail()
    except KeyError as exc:
        with caplog.at_level(logging.INFO):
            log_exception(logger, "scan_crashed", exc, run_id=3)
    [line] = caplog.messages
    assert line.startswith("scan_crashed run_id=3 error_class=KeyError frames=")
    assert "test_logs.py:" in line and ":fail" in line
    assert "hidden message" not in line
